from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.document_ingestion.chunker import DocumentChunker
from app.document_ingestion.downloader import PDFDownloader
from app.document_ingestion.models import (
    DiscoveredDocument,
    DocumentChunk,
    DownloadedDocument,
    ParsedDocument,
)
from app.document_ingestion.parser import PDFParser
from app.document_ingestion.structure.hierarchy_assigner import (
    DocumentHierarchyAssigner,
)
from app.document_ingestion.structure.structure_detector import (
    StructureDetector,
)
from app.document_ingestion.structure.style_profiler import (
    DocumentStyleProfiler,
)
from app.document_ingestion.structure.toc_detector import (
    TOCDetector,
)
from app.document_ingestion.table_extractor import (
    PDFTableExtractor,
)
from app.repositories.document_repository import (
    DocumentRepository,
)


@dataclass
class DocumentIngestionResult:
    """
    Result returned after one document has completed the
    synchronous ingestion pipeline.
    """

    document_id: int
    document_key: str

    downloaded_document: DownloadedDocument
    parsed_document: ParsedDocument

    chunks: list[DocumentChunk]

    page_count: int
    element_count: int
    table_candidate_count: int
    chunk_count: int


class DocumentIngestionService:
    """
    Orchestrates the synchronous document ingestion pipeline.

    Pipeline:

        DiscoveredDocument
                ↓
        document deduplication key
                ↓
        PostgreSQL document upsert
                ↓
        PDF download
                ↓
        PyMuPDF text/layout parsing
                ↓
        pdfplumber table extraction
                ↓
        style profiling
                ↓
        TOC detection
                ↓
        structure detection
                ↓
        hierarchy assignment
                ↓
        section-aware chunking
                ↓
        PostgreSQL chunk persistence

    This service deliberately does NOT:
        - publish RabbitMQ messages
        - generate embeddings
        - perform vector retrieval

    Those are asynchronous/downstream responsibilities.
    """

    def __init__(
        self,
        *,
        repository: DocumentRepository,
        download_dir: str | Path = "data/documents/raw",
        downloader: PDFDownloader | None = None,
        parser: PDFParser | None = None,
        table_extractor: PDFTableExtractor | None = None,
        style_profiler: DocumentStyleProfiler | None = None,
        toc_detector: TOCDetector | None = None,
        structure_detector: StructureDetector | None = None,
        hierarchy_assigner: DocumentHierarchyAssigner | None = None,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self.repository = repository

        self.downloader = (
            downloader
            if downloader is not None
            else PDFDownloader(
                download_dir=download_dir
            )
        )

        self.parser = (
            parser
            if parser is not None
            else PDFParser()
        )

        self.table_extractor = (
            table_extractor
            if table_extractor is not None
            else PDFTableExtractor()
        )

        self.style_profiler = (
            style_profiler
            if style_profiler is not None
            else DocumentStyleProfiler()
        )

        self.toc_detector = (
            toc_detector
            if toc_detector is not None
            else TOCDetector()
        )

        self.structure_detector = (
            structure_detector
            if structure_detector is not None
            else StructureDetector()
        )

        self.hierarchy_assigner = (
            hierarchy_assigner
            if hierarchy_assigner is not None
            else DocumentHierarchyAssigner()
        )

        self.chunker = (
            chunker
            if chunker is not None
            else DocumentChunker()
        )

    # ============================================================
    # Public API
    # ============================================================

    def ingest(
        self,
        document: DiscoveredDocument,
    ) -> DocumentIngestionResult:
        """
        Run the complete synchronous ingestion pipeline for one
        discovered document.
        """

        if not document.pdf_url:
            raise ValueError(
                "Cannot ingest document without pdf_url. "
                f"title={document.title!r}"
            )

        document_key = self.build_document_key(
            document
        )

        print("=" * 70)
        print("Finzer Document Ingestion")
        print("=" * 70)

        print(f"\nTitle: {document.title}")
        print(f"Source: {document.source}")
        print(f"PDF: {document.pdf_url}")
        print(f"Document key: {document_key}")

        # --------------------------------------------------------
        # 1. Persist discovery metadata
        # --------------------------------------------------------

        print("\n[1] Persisting discovery metadata...")

        document_id = (
            self.repository.upsert_discovered_document(
                document_key=document_key,
                document=document,
            )
        )

        print(
            f"    document_id = {document_id}"
        )

        try:
            # ----------------------------------------------------
            # 2. Download
            # ----------------------------------------------------

            print("\n[2] Downloading PDF...")

            self.repository.update_status(
                document_key,
                "downloading",
            )

            downloaded = (
                self.downloader.download(
                    document
                )
            )

            self.repository.save_downloaded_document(
                document_key=document_key,
                document=downloaded,
            )

            print(
                f"    file = {downloaded.file_name}"
            )
            print(
                f"    size = "
                f"{downloaded.file_size_bytes:,} bytes"
            )
            print(
                f"    sha256 = "
                f"{downloaded.file_sha256}"
            )

            # ----------------------------------------------------
            # 3. Parse text/layout
            # ----------------------------------------------------

            print("\n[3] Parsing PDF...")

            self.repository.update_status(
                document_key,
                "parsing",
            )

            parsed = self.parser.parse(
                downloaded
            )

            print(
                f"    pages = {parsed.page_count}"
            )
            print(
                f"    text elements = "
                f"{len(parsed.elements)}"
            )

            # ----------------------------------------------------
            # 4. Extract table candidates
            # ----------------------------------------------------

            print(
                "\n[4] Extracting table candidates..."
            )

            tables = (
                self.table_extractor.extract(
                    downloaded
                )
            )

            parsed.tables = tables

            print(
                f"    table candidates = "
                f"{len(tables)}"
            )

            # ----------------------------------------------------
            # 5. Style profile
            # ----------------------------------------------------

            print(
                "\n[5] Profiling document styles..."
            )

            style_profile = (
                self.style_profiler.profile(
                    parsed
                )
            )

            print(
                f"    body font size = "
                f"{style_profile.body_font_size}"
            )

            print(
                f"    dominant font = "
                f"{style_profile.dominant_font_name}"
            )

            # ----------------------------------------------------
            # 6. TOC detection
            # ----------------------------------------------------

            print(
                "\n[6] Detecting table of contents..."
            )

            toc_result = (
                self.toc_detector.detect(
                    parsed
                )
            )

            print(
                f"    TOC found = "
                f"{toc_result.found}"
            )

            print(
                f"    TOC entries = "
                f"{len(toc_result.entries)}"
            )

            # ----------------------------------------------------
            # 7. Structure detection
            # ----------------------------------------------------

            print(
                "\n[7] Detecting document structure..."
            )

            parsed = (
                self.structure_detector.detect(
                    parsed,
                    style_profile=style_profile,
                    tables=tables,
                    toc=toc_result,
                )
            )

            heading_count = sum(
                1
                for element in parsed.elements
                if element.element_type.value
                == "heading"
            )

            print(
                f"    headings detected = "
                f"{heading_count}"
            )

            # ----------------------------------------------------
            # 8. Hierarchy assignment
            # ----------------------------------------------------

            print(
                "\n[8] Assigning hierarchy..."
            )

            parsed = (
                self.hierarchy_assigner.assign(
                    parsed
                )
            )

            print(
                "    hierarchy assignment complete"
            )

            # ----------------------------------------------------
            # 9. Mark parsed
            # ----------------------------------------------------

            self.repository.update_status(
                document_key,
                "parsed",
            )

            # ----------------------------------------------------
            # 10. Chunk
            # ----------------------------------------------------

            print("\n[9] Building chunks...")

            chunks = self.chunker.chunk(
                parsed
            )

            text_chunks = sum(
                1
                for chunk in chunks
                if chunk.content_type.value
                == "text"
            )

            table_chunks = sum(
                1
                for chunk in chunks
                if chunk.content_type.value
                == "table"
            )

            max_tokens = max(
                (
                    chunk.token_count
                    for chunk in chunks
                ),
                default=0,
            )

            print(
                f"    total chunks = "
                f"{len(chunks)}"
            )

            print(
                f"    text chunks = "
                f"{text_chunks}"
            )

            print(
                f"    table chunks = "
                f"{table_chunks}"
            )

            print(
                f"    max tokens = "
                f"{max_tokens}"
            )

            # ----------------------------------------------------
            # 11. Persist chunks
            # ----------------------------------------------------

            print(
                "\n[10] Persisting chunks..."
            )

            inserted = (
                self.repository.replace_chunks(
                    document_key=document_key,
                    chunks=chunks,
                )
            )

            if inserted != len(chunks):
                raise RuntimeError(
                    "Chunk persistence count mismatch. "
                    f"generated={len(chunks)}, "
                    f"inserted={inserted}"
                )

            print(
                f"    inserted = {inserted}"
            )

            # replace_chunks() changes status to chunked.

            stored = (
                self.repository.get_by_key(
                    document_key
                )
            )

            if stored is None:
                raise RuntimeError(
                    "Document disappeared after "
                    "chunk persistence."
                )

            if stored["status"] != "chunked":
                raise RuntimeError(
                    "Unexpected final document status: "
                    f"{stored['status']}"
                )

            # ----------------------------------------------------
            # Complete
            # ----------------------------------------------------

            print("\n" + "=" * 70)
            print(
                "DOCUMENT INGESTION COMPLETED"
            )
            print("=" * 70)

            print(
                f"Document ID: {document_id}"
            )
            print(
                f"Pages: {parsed.page_count}"
            )
            print(
                f"Elements: {len(parsed.elements)}"
            )
            print(
                f"Table candidates: {len(tables)}"
            )
            print(
                f"Chunks: {len(chunks)}"
            )
            print(
                "Status: chunked"
            )

            return DocumentIngestionResult(
                document_id=document_id,
                document_key=document_key,
                downloaded_document=downloaded,
                parsed_document=parsed,
                chunks=list(chunks),
                page_count=parsed.page_count,
                element_count=len(
                    parsed.elements
                ),
                table_candidate_count=len(
                    tables
                ),
                chunk_count=len(
                    chunks
                ),
            )

        except Exception:
            # ----------------------------------------------------
            # Best-effort failure status.
            #
            # Do not hide the original exception if PostgreSQL
            # itself is unavailable.
            # ----------------------------------------------------

            try:
                self.repository.update_status(
                    document_key,
                    "failed",
                )
            except Exception:
                pass

            raise

    # ============================================================
    # Existing/local PDF ingestion
    # ============================================================

    def ingest_downloaded(
        self,
        *,
        document_key: str,
        downloaded: DownloadedDocument,
    ) -> DocumentIngestionResult:
        """
        Run parsing -> structure -> chunking -> persistence for a
        PDF that already exists locally.

        This is particularly useful for development and for the
        real SEBI PDF already present under data/documents/raw.

        The corresponding document row must already exist.
        """

        document = (
            downloaded.discovered_document
        )

        document_id = (
            self.repository.get_document_id(
                document_key
            )
        )

        if document_id is None:
            document_id = (
                self.repository.upsert_discovered_document(
                    document_key=document_key,
                    document=document,
                )
            )

        try:
            self.repository.save_downloaded_document(
                document_key=document_key,
                document=downloaded,
            )

            self.repository.update_status(
                document_key,
                "parsing",
            )

            parsed = self.parser.parse(
                downloaded
            )

            tables = (
                self.table_extractor.extract(
                    downloaded
                )
            )

            parsed.tables = tables

            style_profile = (
                self.style_profiler.profile(
                    parsed
                )
            )

            toc_result = (
                self.toc_detector.detect(
                    parsed
                )
            )

            parsed = (
                self.structure_detector.detect(
                    parsed,
                    style_profile=style_profile,
                    tables=tables,
                    toc=toc_result,
                )
            )

            parsed = (
                self.hierarchy_assigner.assign(
                    parsed
                )
            )

            self.repository.update_status(
                document_key,
                "parsed",
            )

            chunks = self.chunker.chunk(
                parsed
            )

            self.repository.replace_chunks(
                document_key=document_key,
                chunks=chunks,
            )

            return DocumentIngestionResult(
                document_id=document_id,
                document_key=document_key,
                downloaded_document=downloaded,
                parsed_document=parsed,
                chunks=list(chunks),
                page_count=parsed.page_count,
                element_count=len(
                    parsed.elements
                ),
                table_candidate_count=len(
                    tables
                ),
                chunk_count=len(
                    chunks
                ),
            )

        except Exception:
            try:
                self.repository.update_status(
                    document_key,
                    "failed",
                )
            except Exception:
                pass

            raise

    # ============================================================
    # Document key
    # ============================================================

    @staticmethod
    def build_document_key(
        document: DiscoveredDocument,
    ) -> str:
        """
        Generate the deterministic discovery-level document key.

        Current identity:

            SHA256(
                normalized source
                +
                normalized PDF URL
            )

        The downloaded PDF additionally receives file_sha256,
        which represents the actual file contents.
        """

        if not document.pdf_url:
            raise ValueError(
                "Cannot build document_key "
                "without pdf_url."
            )

        source = (
            document.source
            .strip()
            .lower()
        )

        pdf_url = (
            document.pdf_url
            .strip()
        )

        identity = (
            f"{source}|{pdf_url}"
        )

        return hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()

    # ============================================================
    # Convenience
    # ============================================================

    @staticmethod
    def summarize_chunks(
        chunks: Sequence[DocumentChunk],
    ) -> dict[str, int]:
        """
        Return basic chunk statistics useful for logs/tests.
        """

        text_chunks = sum(
            1
            for chunk in chunks
            if chunk.content_type.value == "text"
        )

        table_chunks = sum(
            1
            for chunk in chunks
            if chunk.content_type.value == "table"
        )

        max_tokens = max(
            (
                chunk.token_count
                for chunk in chunks
            ),
            default=0,
        )

        return {
            "total": len(chunks),
            "text": text_chunks,
            "table": table_chunks,
            "max_tokens": max_tokens,
        }