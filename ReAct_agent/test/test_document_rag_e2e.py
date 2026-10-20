from __future__ import annotations

from app.tools.document_rag import DocumentRAGTool
from app.tools.document_rag_backend import IngestionDocumentRAGBackend


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)


def build_tool() -> DocumentRAGTool:
    backend = IngestionDocumentRAGBackend(
        timeout_seconds=60,
    )

    return DocumentRAGTool(backend)


def test_document_rag_objects_of_offer_e2e():
    """
    Full integration test:

    ReAct DocumentRAGTool
        -> IngestionDocumentRAGBackend
        -> subprocess
        -> ingestion document_rag_bridge
        -> DocumentRetriever
        -> embedding provider
        -> PostgreSQL / pgvector
        -> DocumentContextBuilder
    """

    tool = build_tool()

    result = tool.execute(
        query="What are the objects of the IPO?",
        document_key=DOCUMENT_KEY,
        top_k=5,
        max_context_tokens=4000,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.provider == "finzer-document-rag"

    assert result.data is not None

    # Retrieval should return evidence.
    assert result.data.source_count > 0
    assert len(result.data.sources) > 0

    # Context should actually be constructed.
    assert result.data.context.strip()
    assert result.data.total_tokens > 0
    assert result.data.total_tokens <= 4000

    top_source = result.data.sources[0]

    # This query should retrieve the known IPO section first.
    assert top_source.retrieval_rank == 1
    assert top_source.section == "4. Objects of the Offer"

    assert top_source.document_key == DOCUMENT_KEY
    assert top_source.content.strip()

    # Basic evidence metadata.
    assert top_source.chunk_id is not None
    assert top_source.page_start is not None
    assert top_source.page_end is not None
    assert top_source.similarity is not None

    # Important Windows/Unicode regression check.
    #
    # The retrieved section contains Indian currency values.
    # This ensures Unicode successfully crosses:
    #
    # ingestion subprocess -> stdout JSON -> ReAct backend.
    assert "₹" in result.data.context


def test_document_rag_respects_top_k():
    tool = build_tool()

    result = tool.execute(
        query="What are the objects of the IPO?",
        document_key=DOCUMENT_KEY,
        top_k=2,
        max_context_tokens=4000,
    )

    assert result.status == "success"
    assert result.error is None
    assert result.data is not None

    assert 1 <= result.data.source_count <= 2
    assert len(result.data.sources) <= 2


def test_document_rag_empty_query_validation():
    tool = build_tool()

    result = tool.execute(
        query="",
        document_key=DOCUMENT_KEY,
        top_k=5,
        max_context_tokens=4000,
    )

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None

    assert result.error.type == "VALIDATION_ERROR"
    assert result.error.retryable is False


def test_document_rag_empty_document_key_validation():
    tool = build_tool()

    result = tool.execute(
        query="What are the objects of the IPO?",
        document_key="",
        top_k=5,
        max_context_tokens=4000,
    )

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None

    assert result.error.type == "VALIDATION_ERROR"
    assert result.error.retryable is False