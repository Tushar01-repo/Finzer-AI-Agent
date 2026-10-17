from __future__ import annotations

from typing import Any, Protocol
from functools import wraps
from time import perf_counter

from app.observability.logger import get_logger
from app.observability.metrics import metrics
from app.observability.tracing import trace_span

from pydantic import BaseModel, Field


# ======================================================================
# Input
# ======================================================================


class DocumentRAGInput(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Question or retrieval query.",
    )

    document_key: str = Field(
        ...,
        min_length=1,
        description=(
            "Unique document key identifying the document "
            "that should be searched."
        ),
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    max_context_tokens: int = Field(
        default=4000,
        ge=100,
        le=16000,
    )


# ======================================================================
# Evidence source
# ======================================================================


class DocumentRAGSource(BaseModel):
    source_number: int
    retrieval_rank: int

    document_id: int | None = None
    document_key: str | None = None

    chunk_id: int
    chunk_index: int | None = None

    content_type: str | None = None

    page_start: int | None = None
    page_end: int | None = None

    section: str | None = None
    subsection: str | None = None
    heading: str | None = None

    token_count: int | None = None
    similarity: float | None = None

    content: str

    estimated_context_tokens: int


# ======================================================================
# Result
# ======================================================================


class DocumentRAGResult(BaseModel):
    query: str
    document_key: str

    context: str

    sources: list[DocumentRAGSource]

    source_count: int

    total_tokens: int


# ======================================================================
# Error
# ======================================================================


class DocumentRAGError(BaseModel):
    type: str
    message: str
    retryable: bool = False


# ======================================================================
# Response
# ======================================================================


class DocumentRAGResponse(BaseModel):
    status: str

    data: DocumentRAGResult | None = None

    error: DocumentRAGError | None = None

    provider: str = "finzer-document-rag"


# ======================================================================
# Retrieval backend contract
# ======================================================================


class DocumentRAGBackend(Protocol):
    """
    Boundary between ReAct_agent and the existing document retrieval
    implementation.

    The ReAct layer does not need to know whether retrieval is eventually
    provided through:

        - an internal Python package,
        - HTTP,
        - MCP,
        - or another service boundary.
    """

    def retrieve(
        self,
        *,
        query: str,
        document_key: str,
        top_k: int,
        max_context_tokens: int,
    ) -> dict[str, Any]:
        ...


# Observability deliberately excludes queries, document keys, and source content.
_document_log = get_logger("finzer.tools.document_rag")


def _observe_document_rag(func):
    @wraps(func)
    def wrapped(self, *, query: str, document_key: str, top_k: int = 5,
                max_context_tokens: int = 4000) -> DocumentRAGResponse:
        started = perf_counter()
        outcome = "error"
        source_count = 0
        try:
            with trace_span("document_rag_retrieve"):
                response = func(
                    self,
                    query=query,
                    document_key=document_key,
                    top_k=top_k,
                    max_context_tokens=max_context_tokens,
                )
                if response.status == "success" and response.data is not None:
                    outcome = "success"
                    source_count = len(response.data.sources)
                return response
        except Exception as exc:
            _document_log.error(
                "document_rag_exception", error_type=type(exc).__name__
            )
            raise
        finally:
            # Do not let telemetry exceptions change retrieval behavior.
            try:
                metrics.record_latency("rag", (perf_counter() - started) * 1000)
                metrics.record_operation("rag", outcome)
                _document_log.info(
                    "document_rag_completed",
                    outcome=outcome,
                    source_count=source_count,
                    empty_retrieval=(outcome == "success" and source_count == 0),
                )
            except Exception:
                pass
    return wrapped


# ======================================================================
# Document RAG Tool
# ======================================================================


class DocumentRAGTool:

    def __init__(
        self,
        backend: DocumentRAGBackend,
    ):
        self.backend = backend

    @_observe_document_rag
    def execute(
        self,
        *,
        query: str,
        document_key: str,
        top_k: int = 5,
        max_context_tokens: int = 4000,
    ) -> DocumentRAGResponse:

        # --------------------------------------------------------------
        # Input validation
        # --------------------------------------------------------------

        try:
            request = DocumentRAGInput(
                query=query,
                document_key=document_key,
                top_k=top_k,
                max_context_tokens=max_context_tokens,
            )

        except Exception as exc:
            return DocumentRAGResponse(
                status="error",
                error=DocumentRAGError(
                    type="VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                ),
            )

        # --------------------------------------------------------------
        # Retrieval
        # --------------------------------------------------------------

        try:
            raw_result = self.backend.retrieve(
                query=request.query.strip(),
                document_key=request.document_key.strip(),
                top_k=request.top_k,
                max_context_tokens=(
                    request.max_context_tokens
                ),
            )

            result = DocumentRAGResult(
                query=request.query.strip(),
                document_key=request.document_key.strip(),
                context=raw_result["context"],
                sources=raw_result["sources"],
                source_count=raw_result["source_count"],
                total_tokens=raw_result["total_tokens"],
            )

            return DocumentRAGResponse(
                status="success",
                data=result,
            )

        except ValueError as exc:
            return DocumentRAGResponse(
                status="error",
                error=DocumentRAGError(
                    type="VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                ),
            )

        except Exception as exc:
            return DocumentRAGResponse(
                status="error",
                error=DocumentRAGError(
                    type="RETRIEVAL_ERROR",
                    message=str(exc),
                    retryable=True,
                ),
            )