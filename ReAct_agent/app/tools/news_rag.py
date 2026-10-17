from __future__ import annotations

from typing import Any, Protocol
from functools import wraps
from time import perf_counter

from app.observability.logger import get_logger
from app.observability.metrics import metrics
from app.observability.tracing import trace_span

from pydantic import BaseModel, Field, ValidationError


class NewsRAGInput(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language financial news query.",
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of news sources to retrieve.",
    )

    company: str | None = Field(
        default=None,
        description=(
            "Optional exact company/entity filter based on "
            "companies_mentioned metadata."
        ),
    )

    published_after: str | None = Field(
        default=None,
        description=(
            "Optional inclusive lower publication-time bound "
            "in ISO-8601 format."
        ),
    )

    published_before: str | None = Field(
        default=None,
        description=(
            "Optional inclusive upper publication-time bound "
            "in ISO-8601 format."
        ),
    )


class NewsRAGSource(BaseModel):
    retrieval_rank: int

    article_key: str
    title: str

    url: str | None = None
    source: str | None = None
    authors: list[str] = Field(default_factory=list)

    published_at: str | None = None

    summary: str | None = None
    key_facts: list[str] = Field(default_factory=list)

    companies_mentioned: list[str] = Field(
        default_factory=list
    )

    market_impact: str | None = None

    relevance_score: float | None = None
    relevance_reason: str | None = None

    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None

    embedded_at: str | None = None

    similarity: float | None = None


class NewsRAGResult(BaseModel):
    query: str

    company: str | None = None

    published_after: str | None = None
    published_before: str | None = None

    source_count: int

    sources: list[NewsRAGSource] = Field(
        default_factory=list
    )


class NewsRAGError(BaseModel):
    type: str
    message: str
    retryable: bool = False


class NewsRAGResponse(BaseModel):
    status: str

    data: NewsRAGResult | None = None
    error: NewsRAGError | None = None

    provider: str = "finzer-news-rag"


class NewsRAGBackend(Protocol):
    def retrieve(
        self,
        *,
        query: str,
        top_k: int,
        company: str | None = None,
        published_after: str | None = None,
        published_before: str | None = None,
    ) -> dict[str, Any]:
        ...


# Observability deliberately excludes query text, company names, and article content.
_news_log = get_logger("finzer.tools.news_rag")


def _observe_news_rag(func):
    @wraps(func)
    def wrapped(self, *, query: str, top_k: int = 5,
                company: str | None = None,
                published_after: str | None = None,
                published_before: str | None = None) -> NewsRAGResponse:
        started = perf_counter()
        outcome = "error"
        source_count = 0
        try:
            with trace_span("news_rag_retrieve"):
                response = func(
                    self, query=query, top_k=top_k, company=company,
                    published_after=published_after,
                    published_before=published_before,
                )
                if response.status == "success" and response.data is not None:
                    outcome = "success"
                    source_count = len(response.data.sources)
                return response
        except Exception as exc:
            try:
                _news_log.error("news_rag_exception", error_type=type(exc).__name__)
            except Exception:
                pass
            raise
        finally:
            # Telemetry must not alter retrieval results or failure handling.
            try:
                metrics.record_latency("rag", (perf_counter() - started) * 1000)
                metrics.record_operation("rag", outcome)
                _news_log.info(
                    "news_rag_completed", outcome=outcome,
                    source_count=source_count,
                    empty_retrieval=(outcome == "success" and source_count == 0),
                )
            except Exception:
                pass
    return wrapped


class NewsRAGTool:
    """
    Agent-facing financial news RAG tool.

    Responsibilities:
        - validate agent-generated arguments
        - call the configured retrieval backend
        - normalize retrieval results
        - return structured success/error responses

    Retrieval implementation itself remains outside this class.
    """

    def __init__(
        self,
        backend: NewsRAGBackend,
    ) -> None:
        self.backend = backend

    @_observe_news_rag
    def execute(
        self,
        *,
        query: str,
        top_k: int = 5,
        company: str | None = None,
        published_after: str | None = None,
        published_before: str | None = None,
    ) -> NewsRAGResponse:

        try:
            request = NewsRAGInput(
                query=query,
                top_k=top_k,
                company=company,
                published_after=published_after,
                published_before=published_before,
            )

            normalized_query = request.query.strip()

            normalized_company = (
                request.company.strip()
                if request.company is not None
                else None
            )

            if (
                normalized_company is not None
                and not normalized_company
            ):
                raise ValueError(
                    "company cannot be empty when provided."
                )

            data = self.backend.retrieve(
                query=normalized_query,
                top_k=request.top_k,
                company=normalized_company,
                published_after=request.published_after,
                published_before=request.published_before,
            )

            result = NewsRAGResult.model_validate(
                data
            )

            return NewsRAGResponse(
                status="success",
                data=result,
                error=None,
            )

        except (ValidationError, ValueError) as exc:
            return NewsRAGResponse(
                status="error",
                data=None,
                error=NewsRAGError(
                    type="VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                ),
            )

        except Exception as exc:
            return NewsRAGResponse(
                status="error",
                data=None,
                error=NewsRAGError(
                    type="RETRIEVAL_ERROR",
                    message=str(exc),
                    retryable=True,
                ),
            )