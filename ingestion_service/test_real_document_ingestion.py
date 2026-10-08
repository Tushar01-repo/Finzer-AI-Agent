from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from app.config.settings import settings
from app.document_ingestion.models import (
    DiscoveredDocument,
    DownloadedDocument,
)
from app.document_ingestion.service import (
    DocumentIngestionService,
)
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import (
    DocumentRepository,
)


PDF_PATH = Path(
    "data/documents/raw/HitechFlowSolutionsDAP_p.pdf"
)


def sha256_file(path: Path) -> str:
    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def main():
    print("=" * 70)
    print("Finzer Real Document -> PostgreSQL Test")
    print("=" * 70)

    # ----------------------------------------------------------
    # 1. Validate local PDF
    # ----------------------------------------------------------

    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH.resolve()}"
        )

    file_size = PDF_PATH.stat().st_size
    file_hash = sha256_file(PDF_PATH)

    print("\n[1] Local PDF")

    print(
        f"    path   = {PDF_PATH}"
    )

    print(
        f"    size   = {file_size:,} bytes"
    )

    print(
        f"    sha256 = {file_hash}"
    )

    # ----------------------------------------------------------
    # 2. Build discovery model
    #
    # We use the real SEBI URL associated with this document
    # identity when available in the project flow.
    #
    # The actual PDF is NOT downloaded again in this test.
    # ----------------------------------------------------------

    discovered = DiscoveredDocument(
        source="SEBI",
        title=(
            "Hi-Tech Flow Solutions Limited - DRHP"
        ),
        filing_url=(
            "https://www.sebi.gov.in/"
            "filings/public-issues/"
        ),
        pdf_url=(
            "https://www.sebi.gov.in/"
            "sebi_data/attachdocs/"
            "HitechFlowSolutionsDAP_p.pdf"
        ),
        published_date=None,
        company_name=(
            "Hi-Tech Flow Solutions Limited"
        ),
        document_type="DRHP",
        metadata={
            "integration_test": True,
            "local_pdf": str(PDF_PATH),
            "note": (
                "Real local SEBI PDF used for "
                "document ingestion integration test."
            ),
        },
    )

    # ----------------------------------------------------------
    # 3. Database
    # ----------------------------------------------------------

    print("\n[2] Connecting repository...")

    database = PostgresDatabase(
        settings.DATABASE_URL
    )

    repository = DocumentRepository(
        database
    )

    service = DocumentIngestionService(
        repository=repository
    )

    # ----------------------------------------------------------
    # 4. Build deterministic document key
    # ----------------------------------------------------------

    document_key = (
        service.build_document_key(
            discovered
        )
    )

    print(
        f"    document_key = {document_key}"
    )

    # ----------------------------------------------------------
    # 5. Upsert discovery row
    # ----------------------------------------------------------

    print(
        "\n[3] Persisting document discovery..."
    )

    document_id = (
        repository.upsert_discovered_document(
            document_key=document_key,
            document=discovered,
        )
    )

    print(
        f"    document_id = {document_id}"
    )

    # ----------------------------------------------------------
    # 6. Construct DownloadedDocument from existing local PDF
    # ----------------------------------------------------------

    downloaded = DownloadedDocument(
        discovered_document=discovered,
        file_path=PDF_PATH,
        file_name=PDF_PATH.name,
        file_size_bytes=file_size,
        file_sha256=file_hash,
    )

    # ----------------------------------------------------------
    # 7. Run real pipeline
    # ----------------------------------------------------------

    print(
        "\n[4] Running document ingestion pipeline..."
    )

    result = service.ingest_downloaded(
        document_key=document_key,
        downloaded=downloaded,
    )

    # ----------------------------------------------------------
    # 8. Pipeline statistics
    # ----------------------------------------------------------

    stats = service.summarize_chunks(
        result.chunks
    )

    print("\n[5] Pipeline result")

    print(
        f"    document_id       = "
        f"{result.document_id}"
    )

    print(
        f"    pages             = "
        f"{result.page_count}"
    )

    print(
        f"    elements          = "
        f"{result.element_count}"
    )

    print(
        f"    table candidates  = "
        f"{result.table_candidate_count}"
    )

    print(
        f"    total chunks      = "
        f"{stats['total']}"
    )

    print(
        f"    text chunks       = "
        f"{stats['text']}"
    )

    print(
        f"    table chunks      = "
        f"{stats['table']}"
    )

    print(
        f"    max tokens        = "
        f"{stats['max_tokens']}"
    )

    # ----------------------------------------------------------
    # 9. Verify database document
    # ----------------------------------------------------------

    print(
        "\n[6] Verifying document row..."
    )

    stored_document = repository.get_by_key(
        document_key
    )

    if stored_document is None:
        raise RuntimeError(
            "Document not found in PostgreSQL."
        )

    print(
        f"    status      = "
        f"{stored_document['status']}"
    )

    print(
        f"    file_name   = "
        f"{stored_document['file_name']}"
    )

    print(
        f"    file_sha256 = "
        f"{stored_document['file_sha256']}"
    )

    assert (
        stored_document["status"]
        == "chunked"
    )

    assert (
        stored_document["file_sha256"]
        == file_hash
    )

    # ----------------------------------------------------------
    # 10. Verify persisted chunks
    # ----------------------------------------------------------

    print(
        "\n[7] Verifying persisted chunks..."
    )

    stored_chunks = (
        repository.get_chunks_for_document(
            document_key
        )
    )

    print(
        f"    stored chunks = "
        f"{len(stored_chunks)}"
    )

    if len(stored_chunks) != len(
        result.chunks
    ):
        raise RuntimeError(
            "Generated/stored chunk count mismatch: "
            f"generated={len(result.chunks)}, "
            f"stored={len(stored_chunks)}"
        )

    if not stored_chunks:
        raise RuntimeError(
            "No chunks were persisted."
        )

    # ----------------------------------------------------------
    # 11. Print persisted chunk summary
    # ----------------------------------------------------------

    print(
        "\n[8] Persisted chunk summary"
    )

    for chunk in stored_chunks:

        section = (
            chunk["section"]
            or "-"
        )

        subsection = (
            chunk["subsection"]
            or "-"
        )

        print(
            f"    [{chunk['chunk_index']:02d}] "
            f"{chunk['content_type']:<5} | "
            f"p{chunk['page_start']}"
            f"-{chunk['page_end']} | "
            f"{chunk['token_count']:>4} tokens | "
            f"section={section} | "
            f"subsection={subsection}"
        )

    # ----------------------------------------------------------
    # 12. Safety assertions
    # ----------------------------------------------------------

    print(
        "\n[9] Running quality checks..."
    )

    over_limit = [
        chunk
        for chunk in stored_chunks
        if chunk["token_count"] > 1000
    ]

    if over_limit:
        raise RuntimeError(
            f"{len(over_limit)} chunks exceed "
            "the 1000-token maximum."
        )

    text_count = sum(
        1
        for chunk in stored_chunks
        if chunk["content_type"] == "text"
    )

    table_count = sum(
        1
        for chunk in stored_chunks
        if chunk["content_type"] == "table"
    )

    print(
        f"    TEXT chunks  = {text_count}"
    )

    print(
        f"    TABLE chunks = {table_count}"
    )

    print(
        f"    >1000 tokens = "
        f"{len(over_limit)}"
    )

    # ----------------------------------------------------------
    # 13. Verify embedding handoff
    # ----------------------------------------------------------

    print(
        "\n[10] Checking embedding handoff..."
    )

    first_chunk_id = (
        stored_chunks[0]["chunk_id"]
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
            "Could not retrieve embedding input."
        )

    print(
        f"    chunk_id      = "
        f"{embedding_input['chunk_id']}"
    )

    print(
        f"    chunk_index   = "
        f"{embedding_input['chunk_index']}"
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

    # ----------------------------------------------------------
    # Complete
    # ----------------------------------------------------------

    print("\n" + "=" * 70)

    print(
        "REAL DOCUMENT -> POSTGRESQL TEST PASSED"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()