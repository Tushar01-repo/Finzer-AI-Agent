from __future__ import annotations

from app.tools.news_rag import NewsRAGTool
from app.tools.news_rag_backend import IngestionNewsRAGBackend


def build_tool() -> NewsRAGTool:
    backend = IngestionNewsRAGBackend(
        timeout_seconds=60,
    )

    return NewsRAGTool(backend)


def test_apple_pay_semantic_retrieval_e2e():
    """
    Full E2E path:

    NewsRAGTool
        -> IngestionNewsRAGBackend
        -> subprocess
        -> ingestion news_rag_bridge
        -> NewsRetriever
        -> EmbeddingRouter
        -> PostgreSQL / pgvector
    """

    tool = build_tool()

    result = tool.execute(
        query="Apple Pay launch in India",
        top_k=2,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.provider == "finzer-news-rag"

    assert result.data is not None
    assert result.data.source_count > 0
    assert len(result.data.sources) > 0

    top_source = result.data.sources[0]

    assert top_source.retrieval_rank == 1
    assert "Apple Pay" in top_source.title

    assert top_source.similarity is not None
    assert top_source.embedding_provider == "openai"
    assert top_source.embedding_model == "text-embedding-3-small"
    assert top_source.embedding_dimension == 1024

    assert top_source.summary
    assert len(top_source.key_facts) > 0
    assert len(top_source.companies_mentioned) > 0

    print()
    print("Apple Pay top result:")
    print("Title:", top_source.title)
    print("Similarity:", top_source.similarity)
    print("Published:", top_source.published_at)


def test_hdfc_semantic_retrieval_e2e():
    tool = build_tool()

    result = tool.execute(
        query="HDFC Bank share price outlook and analyst target",
        top_k=2,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert result.data.source_count > 0

    top_source = result.data.sources[0]

    assert "HDFC" in top_source.title.upper()
    assert "HDFC Bank" in top_source.companies_mentioned

    assert top_source.similarity is not None

    print()
    print("HDFC top result:")
    print("Title:", top_source.title)
    print("Similarity:", top_source.similarity)


def test_visa_company_filter_e2e():
    """
    Current indexed dataset contains one article mentioning Visa:
    the Apple Pay article.
    """

    tool = build_tool()

    result = tool.execute(
        query="digital payments in India",
        company="Visa",
        top_k=5,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert result.data.company == "Visa"
    assert result.data.source_count == 1
    assert len(result.data.sources) == 1

    source = result.data.sources[0]

    assert "Visa" in source.companies_mentioned
    assert "Apple Pay" in source.title


def test_hdfc_company_filter_e2e():
    """
    Both currently indexed articles mention HDFC Bank.
    """

    tool = build_tool()

    result = tool.execute(
        query="HDFC Bank",
        company="HDFC Bank",
        top_k=5,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert result.data.company == "HDFC Bank"
    assert result.data.source_count == 2

    for source in result.data.sources:
        assert "HDFC Bank" in source.companies_mentioned


def test_publication_date_filter_e2e():
    tool = build_tool()

    result = tool.execute(
        query="Indian financial markets",
        published_after="2026-09-21T00:00:00+00:00",
        top_k=5,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert result.data.source_count == 2


def test_future_date_returns_no_results():
    tool = build_tool()

    result = tool.execute(
        query="Indian financial markets",
        published_after="2030-01-01T00:00:00+00:00",
        top_k=5,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert result.data.source_count == 0
    assert result.data.sources == []


def test_invalid_date_range():
    tool = build_tool()

    result = tool.execute(
        query="HDFC Bank",
        published_after="2026-10-01T00:00:00+00:00",
        published_before="2026-09-01T00:00:00+00:00",
    )

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None

    assert result.error.type == "VALIDATION_ERROR"
    assert result.error.retryable is False


def test_empty_query_validation():
    tool = build_tool()

    result = tool.execute(
        query="",
    )

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None

    assert result.error.type == "VALIDATION_ERROR"
    assert result.error.retryable is False


def test_empty_company_validation():
    tool = build_tool()

    result = tool.execute(
        query="financial news",
        company="   ",
    )

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None

    assert result.error.type == "VALIDATION_ERROR"
    assert result.error.retryable is False


def test_unicode_survives_subprocess_boundary():
    """
    Regression test for Windows subprocess encoding.

    The indexed HDFC article contains Hindi text in its title.
    That text must survive:

        ingestion_service
            -> JSON stdout
            -> subprocess
            -> ReAct backend
            -> Pydantic model
    """

    tool = build_tool()

    result = tool.execute(
        query="HDFC Bank share price",
        company="HDFC Bank",
        top_k=1,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None
    assert result.data.source_count == 1

    title = result.data.sources[0].title

    assert title
    assert any(
        ord(character) > 127
        for character in title
    )