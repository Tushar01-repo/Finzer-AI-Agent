from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


class DocumentElementType(str, Enum):
    """
    Physical element types detected inside a PDF.
    """

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"


class ChunkContentType(str, Enum):
    """
    Content types that can eventually become retrieval chunks.
    """

    TEXT = "text"
    TABLE = "table"


@dataclass
class DiscoveredDocument:
    """
    Metadata discovered from an external document provider
    such as SEBI.

    This object represents a document BEFORE the PDF has
    been downloaded or parsed.
    """

    source: str

    title: str

    filing_url: str | None
    pdf_url: str | None

    published_date: date | None = None

    company_name: str | None = None
    document_type: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadedDocument:
    """
    Represents a PDF after it has been downloaded and validated.
    """

    discovered_document: DiscoveredDocument

    file_path: Path
    file_name: str

    file_size_bytes: int
    file_sha256: str


@dataclass
class BoundingBox:
    """
    Position of an element on a PDF page.

    PDF coordinate system:
        x0 = left
        y0 = top
        x1 = right
        y1 = bottom
    """

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class DocumentElement:
    """
    A physical element extracted from the PDF.

    Examples:
        heading
        paragraph
        table

    At this stage we preserve the PDF's original structure.
    """

    element_id: str

    page_number: int

    element_type: DocumentElementType

    text: str

    bbox: BoundingBox | None = None

    # Layout information
    font_size: float | None = None
    font_name: str | None = None
    is_bold: bool = False

    # Structural information populated later
    section: str | None = None
    subsection: str | None = None
    heading: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedTable:
    """
    Structured representation of a table extracted from a PDF.
    """

    table_id: str

    page_number: int

    rows: list[list[str | None]]

    bbox: BoundingBox | None = None

    title: str | None = None

    section: str | None = None
    subsection: str | None = None
    heading: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """
    Complete intermediate representation of a parsed PDF.

    This is produced before chunking.
    """

    downloaded_document: DownloadedDocument

    page_count: int

    elements: list[DocumentElement] = field(default_factory=list)

    tables: list[ExtractedTable] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentChunk:
    """
    Final retrieval unit produced by the document chunker.

    Each chunk will eventually receive an embedding.
    """

    chunk_index: int

    content_type: ChunkContentType

    content: str

    page_start: int
    page_end: int

    section: str | None = None
    subsection: str | None = None
    heading: str | None = None

    token_count: int | None = None

    metadata: dict[str, Any] = field(default_factory=dict)