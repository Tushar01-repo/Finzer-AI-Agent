from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class DocumentRAGBackendError(RuntimeError):
    """Base error for document RAG backend failures."""


class DocumentRAGBackendTimeoutError(
    DocumentRAGBackendError
):
    """Raised when the retrieval subprocess times out."""


class DocumentRAGBackendResponseError(
    DocumentRAGBackendError
):
    """Raised when the retrieval bridge returns invalid output."""


class IngestionDocumentRAGBackend:
    """
    Adapter from ReAct_agent to the existing ingestion-service
    document retrieval pipeline.

    Current local implementation:
        ReAct_agent
            -> subprocess
            -> ingestion_service
            -> document_rag_bridge
            -> DocumentRetriever
            -> DocumentContextBuilder

    The DocumentRAGTool itself remains independent of this transport.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        ingestion_service_dir: str | Path | None = None,
    ):
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        self.timeout_seconds = timeout_seconds

        # ReAct_agent/app/tools/document_rag_backend.py
        #
        # parents[0] -> tools
        # parents[1] -> app
        # parents[2] -> ReAct_agent
        # parents[3] -> Finzer-AI-Agent

        repo_root = Path(
            __file__
        ).resolve().parents[3]

        self.ingestion_service_dir = Path(
            ingestion_service_dir
            or repo_root / "ingestion_service"
        ).resolve()

        if not self.ingestion_service_dir.exists():
            raise ValueError(
                "ingestion_service directory does not exist: "
                f"{self.ingestion_service_dir}"
            )

    @staticmethod
    def _extract_json_response(
        stdout: str,
    ) -> dict[str, Any]:
        """
        The embedding router currently prints provider diagnostics
        before the bridge JSON.

        Therefore we search stdout from bottom to top and parse the
        final valid JSON object.
        """

        lines = [
            line.strip()
            for line in stdout.splitlines()
            if line.strip()
        ]

        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        raise DocumentRAGBackendResponseError(
            "Document RAG bridge did not return "
            "a valid JSON response."
        )

    def retrieve(
        self,
        *,
        query: str,
        document_key: str,
        top_k: int,
        max_context_tokens: int,
    ) -> dict[str, Any]:

        command = [
            sys.executable,
            "-m",
            "app.retrieval.document_rag_bridge",
            "--query",
            query,
            "--document-key",
            document_key,
            "--top-k",
            str(top_k),
            "--max-context-tokens",
            str(max_context_tokens),
        ]

        # Explicitly pass the current environment.
        #
        # This preserves API keys / provider configuration available
        # to the current Finzer process without hardcoding secrets.

        process_env = os.environ.copy()
        # Force UTF-8 for the child process.
        # Required because retrieved financial documents can contain
        # Unicode characters such as the Indian Rupee symbol (₹).
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
            raise DocumentRAGBackendTimeoutError(
                "Document RAG retrieval timed out after "
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
                "Document retrieval failed.",
            )

            raise DocumentRAGBackendError(
                f"{error_type}: {message}"
            )

        data = payload.get("data")

        if not isinstance(data, dict):
            raise DocumentRAGBackendResponseError(
                "Document RAG bridge returned "
                "an invalid data payload."
            )

        required_fields = {
            "context",
            "sources",
            "source_count",
            "total_tokens",
        }

        missing = (
            required_fields
            - set(data)
        )

        if missing:
            raise DocumentRAGBackendResponseError(
                "Document RAG bridge response is missing: "
                + ", ".join(sorted(missing))
            )

        return data