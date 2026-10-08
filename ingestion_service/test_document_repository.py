from datetime import date
from pathlib import Path

from app.config.settings import settings
from app.document_ingestion.models import (
    ChunkContentType,
    DiscoveredDocument,
    DocumentChunk,
    DownloadedDocument,
)
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository


TEST_DOCUMENT_KEY = (
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)


def main():
    print("=" * 70)
    print("Finzer Document Repository Integration Test")
    print("=" * 70)

    # ----------------------------------------------------------
    # Database / repository
    # ----------------------------------------------------------

    database = PostgresDatabase(
        settings.DATABASE_URL
    )

    repository = DocumentRepository(
        database
    )

    # ----------------------------------------------------------
    # 1. Create discovered document
    # ----------------------------------------------------------

    discovered = DiscoveredDocument(
        source="SEBI",
        title="Finzer Repository Test - DRHP",
        filing_url=(
            "https://example.com/"
            "finzer-test-filing"
        ),
        pdf_url=(
            "https://example.com/"
            "finzer-test.pdf"
        ),
        published_date=date(
            2026,
            9,
            27,
        ),
        company_name=(
            "Finzer Repository Test Limited"
        ),
        document_type="DRHP",
        metadata={
            "integration_test": True,
        },
    )

    print("\n[1] Upserting discovered document...")

    document_id = (
        repository.upsert_discovered_document(
            document_key=TEST_DOCUMENT_KEY,
            document=discovered,
        )
    )

    print(
        f"    document_id = {document_id}"
    )

    # ----------------------------------------------------------
    # 2. Read document back
    # ----------------------------------------------------------

    print("\n[2] Reading document...")

    stored_document = repository.get_by_key(
        TEST_DOCUMENT_KEY
    )

    if stored_document is None:
        raise RuntimeError(
            "Document was not found after insert."
        )

    print(
        f"    company = "
        f"{stored_document['company_name']}"
    )
    print(
        f"    type    = "
        f"{stored_document['document_type']}"
    )
    print(
        f"    status  = "
        f"{stored_document['status']}"
    )

    assert (
        stored_document["status"]
        == "discovered"
    )

    # ----------------------------------------------------------
    # 3. Simulate successful PDF download
    # ----------------------------------------------------------

    downloaded = DownloadedDocument(
        discovered_document=discovered,
        file_path=Path(
            "downloads/finzer-test.pdf"
        ),
        file_name="finzer-test.pdf",
        file_size_bytes=123456,
        file_sha256=(
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
    )

    print(
        "\n[3] Saving download metadata..."
    )

    repository.save_downloaded_document(
        document_key=TEST_DOCUMENT_KEY,
        document=downloaded,
    )

    stored_document = repository.get_by_key(
        TEST_DOCUMENT_KEY
    )

    print(
        f"    file     = "
        f"{stored_document['file_name']}"
    )
    print(
        f"    status   = "
        f"{stored_document['status']}"
    )

    assert (
        stored_document["status"]
        == "downloaded"
    )

    # ----------------------------------------------------------
    # 4. Simulate parsing lifecycle
    # ----------------------------------------------------------

    print("\n[4] Testing status lifecycle...")

    repository.update_status(
        TEST_DOCUMENT_KEY,
        "parsing",
    )

    repository.update_status(
        TEST_DOCUMENT_KEY,
        "parsed",
    )

    stored_document = repository.get_by_key(
        TEST_DOCUMENT_KEY
    )

    print(
        f"    status = "
        f"{stored_document['status']}"
    )

    assert (
        stored_document["status"]
        == "parsed"
    )

    # ----------------------------------------------------------
    # 5. Create sample chunks
    # ----------------------------------------------------------

    chunks = [
        DocumentChunk(
            chunk_index=0,
            content_type=ChunkContentType.TEXT,
            content=(
                "Section: THE OFFER\n\n"
                "This is a sample text chunk "
                "for the Finzer document "
                "repository integration test."
            ),
            page_start=1,
            page_end=1,
            section="THE OFFER",
            subsection=None,
            heading=None,
            token_count=25,
            metadata={
                "integration_test": True,
            },
        ),
        DocumentChunk(
            chunk_index=1,
            content_type=ChunkContentType.TABLE,
            content=(
                "Section: FINANCIAL INFORMATION\n\n"
                "| Particulars | FY2026 | FY2025 |\n"
                "| --- | --- | --- |\n"
                "| Revenue | 100 | 80 |\n"
                "| Profit | 20 | 15 |"
            ),
            page_start=2,
            page_end=2,
            section="FINANCIAL INFORMATION",
            subsection=None,
            heading=None,
            token_count=40,
            metadata={
                "table_id": "test_table_1",
                "integration_test": True,
            },
        ),
    ]

    # ----------------------------------------------------------
    # 6. Persist chunks
    # ----------------------------------------------------------

    print("\n[5] Replacing chunks...")

    inserted = repository.replace_chunks(
        document_key=TEST_DOCUMENT_KEY,
        chunks=chunks,
    )

    print(
        f"    inserted = {inserted}"
    )

    assert inserted == 2

    # ----------------------------------------------------------
    # 7. Retrieve chunks
    # ----------------------------------------------------------

    print("\n[6] Reading chunks...")

    stored_chunks = (
        repository.get_chunks_for_document(
            TEST_DOCUMENT_KEY
        )
    )

    print(
        f"    chunks = {len(stored_chunks)}"
    )

    for chunk in stored_chunks:
        print(
            f"    [{chunk['chunk_index']}] "
            f"{chunk['content_type']} | "
            f"page "
            f"{chunk['page_start']}"
            f"-{chunk['page_end']} | "
            f"{chunk['token_count']} tokens"
        )

    assert len(stored_chunks) == 2

    # ----------------------------------------------------------
    # 8. Verify final status
    # ----------------------------------------------------------

    stored_document = repository.get_by_key(
        TEST_DOCUMENT_KEY
    )

    print("\n[7] Final document status:")
    print(
        f"    {stored_document['status']}"
    )

    assert (
        stored_document["status"]
        == "chunked"
    )

    # ----------------------------------------------------------
    # 9. Verify embedding input
    # ----------------------------------------------------------

    first_chunk_id = (
        stored_chunks[0]["chunk_id"]
    )

    print(
        "\n[8] Checking embedding input..."
    )

    embedding_input = (
        repository.get_embedding_input(
            first_chunk_id,
            provider="test-provider",
            model="test-model",
        )
    )

    if embedding_input is None:
        raise RuntimeError(
            "Embedding input not found."
        )

    print(
        f"    chunk_id      = "
        f"{embedding_input['chunk_id']}"
    )
    print(
        f"    content_type  = "
        f"{embedding_input['content_type']}"
    )
    print(
        f"    has_embedding = "
        f"{embedding_input['has_embedding']}"
    )

    assert (
        embedding_input["has_embedding"]
        is False
    )

    print("\n" + "=" * 70)
    print(
        "DOCUMENT REPOSITORY INTEGRATION TEST PASSED"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()