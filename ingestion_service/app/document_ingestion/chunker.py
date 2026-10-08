from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import tiktoken

from app.document_ingestion.models import (
    BoundingBox,
    ChunkContentType,
    DocumentChunk,
    DocumentElement,
    DocumentElementType,
    ExtractedTable,
    ParsedDocument,
)
from app.document_ingestion.tables.table_validator import TableValidator


@dataclass
class ChunkerConfig:
    """
    Configuration for document chunking.

    target_tokens:
        Preferred chunk size. We try to create chunks around this size,
        but hierarchy boundaries are more important than hitting the
        target exactly.

    max_tokens:
        Hard maximum token count for a chunk.

    overlap_tokens:
        Token overlap used when a single text element is too large and
        must be split.

    encoding_name:
        tiktoken encoding used for token counting.
    """

    target_tokens: int = 800
    max_tokens: int = 1000
    overlap_tokens: int = 100
    encoding_name: str = "cl100k_base"


class DocumentChunker:
    """
    Convert a structured ParsedDocument into retrieval-ready chunks.

    Design principles
    -----------------
    1. TEXT and TABLE chunks are kept separate.

    2. Section/subsection/heading boundaries are stronger than token
       targets.

    3. PyMuPDF text remains the authoritative text representation.

       We DO NOT remove text simply because it overlaps a pdfplumber
       table candidate.

       This is intentional because pdfplumber can detect only part of a
       table while PyMuPDF still extracts important values outside the
       detected table region.

    4. pdfplumber tables are supplementary structured representations.

       Only candidates accepted by TableValidator are converted into
       TABLE chunks.

    5. Large tables are split by rows while repeating the header.

    6. Every chunk carries page and hierarchy metadata.
    """

    def __init__(
        self,
        config: ChunkerConfig | None = None,
        table_validator: TableValidator | None = None,
    ) -> None:
        self.config = config or ChunkerConfig()
        self.table_validator = table_validator or TableValidator()

        self._validate_config()

        self.encoding = tiktoken.get_encoding(
            self.config.encoding_name
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(
        self,
        document: ParsedDocument,
    ) -> list[DocumentChunk]:
        """
        Build TEXT and TABLE chunks for a parsed document.
        """

        all_tables = list(document.tables or [])

        # --------------------------------------------------------------
        # Validate pdfplumber table candidates.
        #
        # IMPORTANT:
        # Invalid table candidates are NOT used to suppress PyMuPDF text.
        # PyMuPDF text always remains available to the text chunking path.
        # --------------------------------------------------------------

        valid_tables = self.table_validator.filter_valid_tables(
            all_tables
        )

        # Give validated tables hierarchy context before creating chunks.
        self._assign_table_hierarchy(
            document=document,
            tables=valid_tables,
        )

        text_chunks = self._build_text_chunks(
            document=document,
        )

        table_chunks = self._build_table_chunks(
            tables=valid_tables,
        )

        chunks = text_chunks + table_chunks

        # Stable ordering:
        #
        # page
        # source order
        # content type
        #
        # This is primarily for deterministic chunk IDs / persistence.
        chunks.sort(
            key=lambda chunk: (
                chunk.page_start,
                chunk.metadata.get(
                    "source_order",
                    10**9,
                ),
                self._content_type_order(
                    chunk.content_type
                ),
                chunk.page_end,
            )
        )

        # Reassign sequential chunk indices after TEXT/TABLE merge.
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index

        return chunks

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        if self.config.target_tokens <= 0:
            raise ValueError(
                "target_tokens must be greater than 0"
            )

        if self.config.max_tokens <= 0:
            raise ValueError(
                "max_tokens must be greater than 0"
            )

        if (
            self.config.target_tokens
            > self.config.max_tokens
        ):
            raise ValueError(
                "target_tokens cannot exceed max_tokens"
            )

        if self.config.overlap_tokens < 0:
            raise ValueError(
                "overlap_tokens cannot be negative"
            )

        if (
            self.config.overlap_tokens
            >= self.config.max_tokens
        ):
            raise ValueError(
                "overlap_tokens must be smaller than "
                "max_tokens"
            )

    # ------------------------------------------------------------------
    # TEXT chunking
    # ------------------------------------------------------------------

    def _build_text_chunks(
        self,
        document: ParsedDocument,
    ) -> list[DocumentChunk]:
        """
        Build hierarchy-aware TEXT chunks.

        NOTE:
        We intentionally do NOT suppress elements that overlap tables.

        PyMuPDF text is currently our safest complete representation of
        the document. pdfplumber tables are supplementary.
        """

        elements: list[DocumentElement] = []

        for element in document.elements:
            if not element.text:
                continue

            if not element.text.strip():
                continue

            # TABLE elements, if ever explicitly produced by another
            # parser stage, are handled separately.
            if (
                element.element_type
                == DocumentElementType.TABLE
            ):
                continue

            # Heading elements are represented through chunk hierarchy
            # prefixes rather than duplicated as body text.
            if (
                element.element_type
                == DocumentElementType.HEADING
            ):
                continue

            elements.append(element)

        groups = self._group_elements_by_hierarchy(
            elements
        )

        chunks: list[DocumentChunk] = []

        source_order = 0

        for group_index, group in enumerate(groups):
            group_chunks = self._chunk_text_group(
                group=group,
                group_index=group_index,
                source_order_start=source_order,
            )

            chunks.extend(group_chunks)
            source_order += len(group_chunks)

        return chunks

    def _group_elements_by_hierarchy(
        self,
        elements: list[DocumentElement],
    ) -> list[list[DocumentElement]]:
        """
        Group consecutive elements with identical hierarchy.

        We deliberately do not merge across hierarchy boundaries even if
        the resulting chunks are small.
        """

        groups: list[list[DocumentElement]] = []

        current_group: list[DocumentElement] = []
        current_key: tuple[
            str | None,
            str | None,
            str | None,
        ] | None = None

        for element in elements:
            key = (
                element.section,
                element.subsection,
                element.heading,
            )

            if current_key is None:
                current_key = key
                current_group = [element]
                continue

            if key == current_key:
                current_group.append(element)
                continue

            if current_group:
                groups.append(current_group)

            current_group = [element]
            current_key = key

        if current_group:
            groups.append(current_group)

        return groups

    def _chunk_text_group(
        self,
        group: list[DocumentElement],
        group_index: int,
        source_order_start: int,
    ) -> list[DocumentChunk]:
        if not group:
            return []

        section = group[0].section
        subsection = group[0].subsection
        heading = group[0].heading

        pieces: list[dict] = []

        # --------------------------------------------------------------
        # Convert elements into pieces.
        #
        # Normally one element = one piece.
        # Oversized elements are split token-wise.
        # --------------------------------------------------------------

        for element in group:
            text = self._normalize_text(
                element.text
            )

            if not text:
                continue

            token_count = self._count_tokens(text)

            if token_count <= self.config.max_tokens:
                pieces.append(
                    {
                        "text": text,
                        "page_start": element.page_number,
                        "page_end": element.page_number,
                        "element_ids": [
                            element.element_id
                        ],
                        "source_element_id": (
                            element.element_id
                        ),
                        "split_part": None,
                    }
                )
                continue

            split_texts = self._split_oversized_text(
                text
            )

            for split_index, split_text in enumerate(
                split_texts
            ):
                pieces.append(
                    {
                        "text": split_text,
                        "page_start": element.page_number,
                        "page_end": element.page_number,
                        "element_ids": [
                            element.element_id
                        ],
                        "source_element_id": (
                            element.element_id
                        ),
                        "split_part": split_index,
                    }
                )

        if not pieces:
            return []

        # --------------------------------------------------------------
        # Merge pieces up to target/max token limits.
        # --------------------------------------------------------------

        chunks: list[DocumentChunk] = []

        current_pieces: list[dict] = []
        current_body_tokens = 0

        source_order = source_order_start

        def flush() -> None:
            nonlocal current_pieces
            nonlocal current_body_tokens
            nonlocal source_order

            if not current_pieces:
                return

            chunk = self._render_text_chunk(
                pieces=current_pieces,
                section=section,
                subsection=subsection,
                heading=heading,
                group_index=group_index,
                source_order=source_order,
            )

            chunks.append(chunk)

            source_order += 1
            current_pieces = []
            current_body_tokens = 0

        for piece in pieces:
            piece_tokens = self._count_tokens(
                piece["text"]
            )

            # If adding this piece exceeds the hard limit, flush the
            # current chunk first.
            if (
                current_pieces
                and (
                    current_body_tokens
                    + piece_tokens
                    > self.config.max_tokens
                )
            ):
                flush()

            current_pieces.append(piece)
            current_body_tokens += piece_tokens

            # Soft target:
            #
            # Once we have reached the preferred size, finish the chunk
            # at the current natural element boundary.
            if (
                current_body_tokens
                >= self.config.target_tokens
            ):
                flush()

        flush()

        return chunks

    def _render_text_chunk(
        self,
        pieces: list[dict],
        section: str | None,
        subsection: str | None,
        heading: str | None,
        group_index: int,
        source_order: int,
    ) -> DocumentChunk:
        body = "\n\n".join(
            piece["text"]
            for piece in pieces
        ).strip()

        prefix = self._build_hierarchy_prefix(
            section=section,
            subsection=subsection,
            heading=heading,
        )

        content = (
            f"{prefix}\n\n{body}".strip()
            if prefix
            else body
        )

        # The hierarchy prefix itself consumes tokens.
        #
        # If adding the prefix causes the chunk to exceed the hard limit,
        # trim the body to keep the final chunk within max_tokens.
        if (
            self._count_tokens(content)
            > self.config.max_tokens
        ):
            content = self._trim_content_to_max_tokens(
                prefix=prefix,
                body=body,
            )

        pages = [
            piece["page_start"]
            for piece in pieces
        ] + [
            piece["page_end"]
            for piece in pieces
        ]

        element_ids: list[str] = []

        for piece in pieces:
            element_ids.extend(
                piece["element_ids"]
            )

        metadata = {
            "source": "text",
            "group_index": group_index,
            "element_ids": element_ids,
            "body_token_count": self._count_tokens(
                body
            ),
            "source_order": source_order,
        }

        split_parts = [
            piece["split_part"]
            for piece in pieces
            if piece["split_part"] is not None
        ]

        if split_parts:
            metadata["split_parts"] = split_parts

        return DocumentChunk(
            chunk_index=-1,
            content_type=ChunkContentType.TEXT,
            content=content,
            page_start=min(pages),
            page_end=max(pages),
            section=section,
            subsection=subsection,
            heading=heading,
            token_count=self._count_tokens(
                content
            ),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Oversized text splitting
    # ------------------------------------------------------------------

    def _split_oversized_text(
        self,
        text: str,
    ) -> list[str]:
        """
        Split one oversized text element using token windows.

        Overlap is only introduced here.

        Normal paragraph chunks do not overlap because natural document
        hierarchy and paragraph boundaries are preferred.
        """

        token_ids = self.encoding.encode(text)

        if (
            len(token_ids)
            <= self.config.max_tokens
        ):
            return [text]

        window_size = min(
            self.config.target_tokens,
            self.config.max_tokens,
        )

        overlap = self.config.overlap_tokens

        step = window_size - overlap

        if step <= 0:
            raise ValueError(
                "Invalid chunk configuration: "
                "overlap_tokens leaves no forward progress"
            )

        chunks: list[str] = []

        start = 0

        while start < len(token_ids):
            end = min(
                start + window_size,
                len(token_ids),
            )

            # Avoid creating a very small final tail when the current
            # chunk still has room under max_tokens.
            remaining = len(token_ids) - end

            if (
                remaining > 0
                and remaining < overlap
                and (
                    len(token_ids) - start
                    <= self.config.max_tokens
                )
            ):
                end = len(token_ids)

            chunk_tokens = token_ids[start:end]

            chunk_text = self.encoding.decode(
                chunk_tokens
            ).strip()

            if chunk_text:
                chunks.append(chunk_text)

            if end >= len(token_ids):
                break

            start = end - overlap

        return chunks

    # ------------------------------------------------------------------
    # TABLE chunking
    # ------------------------------------------------------------------

    def _build_table_chunks(
        self,
        tables: list[ExtractedTable],
    ) -> list[DocumentChunk]:
        """
        Build TABLE chunks only from validated pdfplumber candidates.
        """

        chunks: list[DocumentChunk] = []

        source_order = 0

        for table_index, table in enumerate(tables):
            normalized_rows = self._normalize_table_rows(
                table.rows
            )

            if not normalized_rows:
                continue

            if len(normalized_rows) < 2:
                continue

            table_chunks = self._chunk_single_table(
                table=table,
                rows=normalized_rows,
                table_index=table_index,
                source_order_start=source_order,
            )

            chunks.extend(table_chunks)
            source_order += len(table_chunks)

        return chunks

    def _chunk_single_table(
        self,
        table: ExtractedTable,
        rows: list[list[str]],
        table_index: int,
        source_order_start: int,
    ) -> list[DocumentChunk]:
        header = rows[0]
        data_rows = rows[1:]

        # Try the complete table first.
        complete_markdown = self._render_markdown_table(
            header=header,
            rows=data_rows,
        )

        complete_content = self._render_table_content(
            table=table,
            markdown=complete_markdown,
        )

        if (
            self._count_tokens(complete_content)
            <= self.config.max_tokens
        ):
            return [
                self._make_table_chunk(
                    table=table,
                    content=complete_content,
                    table_index=table_index,
                    table_part=0,
                    row_start=1,
                    row_end=len(rows) - 1,
                    source_order=source_order_start,
                )
            ]

        # --------------------------------------------------------------
        # Large table:
        # split by rows and repeat the header in every chunk.
        # --------------------------------------------------------------

        chunks: list[DocumentChunk] = []

        current_rows: list[list[str]] = []
        row_start = 1

        table_part = 0
        source_order = source_order_start

        for row_index, row in enumerate(
            data_rows,
            start=1,
        ):
            candidate_rows = current_rows + [row]

            candidate_markdown = (
                self._render_markdown_table(
                    header=header,
                    rows=candidate_rows,
                )
            )

            candidate_content = (
                self._render_table_content(
                    table=table,
                    markdown=candidate_markdown,
                )
            )

            if (
                current_rows
                and (
                    self._count_tokens(
                        candidate_content
                    )
                    > self.config.max_tokens
                )
            ):
                markdown = self._render_markdown_table(
                    header=header,
                    rows=current_rows,
                )

                content = self._render_table_content(
                    table=table,
                    markdown=markdown,
                )

                chunks.append(
                    self._make_table_chunk(
                        table=table,
                        content=content,
                        table_index=table_index,
                        table_part=table_part,
                        row_start=row_start,
                        row_end=row_index - 1,
                        source_order=source_order,
                    )
                )

                table_part += 1
                source_order += 1

                current_rows = [row]
                row_start = row_index

            else:
                current_rows.append(row)

        if current_rows:
            markdown = self._render_markdown_table(
                header=header,
                rows=current_rows,
            )

            content = self._render_table_content(
                table=table,
                markdown=markdown,
            )

            # Extremely large individual rows can still exceed the
            # limit. In that unusual case, preserve the data and split
            # the rendered table text token-wise.
            if (
                self._count_tokens(content)
                <= self.config.max_tokens
            ):
                chunks.append(
                    self._make_table_chunk(
                        table=table,
                        content=content,
                        table_index=table_index,
                        table_part=table_part,
                        row_start=row_start,
                        row_end=len(rows) - 1,
                        source_order=source_order,
                    )
                )
            else:
                chunks.extend(
                    self._split_large_rendered_table(
                        table=table,
                        content=content,
                        table_index=table_index,
                        table_part_start=table_part,
                        row_start=row_start,
                        row_end=len(rows) - 1,
                        source_order_start=source_order,
                    )
                )

        return chunks

    def _make_table_chunk(
        self,
        table: ExtractedTable,
        content: str,
        table_index: int,
        table_part: int,
        row_start: int,
        row_end: int,
        source_order: int,
    ) -> DocumentChunk:
        validation = table.metadata.get(
            "table_validation",
            {}
        )

        metadata = {
            "source": "table",
            "table_id": table.table_id,
            "table_index": table_index,
            "table_part": table_part,
            "row_start": row_start,
            "row_end": row_end,
            "source_order": source_order,
            "table_validation": validation,
        }

        return DocumentChunk(
            chunk_index=-1,
            content_type=ChunkContentType.TABLE,
            content=content,
            page_start=table.page_number,
            page_end=table.page_number,
            section=table.section,
            subsection=table.subsection,
            heading=table.heading,
            token_count=self._count_tokens(
                content
            ),
            metadata=metadata,
        )

    def _split_large_rendered_table(
        self,
        table: ExtractedTable,
        content: str,
        table_index: int,
        table_part_start: int,
        row_start: int,
        row_end: int,
        source_order_start: int,
    ) -> list[DocumentChunk]:
        """
        Safety fallback for a single table row that itself exceeds the
        hard token limit.

        Normally table splitting should happen by rows. This fallback
        exists only to guarantee the hard max-token invariant.
        """

        pieces = self._split_oversized_text(
            content
        )

        chunks: list[DocumentChunk] = []

        for index, piece in enumerate(pieces):
            metadata = {
                "source": "table",
                "table_id": table.table_id,
                "table_index": table_index,
                "table_part": (
                    table_part_start + index
                ),
                "row_start": row_start,
                "row_end": row_end,
                "source_order": (
                    source_order_start + index
                ),
                "table_validation": (
                    table.metadata.get(
                        "table_validation",
                        {},
                    )
                ),
                "token_split_fallback": True,
            }

            chunks.append(
                DocumentChunk(
                    chunk_index=-1,
                    content_type=(
                        ChunkContentType.TABLE
                    ),
                    content=piece,
                    page_start=table.page_number,
                    page_end=table.page_number,
                    section=table.section,
                    subsection=table.subsection,
                    heading=table.heading,
                    token_count=self._count_tokens(
                        piece
                    ),
                    metadata=metadata,
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Table hierarchy assignment
    # ------------------------------------------------------------------

    def _assign_table_hierarchy(
        self,
        document: ParsedDocument,
        tables: list[ExtractedTable],
    ) -> None:
        """
        Assign section/subsection/heading context to tables.

        Strategy:
        - Prefer the nearest preceding hierarchical element on the same
          page.
        - Otherwise use the latest hierarchical element from an earlier
          page.

        This is intentionally deterministic and does not use an LLM.
        """

        hierarchical_elements = [
            element
            for element in document.elements
            if (
                element.section
                or element.subsection
                or element.heading
            )
        ]

        hierarchical_elements.sort(
            key=lambda element: (
                element.page_number,
                self._bbox_top(element.bbox),
            )
        )

        for table in tables:
            candidate: DocumentElement | None = None

            table_top = self._bbox_top(
                table.bbox
            )

            # ----------------------------------------------------------
            # Same page:
            # choose the closest preceding hierarchical element.
            # ----------------------------------------------------------

            same_page_candidates = [
                element
                for element in hierarchical_elements
                if (
                    element.page_number
                    == table.page_number
                    and self._bbox_top(
                        element.bbox
                    )
                    <= table_top
                )
            ]

            if same_page_candidates:
                candidate = max(
                    same_page_candidates,
                    key=lambda element: (
                        self._bbox_top(
                            element.bbox
                        )
                    ),
                )

            # ----------------------------------------------------------
            # Previous pages fallback.
            # ----------------------------------------------------------

            if candidate is None:
                previous_candidates = [
                    element
                    for element in hierarchical_elements
                    if (
                        element.page_number
                        < table.page_number
                    )
                ]

                if previous_candidates:
                    candidate = max(
                        previous_candidates,
                        key=lambda element: (
                            element.page_number,
                            self._bbox_top(
                                element.bbox
                            ),
                        ),
                    )

            if candidate is None:
                continue

            table.section = candidate.section
            table.subsection = (
                candidate.subsection
            )
            table.heading = candidate.heading

            table.metadata[
                "hierarchy_source_element_id"
            ] = candidate.element_id

    # ------------------------------------------------------------------
    # Table normalization / rendering
    # ------------------------------------------------------------------

    def _normalize_table_rows(
        self,
        rows: list[list[str | None]],
    ) -> list[list[str]]:
        """
        Normalize pdfplumber rows.

        - clean whitespace
        - remove completely empty rows
        - pad rows to equal width
        - remove columns that are empty for every row
        """

        cleaned_rows: list[list[str]] = []

        for row in rows:
            cleaned = [
                self._clean_table_cell(cell)
                for cell in row
            ]

            if any(cleaned):
                cleaned_rows.append(cleaned)

        if not cleaned_rows:
            return []

        max_columns = max(
            len(row)
            for row in cleaned_rows
        )

        padded_rows = [
            row
            + [""] * (
                max_columns - len(row)
            )
            for row in cleaned_rows
        ]

        keep_columns: list[int] = []

        for column_index in range(
            max_columns
        ):
            if any(
                row[column_index]
                for row in padded_rows
            ):
                keep_columns.append(
                    column_index
                )

        if not keep_columns:
            return []

        normalized_rows = [
            [
                row[column_index]
                for column_index in keep_columns
            ]
            for row in padded_rows
        ]

        return normalized_rows

    def _clean_table_cell(
        self,
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        value = str(value)

        parts = [
            part.strip()
            for part in value.replace(
                "\r",
                "\n",
            ).splitlines()
            if part.strip()
        ]

        value = " ".join(
            " ".join(parts).split()
        )

        # Escape markdown table separator.
        value = value.replace(
            "|",
            "\\|",
        )

        return value

    def _render_markdown_table(
        self,
        header: list[str],
        rows: Iterable[list[str]],
    ) -> str:
        header_line = (
            "| "
            + " | ".join(header)
            + " |"
        )

        separator_line = (
            "| "
            + " | ".join(
                "---"
                for _ in header
            )
            + " |"
        )

        data_lines = [
            "| "
            + " | ".join(row)
            + " |"
            for row in rows
        ]

        return "\n".join(
            [
                header_line,
                separator_line,
                *data_lines,
            ]
        )

    def _render_table_content(
        self,
        table: ExtractedTable,
        markdown: str,
    ) -> str:
        parts: list[str] = []

        hierarchy_prefix = (
            self._build_hierarchy_prefix(
                section=table.section,
                subsection=table.subsection,
                heading=table.heading,
            )
        )

        if hierarchy_prefix:
            parts.append(
                hierarchy_prefix
            )

        if table.title:
            title = self._normalize_text(
                table.title
            )

            if title:
                parts.append(
                    f"Table: {title}"
                )

        parts.append(markdown)

        return "\n\n".join(
            parts
        ).strip()

    # ------------------------------------------------------------------
    # Hierarchy rendering
    # ------------------------------------------------------------------

    def _build_hierarchy_prefix(
        self,
        section: str | None,
        subsection: str | None,
        heading: str | None,
    ) -> str:
        parts: list[str] = []

        if section:
            parts.append(
                f"Section: "
                f"{self._normalize_text(section)}"
            )

        if subsection:
            parts.append(
                f"Subsection: "
                f"{self._normalize_text(subsection)}"
            )

        if heading:
            normalized_heading = (
                self._normalize_text(
                    heading
                )
            )

            normalized_section = (
                self._normalize_text(
                    section
                )
                if section
                else None
            )

            normalized_subsection = (
                self._normalize_text(
                    subsection
                )
                if subsection
                else None
            )

            # Avoid printing exactly the same hierarchy text twice.
            if normalized_heading not in {
                normalized_section,
                normalized_subsection,
            }:
                parts.append(
                    f"Heading: "
                    f"{normalized_heading}"
                )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _count_tokens(
        self,
        text: str,
    ) -> int:
        if not text:
            return 0

        return len(
            self.encoding.encode(text)
        )

    def _trim_content_to_max_tokens(
        self,
        prefix: str,
        body: str,
    ) -> str:
        """
        Safety helper ensuring hierarchy prefix + body never exceeds the
        configured hard token limit.
        """

        if not prefix:
            token_ids = self.encoding.encode(
                body
            )

            return self.encoding.decode(
                token_ids[
                    : self.config.max_tokens
                ]
            ).strip()

        prefix_tokens = self._count_tokens(
            prefix
        )

        separator_tokens = self._count_tokens(
            "\n\n"
        )

        available = (
            self.config.max_tokens
            - prefix_tokens
            - separator_tokens
        )

        if available <= 0:
            prefix_ids = self.encoding.encode(
                prefix
            )

            return self.encoding.decode(
                prefix_ids[
                    : self.config.max_tokens
                ]
            ).strip()

        body_ids = self.encoding.encode(
            body
        )

        trimmed_body = self.encoding.decode(
            body_ids[:available]
        ).strip()

        return (
            f"{prefix}\n\n{trimmed_body}"
        ).strip()

    # ------------------------------------------------------------------
    # General helpers
    # ------------------------------------------------------------------

    def _normalize_text(
        self,
        text: str | None,
    ) -> str:
        if not text:
            return ""

        lines = [
            " ".join(line.split())
            for line in text.replace(
                "\r",
                "\n",
            ).splitlines()
        ]

        lines = [
            line
            for line in lines
            if line
        ]

        return "\n".join(lines).strip()

    def _bbox_top(
        self,
        bbox: BoundingBox | None,
    ) -> float:
        if bbox is None:
            return float("inf")

        return float(bbox.y0)

    def _content_type_order(
        self,
        content_type: ChunkContentType,
    ) -> int:
        if (
            content_type
            == ChunkContentType.TEXT
        ):
            return 0

        if (
            content_type
            == ChunkContentType.TABLE
        ):
            return 1

        return 2