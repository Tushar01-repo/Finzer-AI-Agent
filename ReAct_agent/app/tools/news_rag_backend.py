from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class NewsRAGBackendError(RuntimeError):
    """Base error raised by the News RAG backend."""


class NewsRAGBackendTimeoutError(NewsRAGBackendError):
    """Raised when news retrieval exceeds the configured timeout."""


class NewsRAGBackendResponseError(NewsRAGBackendError):
    """Raised when the ingestion bridge returns an invalid response."""


class IngestionNewsRAGBackend:
    """
    ReAct-side adapter for the ingestion service News RAG bridge.

    Boundary:

        ReAct_agent
            -> IngestionNewsRAGBackend
            -> subprocess
            -> ingestion_service
            -> news_rag_bridge
            -> NewsRetriever
            -> PostgreSQL / pgvector

    Retrieval logic intentionally remains inside ingestion_service.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = 60,
        ingestion_service_dir: str | Path | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.timeout_seconds = timeout_seconds

        if ingestion_service_dir is None:
            repo_root = Path(__file__).resolve().parents[3]

            ingestion_service_dir = (
                repo_root / "ingestion_service"
            )

        self.ingestion_service_dir = Path(
            ingestion_service_dir
        ).resolve()

        if not self.ingestion_service_dir.exists():
            raise ValueError(
                "ingestion_service directory does not exist: "
                f"{self.ingestion_service_dir}"
            )

    def retrieve(
        self,
        *,
        query: str,
        top_k: int,
        company: str | None = None,
        published_after: str | None = None,
        published_before: str | None = None,
    ) -> dict[str, Any]:

        command = [
            sys.executable,
            "-m",
            "app.retrieval.news_rag_bridge",
            "--query",
            query,
            "--top-k",
            str(top_k),
        ]

        if company is not None:
            command.extend(
                [
                    "--company",
                    company,
                ]
            )

        if published_after is not None:
            command.extend(
                [
                    "--published-after",
                    published_after,
                ]
            )

        if published_before is not None:
            command.extend(
                [
                    "--published-before",
                    published_before,
                ]
            )

        # Preserve the current environment so provider/API/database
        # configuration remains available to ingestion_service.
        process_env = os.environ.copy()

        # Force UTF-8 across the Windows subprocess boundary.
        #
        # Financial news can contain Hindi text, ₹, typographic
        # punctuation, and other Unicode characters.
        process_env["PYTHONIOENCODING"] = "utf-8"
        process_env["PYTHONUTF8"] = "1"

        try:
            completed = subprocess.run(
                command,
                cwd=self.ingestion_service_dir,
                env=process_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            raise NewsRAGBackendTimeoutError(
                "News RAG retrieval timed out after "
                f"{self.timeout_seconds} seconds."
            ) from exc

        payload = self._extract_json_response(
            completed.stdout
        )

        status = payload.get("status")

        if status != "success":
            error = payload.get("error") or {}

            error_type = error.get(
                "type",
                "RETRIEVAL_ERROR",
            )

            message = error.get(
                "message",
                "News retrieval failed.",
            )

            # Preserve validation semantics for the future
            # agent-facing tool.
            if error_type == "VALIDATION_ERROR":
                raise ValueError(message)

            raise NewsRAGBackendError(
                f"{error_type}: {message}"
            )

        data = payload.get("data")

        if not isinstance(data, dict):
            raise NewsRAGBackendResponseError(
                "News RAG bridge returned an invalid data payload."
            )

        required_fields = {
            "query",
            "source_count",
            "sources",
        }

        missing = required_fields - set(data)

        if missing:
            raise NewsRAGBackendResponseError(
                "News RAG bridge response is missing: "
                + ", ".join(sorted(missing))
            )

        if not isinstance(data["sources"], list):
            raise NewsRAGBackendResponseError(
                "News RAG bridge sources must be a list."
            )

        if data["source_count"] != len(data["sources"]):
            raise NewsRAGBackendResponseError(
                "News RAG bridge source_count does not match "
                "the number of returned sources."
            )

        return data

    @staticmethod
    def _extract_json_response(
        stdout: str,
    ) -> dict[str, Any]:
        """
        Extract the final JSON payload from bridge stdout.

        EmbeddingRouter currently writes provider-selection messages
        before the bridge JSON, so stdout cannot be parsed as one
        complete JSON document.
        """

        if not stdout or not stdout.strip():
            raise NewsRAGBackendResponseError(
                "News RAG bridge did not return a response."
            )

        lines = stdout.splitlines()

        for line in reversed(lines):
            candidate = line.strip()

            if not candidate:
                continue

            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        raise NewsRAGBackendResponseError(
            "News RAG bridge did not return a valid JSON response."
        )