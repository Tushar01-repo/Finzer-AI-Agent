from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.document_ingestion.models import (
    DocumentElement,
    DocumentElementType,
    ExtractedTable,
    ParsedDocument,
)
from app.document_ingestion.structure.style_profiler import (
    DocumentStyleProfile,
)
from app.document_ingestion.structure.toc_detector import (
    TOCResult,
)


@dataclass
class HeadingDecision:
    is_heading: bool
    score: float
    reasons: list[str]


class StructureDetector:
    """
    Detect physical headings using typography, text patterns,
    table geometry and document-level structural evidence.

    This is not a semantic IPO section classifier.
    """

    HEADING_THRESHOLD = 3.0

    SHORT_TEXT_LIMIT = 180
    VERY_SHORT_TEXT_LIMIT = 90

    SECTION_PATTERN = re.compile(
        r"^SECTION\s+(?:[IVXLCDM]+|\d+)"
        r"(?:\s*[:\-–—]\s*|\s+).*$",
        re.IGNORECASE,
    )

    # 1. Introduction
    # 1.1 Business Overview
    NUMBERED_PATTERN = re.compile(
        r"^\d+(?:\.\d+){0,4}[\.\)]\s+[A-Za-z]"
    )

    # a) Business Overview
    # B. Products
    # iii) Operations
    ENUMERATED_PATTERN = re.compile(
        r"^(?:[A-Za-z]|[IVXLCDM]{1,5})[\.\)]\s*[A-Za-z]",
        re.IGNORECASE,
    )

    def detect(
        self,
        document: ParsedDocument,
        *,
        style_profile: DocumentStyleProfile,
        tables: Iterable[ExtractedTable] | None = None,
        toc: TOCResult | None = None,
    ) -> ParsedDocument:

        tables = list(tables or [])

        toc_titles = self._build_toc_titles(
            toc
        )

        for element in document.elements:

            inside_table = self._inside_table(
                element,
                tables,
            )

            decision = self._classify_element(
                element=element,
                style_profile=style_profile,
                inside_table=inside_table,
                toc_titles=toc_titles,
            )

            element.metadata[
                "heading_score"
            ] = decision.score

            element.metadata[
                "heading_reasons"
            ] = decision.reasons

            element.metadata[
                "inside_table"
            ] = inside_table

            if decision.is_heading:
                element.element_type = (
                    DocumentElementType.HEADING
                )

                element.heading = (
                    self._normalize_heading_text(
                        element.text
                    )
                )
            else:
                element.element_type = (
                    DocumentElementType.PARAGRAPH
                )

                element.heading = None

        return document

    # ==========================================================
    # CLASSIFICATION
    # ==========================================================

    def _classify_element(
        self,
        *,
        element: DocumentElement,
        style_profile: DocumentStyleProfile,
        inside_table: bool,
        toc_titles: set[str],
    ) -> HeadingDecision:

        text = self._normalize_heading_text(
            element.text
        )

        if not text:
            return HeadingDecision(
                False,
                0.0,
                [],
            )

        # ------------------------------------------------------
        # Strong rejection: detected table
        # ------------------------------------------------------

        if inside_table:
            return HeadingDecision(
                False,
                -5.0,
                ["inside_table"],
            )

        score = 0.0
        reasons: list[str] = []

        text_length = len(text)

        # ------------------------------------------------------
        # Table/data-like content
        # ------------------------------------------------------

        if self._looks_numeric_heavy(text):
            score -= 4.0
            reasons.append(
                "numeric_heavy_penalty"
            )

        if self._contains_placeholder_cells(text):
            score -= 2.0
            reasons.append(
                "table_placeholder_penalty"
            )

        if self._looks_like_table_row(text):
            score -= 3.0
            reasons.append(
                "table_row_penalty"
            )

        # ------------------------------------------------------
        # Explicit section pattern
        # ------------------------------------------------------

        if self.SECTION_PATTERN.match(text):
            score += 6.0
            reasons.append(
                "explicit_section_pattern"
            )

        # ------------------------------------------------------
        # Numbered headings
        # ------------------------------------------------------

        elif self.NUMBERED_PATTERN.match(text):

            if self._reasonable_heading_shape(text):
                score += 3.0
                reasons.append(
                    "numbered_heading_pattern"
                )

        # ------------------------------------------------------
        # Letter / Roman enumeration
        # ------------------------------------------------------

        elif self.ENUMERATED_PATTERN.match(text):

            if self._reasonable_heading_shape(text):
                score += 2.5
                reasons.append(
                    "enumerated_heading_pattern"
                )

        # ------------------------------------------------------
        # TOC match
        # ------------------------------------------------------

        normalized = self._normalize_for_match(
            text
        )

        if normalized in toc_titles:
            score += 6.0
            reasons.append("toc_match")

        # ------------------------------------------------------
        # Typography
        # ------------------------------------------------------

        if element.is_bold:
            score += 1.5
            reasons.append("bold")

        if self._is_uppercase(text):
            score += 1.25
            reasons.append("uppercase")

        # ------------------------------------------------------
        # Length
        # ------------------------------------------------------

        if (
            text_length
            <= self.VERY_SHORT_TEXT_LIMIT
        ):
            score += 0.75
            reasons.append(
                "very_short_text"
            )

        elif (
            text_length
            <= self.SHORT_TEXT_LIMIT
        ):
            score += 0.25
            reasons.append(
                "short_text"
            )

        else:
            score -= 1.5
            reasons.append(
                "long_text_penalty"
            )

        # ------------------------------------------------------
        # Font size
        # ------------------------------------------------------

        if (
            element.font_size is not None
            and
            style_profile.body_font_size
            is not None
        ):

            difference = (
                element.font_size
                - style_profile.body_font_size
            )

            if difference >= 2.0:
                score += 2.0
                reasons.append(
                    "font_much_larger_than_body"
                )

            elif difference >= 0.75:
                score += 1.0
                reasons.append(
                    "font_larger_than_body"
                )

        # ------------------------------------------------------
        # Line structure
        # ------------------------------------------------------

        lines = [
            line.strip()
            for line in element.text.splitlines()
            if line.strip()
        ]

        if len(lines) >= 5:
            score -= 2.0
            reasons.append(
                "many_lines_penalty"
            )

        # Blocks containing many tiny lines are often tables.
        if self._many_short_lines(lines):
            score -= 2.0
            reasons.append(
                "many_short_lines_penalty"
            )

        return HeadingDecision(
            is_heading=(
                score >= self.HEADING_THRESHOLD
            ),
            score=score,
            reasons=reasons,
        )

    # ==========================================================
    # TABLE / DATA HEURISTICS
    # ==========================================================

    @staticmethod
    def _looks_numeric_heavy(
        text: str,
    ) -> bool:

        meaningful = [
            char
            for char in text
            if not char.isspace()
        ]

        if not meaningful:
            return False

        numeric_like = sum(
            1
            for char in meaningful
            if (
                char.isdigit()
                or char in "₹$€£%,.[]●()-"
            )
        )

        ratio = (
            numeric_like
            / len(meaningful)
        )

        return ratio >= 0.45

    @staticmethod
    def _contains_placeholder_cells(
        text: str,
    ) -> bool:

        placeholder_count = len(
            re.findall(
                r"\[?\s*●\s*\]?",
                text,
            )
        )

        return placeholder_count >= 2

    @staticmethod
    def _looks_like_table_row(
        text: str,
    ) -> bool:

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        if len(lines) < 4:
            return False

        numeric_lines = 0

        for line in lines:

            compact = line.replace(
                ",",
                "",
            ).replace(
                "%",
                "",
            ).replace(
                ".",
                "",
            ).replace(
                "₹",
                "",
            ).strip()

            if (
                compact.isdigit()
                or compact in {
                    "[●]",
                    "●",
                    "-",
                }
            ):
                numeric_lines += 1

        return (
            numeric_lines / len(lines)
        ) >= 0.30

    @staticmethod
    def _many_short_lines(
        lines: list[str],
    ) -> bool:

        if len(lines) < 5:
            return False

        short_lines = sum(
            1
            for line in lines
            if len(line) <= 20
        )

        return (
            short_lines / len(lines)
        ) >= 0.60

    # ==========================================================
    # HEADING SHAPE
    # ==========================================================

    @staticmethod
    def _reasonable_heading_shape(
        text: str,
    ) -> bool:
        """
        Prevent numbering inside table rows from becoming
        heading evidence.
        """

        normalized = " ".join(
            text.split()
        )

        if len(normalized) > 180:
            return False

        digit_count = sum(
            char.isdigit()
            for char in normalized
        )

        letter_count = sum(
            char.isalpha()
            for char in normalized
        )

        if letter_count == 0:
            return False

        # A real heading should generally contain substantially
        # more letters than digits.
        if digit_count > letter_count * 0.50:
            return False

        return True

    # ==========================================================
    # TABLE GEOMETRY
    # ==========================================================

    @staticmethod
    def _inside_table(
        element: DocumentElement,
        tables: list[ExtractedTable],
    ) -> bool:

        if element.bbox is None:
            return False

        center_x = (
            element.bbox.x0
            + element.bbox.x1
        ) / 2

        center_y = (
            element.bbox.y0
            + element.bbox.y1
        ) / 2

        for table in tables:

            if (
                table.page_number
                != element.page_number
            ):
                continue

            if table.bbox is None:
                continue

            if (
                table.bbox.x0
                <= center_x
                <= table.bbox.x1
                and
                table.bbox.y0
                <= center_y
                <= table.bbox.y1
            ):
                return True

        return False

    # ==========================================================
    # TOC
    # ==========================================================

    @staticmethod
    def _build_toc_titles(
        toc: TOCResult | None,
    ) -> set[str]:

        if (
            toc is None
            or not toc.found
        ):
            return set()

        return {
            StructureDetector
            ._normalize_for_match(
                entry.title
            )
            for entry in toc.entries
        }

    # ==========================================================
    # TEXT
    # ==========================================================

    @staticmethod
    def _is_uppercase(
        text: str,
    ) -> bool:

        letters = [
            char
            for char in text
            if char.isalpha()
        ]

        if not letters:
            return False

        uppercase = sum(
            char.isupper()
            for char in letters
        )

        return (
            uppercase / len(letters)
        ) >= 0.90

    @staticmethod
    def _normalize_heading_text(
        text: str,
    ) -> str:

        return " ".join(
            text.split()
        ).strip()

    @staticmethod
    def _normalize_for_match(
        text: str,
    ) -> str:

        text = " ".join(
            text.upper().split()
        )

        text = re.sub(
            r"[.\s]+$",
            "",
            text,
        )

        return text.strip()