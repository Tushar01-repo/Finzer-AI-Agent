
"""Context-aware tracing for the Finzer ReAct agent."""

from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from app.observability.config import get_observability_settings
from app.observability.logger import get_logger, log_context


_current_span = contextvars.ContextVar("finzer_current_span", default=None)

logger = get_logger("finzer.tracing")


@dataclass
class TraceSpan:
    """One timed operation within an agent execution."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    ended_at: datetime | None = None
    duration_ms: float | None = None
    status: str = "running"
    error_type: str | None = None


def current_span() -> TraceSpan | None:
    """Return the active span in the current execution context."""
    return _current_span.get()


@contextlib.contextmanager
def trace_span(
    name: str,
    *,
    run_id: str | None = None,
    user_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[TraceSpan | None]:
    """Create a nested span and emit a completion event."""
    settings = get_observability_settings()

    if not settings.tracing_enabled:
        yield None
        return

    parent = current_span()
    trace_id = parent.trace_id if parent else uuid.uuid4().hex

    span = TraceSpan(
        trace_id=trace_id,
        span_id=uuid.uuid4().hex[:16],
        parent_span_id=parent.span_id if parent else None,
        name=name,
        started_at=datetime.now(timezone.utc),
        attributes=dict(attributes or {}),
    )

    token = _current_span.set(span)
    start = time.perf_counter()

    try:
        with log_context(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
        ):
            try:
                yield span
                span.status = "ok"
            except Exception as exc:
                span.status = "error"
                span.error_type = type(exc).__name__
                raise
            finally:
                span.ended_at = datetime.now(timezone.utc)
                span.duration_ms = round(
                    (time.perf_counter() - start) * 1000, 3
                )

                logger.info(
                    "trace_span_completed",
                    span_name=span.name,
                    span_id=span.span_id,
                    parent_span_id=span.parent_span_id,
                    duration_ms=span.duration_ms,
                    status=span.status,
                    error_type=span.error_type,
                    attributes=span.attributes,
                )
    finally:
        _current_span.reset(token)


def add_span_attributes(**attributes: Any) -> None:
    """Attach metadata to the active span."""
    span = current_span()
    if span is not None:
        span.attributes.update(attributes)
