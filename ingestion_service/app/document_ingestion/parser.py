from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf

from app.document_ingestion.models import (
    BoundingBox,
    DocumentElement,
    DocumentElementType,
    DownloadedDocument,
    ParsedDocument,
)


class PDFParseError(RuntimeError):
    """
    Raised when a PDF cannot be parsed successfully.
    """


class PDFParser:
    """
    Extract physical text/layout information from a PDF.

    Responsibilities:
        - Open the PDF using PyMuPDF.
        - Process every page.
        - Extract text blocks, lines and spans.
        - Preserve page numbers.
        - Preserve bounding boxes.
        - Preserve font information.
        - Preserve basic style information.
        - Preserve reading order as reported by PyMuPDF.
        - Split mixed physical blocks into conservative logical
          elements when a strong structural-heading transition exists.

    This parser deliberately does NOT:
        - Detect sections.
        - Detect subsections.
        - Classify headings.
        - Extract structured tables.
        - Create chunks.
        - Generate embeddings.

    Those responsibilities belong to later pipeline stages.
    """

    def parse(
        self,
        document: DownloadedDocument,
    ) -> ParsedDocument:
        """
        Parse a downloaded PDF into our intermediate
        ParsedDocument representation.
        """

        file_path = Path(document.file_path)

        if not file_path.exists():
            raise PDFParseError(
                f"PDF does not exist: {file_path}"
            )

        elements: list[DocumentElement] = []

        try:
            pdf = pymupdf.open(file_path)

        except Exception as exc:
            raise PDFParseError(
                f"Unable to open PDF: {file_path}"
            ) from exc

        try:
            page_count = pdf.page_count

            for page_index in range(page_count):
                page = pdf.load_page(page_index)

                page_number = page_index + 1

                page_elements = self._parse_page(
                    page=page,
                    page_number=page_number,
                )

                elements.extend(page_elements)

            metadata = self._build_document_metadata(
                pdf=pdf,
                elements=elements,
            )

            return ParsedDocument(
                downloaded_document=document,
                page_count=page_count,
                elements=elements,
                tables=[],
                metadata=metadata,
            )

        except Exception as exc:
            if isinstance(exc, PDFParseError):
                raise

            raise PDFParseError(
                f"Failed while parsing PDF: {file_path}"
            ) from exc

        finally:
            pdf.close()

    # ==========================================================
    # PAGE PARSING
    # ==========================================================

    def _parse_page(
        self,
        *,
        page: pymupdf.Page,
        page_number: int,
    ) -> list[DocumentElement]:
        """
        Extract text blocks from one PDF page.

        A single physical PyMuPDF block may contain more than one
        logical document element.

        Example:

            For further details, see ...
            4.
            Objects of the Offer

        or:

            Normal paragraph...
            b)
            Industries Served and Typical Customers / Clients

        PyMuPDF may return these as one physical block. We allow
        one physical block to produce multiple logical elements.
        """

        page_dict = page.get_text(
            "dict",
            sort=True,
        )

        page_elements: list[DocumentElement] = []

        block_index = 0

        for block in page_dict.get(
            "blocks",
            [],
        ):
            # PyMuPDF block types:
            #
            # 0 = text
            # 1 = image
            #
            # For now we process only text blocks.

            if block.get("type") != 0:
                continue

            block_elements = self._build_text_elements(
                block=block,
                page_number=page_number,
                block_index=block_index,
            )

            block_index += 1

            page_elements.extend(
                block_elements
            )

        return page_elements

    # ==========================================================
    # PHYSICAL BLOCK -> LOGICAL ELEMENTS
    # ==========================================================

    def _build_text_elements(
        self,
        *,
        block: dict[str, Any],
        page_number: int,
        block_index: int,
    ) -> list[DocumentElement]:
        """
        Convert one physical PyMuPDF text block into one or more
        logical DocumentElements.

        Splitting is intentionally conservative.

        Supported structural transitions include:

            4.
            Objects of the Offer

            b)
            Industries Served and Typical Customers / Clients

            ii)
            Another Subsection

        We do NOT split merely because text is bold.
        """

        lines = block.get(
            "lines",
            [],
        )

        if not lines:
            return []

        logical_groups = (
            self._split_logical_lines(
                lines
            )
        )

        elements: list[DocumentElement] = []

        for group_index, group in enumerate(
            logical_groups
        ):
            element = (
                self._build_element_from_lines(
                    lines=group,
                    page_number=page_number,
                    block_index=block_index,
                    group_index=group_index,
                )
            )

            if element is not None:
                elements.append(element)

        return elements

    def _split_logical_lines(
        self,
        lines: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """
        Split physical block lines into conservative logical groups.

        Example:

            paragraph line 1
            paragraph line 2
            4.
            Objects of the Offer

        becomes:

            Group 0:
                paragraph line 1
                paragraph line 2

            Group 1:
                4.
                Objects of the Offer

        The same applies to alphabetic and Roman subsection
        markers such as:

            b)
            Industries Served and Typical Customers / Clients
        """

        if not lines:
            return []

        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []

        index = 0

        while index < len(lines):
            line = lines[index]

            text = self._line_text(
                line
            )

            # --------------------------------------------------
            # Detect structural marker + heading title:
            #
            #   4.
            #   Objects of the Offer
            #
            #   b)
            #   Industries Served and Typical Customers / Clients
            #
            # Both lines must satisfy strong heading-style
            # requirements before we split the physical block.
            # --------------------------------------------------

            if (
                self._is_structural_marker(text)
                and index + 1 < len(lines)
            ):
                next_line = lines[index + 1]

                next_text = self._line_text(
                    next_line
                )

                if self._is_heading_pair(
                    marker_line=line,
                    marker_text=text,
                    title_line=next_line,
                    title_text=next_text,
                ):
                    # Flush content before the heading.

                    if current:
                        groups.append(current)
                        current = []

                    # Marker + title become one logical element.

                    groups.append(
                        [
                            line,
                            next_line,
                        ]
                    )

                    index += 2
                    continue

            current.append(line)

            index += 1

        if current:
            groups.append(current)

        return groups

    # ==========================================================
    # LOGICAL ELEMENT CONSTRUCTION
    # ==========================================================

    def _build_element_from_lines(
        self,
        *,
        lines: list[dict[str, Any]],
        page_number: int,
        block_index: int,
        group_index: int,
    ) -> DocumentElement | None:
        """
        Build one DocumentElement from a logical group of lines.

        Every logical element is still initially PARAGRAPH.

        StructureDetector remains responsible for deciding whether
        the element represents a heading.
        """

        if not lines:
            return None

        text_lines: list[str] = []
        all_spans: list[dict[str, Any]] = []

        for line in lines:
            line_text = self._line_text(
                line
            )

            if line_text:
                text_lines.append(
                    line_text
                )

            for span in line.get(
                "spans",
                [],
            ):
                span_text = span.get(
                    "text",
                    "",
                )

                if not span_text:
                    continue

                all_spans.append(span)

        if not text_lines:
            return None

        text = "\n".join(
            text_lines
        ).strip()

        if not text:
            return None

        bbox = self._bbox_from_lines(
            lines
        )

        dominant_font_size = (
            self._get_dominant_font_size(
                all_spans
            )
        )

        dominant_font_name = (
            self._get_dominant_font_name(
                all_spans
            )
        )

        is_bold = self._is_block_bold(
            all_spans
        )

        element_id = (
            f"p{page_number}_"
            f"b{block_index}_"
            f"g{group_index}"
        )

        return DocumentElement(
            element_id=element_id,
            page_number=page_number,
            element_type=(
                DocumentElementType.PARAGRAPH
            ),
            text=text,
            bbox=bbox,
            font_size=dominant_font_size,
            font_name=dominant_font_name,
            is_bold=is_bold,
            metadata={
                "block_index": block_index,
                "logical_group_index": (
                    group_index
                ),
                "line_count": len(
                    text_lines
                ),
                "span_count": len(
                    all_spans
                ),
                "font_sizes": (
                    self._collect_font_sizes(
                        all_spans
                    )
                ),
                "font_names": (
                    self._collect_font_names(
                        all_spans
                    )
                ),
            },
        )

    # ==========================================================
    # LINE HELPERS
    # ==========================================================

    def _line_text(
        self,
        line: dict[str, Any],
    ) -> str:
        """
        Extract normalized text from one PyMuPDF line.
        """

        parts: list[str] = []

        for span in line.get(
            "spans",
            [],
        ):
            span_text = span.get(
                "text",
                "",
            )

            if span_text:
                parts.append(
                    span_text
                )

        text = "".join(parts)

        return self._normalize_text(
            text
        )

    @staticmethod
    def _is_structural_marker(
        text: str,
    ) -> bool:
        """
        Detect standalone structural markers.

        Numeric examples:
            1.
            4.
            12.
            1)
            3.2.
            2.4.1.

        Alphabetic examples:
            a)
            b)
            c)
            A.
            B)

        Roman numeral examples:
            i)
            ii)
            iii)
            iv)
            IV.

        Rejected examples:
            19.74
            4,171.71
            2026
            5.79%
        """

        value = text.strip()

        if not value:
            return False

        # ---------------------------------------------
        # Numeric markers
        # ---------------------------------------------
        #
        # Matches:
        #   1.
        #   12.
        #   3.2.
        #   2.4.1.
        #   1)
        #
        # Does not match:
        #   19.74
        # because a final "." is required for dotted
        # multi-level numbering.
        # ---------------------------------------------

        numeric_pattern = (
            r"(?:\d{1,3}\.){1,3}"
            r"|\d{1,3}\)"
        )

        # ---------------------------------------------
        # Alphabetic markers
        # ---------------------------------------------
        #
        # Matches:
        #   a)
        #   b)
        #   A.
        #   B)
        # ---------------------------------------------

        alphabetic_pattern = (
            r"[A-Za-z][\.\)]"
        )

        # ---------------------------------------------
        # Roman numeral markers
        # ---------------------------------------------
        #
        # Matches:
        #   ii)
        #   iii)
        #   IV.
        #
        # Single-character Roman markers such as:
        #   i)
        #   V.
        #
        # are already accepted by alphabetic_pattern.
        # ---------------------------------------------

        roman_pattern = (
            r"(?i:[ivxlcdm]{2,6})[\.\)]"
        )

        pattern = (
            rf"(?:"
            rf"{numeric_pattern}"
            rf"|{alphabetic_pattern}"
            rf"|{roman_pattern}"
            rf")"
        )

        return bool(
            re.fullmatch(
                pattern,
                value,
            )
        )

    def _is_heading_pair(
        self,
        *,
        marker_line: dict[str, Any],
        marker_text: str,
        title_line: dict[str, Any],
        title_text: str,
    ) -> bool:
        """
        Decide whether:

            <structural marker>
            <title>

        represents a strong structural heading transition.

        Examples:

            4.
            Objects of the Offer

            b)
            Industries Served and Typical Customers / Clients

        This deliberately requires strong evidence because tables
        contain many standalone numbers, letters and bold cells.
        """

        if not marker_text:
            return False

        if not title_text:
            return False

        # Structural heading titles should remain reasonably
        # compact. Very long text is more likely to be body text.
        if len(title_text) > 180:
            return False

        letters = sum(
            character.isalpha()
            for character in title_text
        )

        digits = sum(
            character.isdigit()
            for character in title_text
        )

        # A heading title needs meaningful alphabetic content.
        if letters == 0:
            return False

        # Reject numeric-heavy title lines.
        if digits > letters * 0.5:
            return False

        # Marker and title must both be predominantly bold.
        #
        # This is important because values such as:
        #
        #   4.
        #   7,999,523
        #
        # may appear in financial/shareholding tables.
        if not self._line_is_bold(
            marker_line
        ):
            return False

        if not self._line_is_bold(
            title_line
        ):
            return False

        return True

    @staticmethod
    def _line_is_bold(
        line: dict[str, Any],
    ) -> bool:
        """
        Determine whether a line is strongly/predominantly bold.

        A stricter 80% threshold is used here because this method
        participates in physical block splitting.

        We therefore require stronger evidence than normal
        block-level bold detection.
        """

        spans = line.get(
            "spans",
            [],
        )

        total_characters = 0
        bold_characters = 0

        for span in spans:
            text = span.get(
                "text",
                "",
            )

            if not text:
                continue

            length = len(
                text.strip()
            )

            if length == 0:
                continue

            total_characters += length

            font_name = (
                str(
                    span.get(
                        "font",
                        "",
                    )
                )
                .lower()
            )

            if any(
                marker in font_name
                for marker in (
                    "bold",
                    "black",
                    "heavy",
                    "semibold",
                    "demibold",
                )
            ):
                bold_characters += length

        if total_characters == 0:
            return False

        return (
            bold_characters
            / total_characters
        ) >= 0.80

    # ==========================================================
    # FONT INFORMATION
    # ==========================================================

    @staticmethod
    def _get_dominant_font_size(
        spans: list[dict[str, Any]],
    ) -> float | None:
        """
        Determine the most frequently occurring font size
        within the logical element.
        """

        sizes = [
            round(
                float(span["size"]),
                2,
            )
            for span in spans
            if span.get("size") is not None
        ]

        if not sizes:
            return None

        return Counter(
            sizes
        ).most_common(1)[0][0]

    @staticmethod
    def _get_dominant_font_name(
        spans: list[dict[str, Any]],
    ) -> str | None:
        """
        Determine the most frequently occurring font name
        within the logical element.
        """

        fonts = [
            str(span["font"])
            for span in spans
            if span.get("font")
        ]

        if not fonts:
            return None

        return Counter(
            fonts
        ).most_common(1)[0][0]

    @staticmethod
    def _collect_font_sizes(
        spans: list[dict[str, Any]],
    ) -> list[float]:
        """
        Collect unique font sizes used in the logical element.
        """

        sizes = {
            round(
                float(span["size"]),
                2,
            )
            for span in spans
            if span.get("size") is not None
        }

        return sorted(sizes)

    @staticmethod
    def _collect_font_names(
        spans: list[dict[str, Any]],
    ) -> list[str]:
        """
        Collect unique font names used in the logical element.
        """

        fonts = {
            str(span["font"])
            for span in spans
            if span.get("font")
        }

        return sorted(fonts)

    # ==========================================================
    # BOLD DETECTION
    # ==========================================================

    @staticmethod
    def _is_block_bold(
        spans: list[dict[str, Any]],
    ) -> bool:
        """
        Estimate whether a logical element is predominantly bold.

        We primarily inspect the font name because PDF font flags
        are not always reliable across documents.

        Examples:
            Times-Bold
            Arial-BoldMT
            Helvetica-Bold
            ABCDEF+Calibri-Bold
        """

        if not spans:
            return False

        bold_characters = 0
        total_characters = 0

        for span in spans:
            text = span.get(
                "text",
                "",
            )

            if not text:
                continue

            length = len(
                text.strip()
            )

            if length == 0:
                continue

            total_characters += length

            font_name = (
                str(
                    span.get(
                        "font",
                        "",
                    )
                )
                .lower()
            )

            if any(
                marker in font_name
                for marker in (
                    "bold",
                    "black",
                    "heavy",
                    "semibold",
                    "demibold",
                )
            ):
                bold_characters += length

        if total_characters == 0:
            return False

        return (
            bold_characters
            / total_characters
        ) >= 0.5

    # ==========================================================
    # DOCUMENT METADATA
    # ==========================================================

    @staticmethod
    def _build_document_metadata(
        *,
        pdf: pymupdf.Document,
        elements: list[DocumentElement],
    ) -> dict[str, Any]:
        """
        Store useful parser-level metadata.

        This is NOT structural classification yet.
        """

        pdf_metadata = (
            pdf.metadata
            or {}
        )

        text_element_count = len(
            elements
        )

        pages_with_text = len(
            {
                element.page_number
                for element in elements
                if element.text.strip()
            }
        )

        return {
            "pdf_metadata": {
                "title": pdf_metadata.get(
                    "title"
                ),
                "author": pdf_metadata.get(
                    "author"
                ),
                "subject": pdf_metadata.get(
                    "subject"
                ),
                "keywords": pdf_metadata.get(
                    "keywords"
                ),
                "creator": pdf_metadata.get(
                    "creator"
                ),
                "producer": pdf_metadata.get(
                    "producer"
                ),
            },
            "text_element_count": (
                text_element_count
            ),
            "pages_with_text": (
                pages_with_text
            ),
        }

    # ==========================================================
    # BOUNDING BOX HELPERS
    # ==========================================================

    @staticmethod
    def _bbox_from_lines(
        lines: list[dict[str, Any]],
    ) -> BoundingBox | None:
        """
        Calculate the union bounding box for a logical collection
        of PyMuPDF lines.
        """

        boxes: list[Any] = []

        for line in lines:
            bbox = line.get(
                "bbox"
            )

            if (
                bbox
                and len(bbox) == 4
            ):
                boxes.append(
                    bbox
                )

        if not boxes:
            return None

        return BoundingBox(
            x0=float(
                min(
                    box[0]
                    for box in boxes
                )
            ),
            y0=float(
                min(
                    box[1]
                    for box in boxes
                )
            ),
            x1=float(
                max(
                    box[2]
                    for box in boxes
                )
            ),
            y1=float(
                max(
                    box[3]
                    for box in boxes
                )
            ),
        )

    @staticmethod
    def _extract_bbox(
        value: Any,
    ) -> BoundingBox | None:
        """
        Convert a raw PyMuPDF bbox into our BoundingBox model.

        Kept because it may still be useful for future parser
        functionality.
        """

        if not value:
            return None

        if len(value) != 4:
            return None

        return BoundingBox(
            x0=float(value[0]),
            y0=float(value[1]),
            x1=float(value[2]),
            y1=float(value[3]),
        )

    # ==========================================================
    # TEXT NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """
        Normalize whitespace inside a single extracted line
        without destroying document structure.
        """

        value = value.replace(
            "\u00a0",
            " ",
        )

        value = re.sub(
            r"[ \t]+",
            " ",
            value,
        )

        return value.strip()