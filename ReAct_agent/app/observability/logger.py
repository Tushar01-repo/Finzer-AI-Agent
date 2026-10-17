
"""Structured, context-aware logging for the Finzer ReAct agent."""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterator

from app.observability.config import get_observability_settings


_run_id = contextvars.ContextVar("finzer_run_id", default=None)
_user_id = contextvars.ContextVar("finzer_user_id", default=None)
_trace_id = contextvars.ContextVar("finzer_trace_id", default=None)

_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "set_cookie",
    "database_url",
    "private_key",
    "credential",
    "credentials",
}

_BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+"
)


def _normalize_key(key: Any) -> str:
    return str(key).lower().replace("-", "_").replace(" ", "_")


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_api_key")
    )


def _sanitize(value: Any, *, redact: bool) -> Any:
    """Convert values into JSON-safe objects and redact common secrets."""
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if redact and _is_sensitive_key(key)
                else _sanitize(item, redact=redact)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item, redact=redact) for item in value]

    if isinstance(value, str):
        if redact:
            return _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        return value

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    # Avoid serializing arbitrary objects or exception internals.
    return f"<{type(value).__name__}>"


class ContextFilter(logging.Filter):
    """Attach the current agent execution context to each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id.get()
        record.user_id = _user_id.get()
        record.trace_id = _trace_id.get()
        return True


class StructuredFormatter(logging.Formatter):
    """Produce structured JSON or developer-friendly console output."""

    def __init__(self, *, output_format: str = "json", redact: bool = True):
        super().__init__()
        self.output_format = output_format
        self.redact = redact

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _sanitize(message, redact=self.redact),
            "run_id": getattr(record, "run_id", None),
            "user_id": getattr(record, "user_id", None),
            "trace_id": getattr(record, "trace_id", None),
        }

        extra_fields = getattr(record, "structured_fields", None)
        if isinstance(extra_fields, dict):
            payload["fields"] = _sanitize(
                extra_fields, redact=self.redact
            )

        if record.exc_info:
            # Do not serialize raw tracebacks when redaction is enabled:
            # exception messages may contain tokens, URLs or credentials.
            payload["exception"] = (
                record.exc_info[0].__name__
                if record.exc_info[0]
                else "Exception"
            )

        if self.output_format == "console":
            context = f"run={payload['run_id']}" if payload["run_id"] else ""
            return (
                f"{payload['timestamp']} "
                f"[{payload['level']}] "
                f"{payload['logger']} {context} "
                f"{payload['message']}"
            )

        return json.dumps(payload, ensure_ascii=False, default=str)


class AgentLogger:
    """Small wrapper around Python logging with structured event fields."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def log(
        self,
        level: int,
        event: str,
        **fields: Any,
    ) -> None:
        self._logger.log(
            level,
            event,
            extra={"structured_fields": fields},
        )

    def debug(self, event: str, **fields: Any) -> None:
        self.log(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self.log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self.log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self.log(logging.ERROR, event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._logger.exception(
            event,
            extra={"structured_fields": fields},
        )


def get_logger(name: str) -> AgentLogger:
    """Get or configure a Finzer structured logger."""
    settings = get_observability_settings()

    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level)
    logger.propagate = False

    if not any(
        getattr(handler, "_finzer_handler", False)
        for handler in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            StructuredFormatter(
                output_format=settings.log_format,
                redact=settings.redact_sensitive_data,
            )
        )
        handler.addFilter(ContextFilter())
        handler._finzer_handler = True
        logger.addHandler(handler)

    return AgentLogger(logger)


@contextlib.contextmanager
def log_context(
    *,
    run_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
) -> Iterator[None]:
    """Bind identifiers for one execution without leaking across requests."""
    tokens = []

    try:
        if run_id is not None:
            tokens.append((_run_id, _run_id.set(run_id)))

        if user_id is not None:
            tokens.append((_user_id, _user_id.set(user_id)))

        if trace_id is not None:
            tokens.append((_trace_id, _trace_id.set(trace_id)))

        yield

    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
