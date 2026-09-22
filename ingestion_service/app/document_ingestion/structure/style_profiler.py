from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.document_ingestion.models import (
    DocumentElement,
    ParsedDocument,
)


@dataclass
class DocumentStyleProfile:
    """
    Typography/layout profile learned from one PDF.
    """

    body_font_size: float | None
    dominant_font_name: str | None

    font_size_counts: dict[float, int] = field(
        default_factory=dict
    )

    font_name_counts: dict[str, int] = field(
        default_factory=dict
    )

    total_elements: int = 0
    bold_elements: int = 0

    uppercase_elements: int = 0
    short_bold_elements: int = 0

    candidate_heading_sizes: list[float] = field(
        default_factory=list
    )

    @property
    def bold_ratio(self) -> float:
        if self.total_elements == 0:
            return 0.0

        return self.bold_elements / self.total_elements


class DocumentStyleProfiler:
    """
    Learn typography patterns from a ParsedDocument.

    Important:
        This class does NOT decide whether an element is a
        heading.

    It only describes the style distribution of the PDF.
    """

    SHORT_TEXT_LIMIT = 160

    def profile(
        self,
        document: ParsedDocument,
    ) -> DocumentStyleProfile:

        elements = [
            element
            for element in document.elements
            if element.text.strip()
        ]

        if not elements:
            return DocumentStyleProfile(
                body_font_size=None,
                dominant_font_name=None,
            )

        font_size_counts = (
            self._count_font_sizes(elements)
        )

        font_name_counts = (
            self._count_font_names(elements)
        )

        body_font_size = (
            self._determine_body_font_size(
                elements
            )
        )

        dominant_font_name = (
            self._determine_dominant_font(
                elements
            )
        )

        bold_elements = sum(
            1
            for element in elements
            if element.is_bold
        )

        uppercase_elements = sum(
            1
            for element in elements
            if self._is_uppercase_candidate(
                element.text
            )
        )

        short_bold_elements = sum(
            1
            for element in elements
            if (
                element.is_bold
                and self._is_short_text(
                    element.text
                )
            )
        )

        candidate_heading_sizes = (
            self._candidate_heading_sizes(
                font_size_counts,
                body_font_size,
            )
        )

        return DocumentStyleProfile(
            body_font_size=body_font_size,
            dominant_font_name=dominant_font_name,
            font_size_counts=dict(
                sorted(font_size_counts.items())
            ),
            font_name_counts=dict(
                font_name_counts
            ),
            total_elements=len(elements),
            bold_elements=bold_elements,
            uppercase_elements=uppercase_elements,
            short_bold_elements=short_bold_elements,
            candidate_heading_sizes=(
                candidate_heading_sizes
            ),
        )

    # ==========================================================
    # BODY FONT
    # ==========================================================

    @staticmethod
    def _determine_body_font_size(
        elements: list[DocumentElement],
    ) -> float | None:
        """
        Estimate body font size using character-weighted
        frequency.

        This is better than counting blocks because a PDF may
        contain many small heading/table blocks but much more
        actual body text.
        """

        weighted_sizes: Counter[float] = Counter()

        for element in elements:

            if element.font_size is None:
                continue

            text_length = len(
                element.text.strip()
            )

            if text_length == 0:
                continue

            size = round(
                float(element.font_size),
                2,
            )

            weighted_sizes[size] += text_length

        if not weighted_sizes:
            return None

        return weighted_sizes.most_common(1)[0][0]

    # ==========================================================
    # DOMINANT FONT
    # ==========================================================

    @staticmethod
    def _determine_dominant_font(
        elements: list[DocumentElement],
    ) -> str | None:

        weighted_fonts: Counter[str] = Counter()

        for element in elements:

            if not element.font_name:
                continue

            text_length = len(
                element.text.strip()
            )

            if text_length == 0:
                continue

            weighted_fonts[
                element.font_name
            ] += text_length

        if not weighted_fonts:
            return None

        return weighted_fonts.most_common(1)[0][0]

    # ==========================================================
    # DISTRIBUTIONS
    # ==========================================================

    @staticmethod
    def _count_font_sizes(
        elements: list[DocumentElement],
    ) -> Counter[float]:

        counter: Counter[float] = Counter()

        for element in elements:

            if element.font_size is None:
                continue

            size = round(
                float(element.font_size),
                2,
            )

            counter[size] += 1

        return counter

    @staticmethod
    def _count_font_names(
        elements: list[DocumentElement],
    ) -> Counter[str]:

        counter: Counter[str] = Counter()

        for element in elements:

            if element.font_name:
                counter[
                    element.font_name
                ] += 1

        return counter

    # ==========================================================
    # HEADING-SIZE CANDIDATES
    # ==========================================================

    @staticmethod
    def _candidate_heading_sizes(
        font_size_counts: Counter[float],
        body_font_size: float | None,
    ) -> list[float]:
        """
        Return font sizes larger than the inferred body font.

        These are merely signals for the later structure
        detector.
        """

        if body_font_size is None:
            return []

        candidates = [
            size
            for size in font_size_counts
            if size > body_font_size
        ]

        return sorted(
            candidates,
            reverse=True,
        )

    # ==========================================================
    # TEXT CHARACTERISTICS
    # ==========================================================

    @classmethod
    def _is_short_text(
        cls,
        text: str,
    ) -> bool:

        normalized = " ".join(
            text.split()
        )

        return (
            0
            < len(normalized)
            <= cls.SHORT_TEXT_LIMIT
        )

    @staticmethod
    def _is_uppercase_candidate(
        text: str,
    ) -> bool:
        """
        Determine whether alphabetic content is predominantly
        uppercase.

        Numbers and punctuation do not count.
        """

        letters = [
            char
            for char in text
            if char.isalpha()
        ]

        if not letters:
            return False

        uppercase = sum(
            1
            for char in letters
            if char.isupper()
        )

        return (
            uppercase / len(letters)
        ) >= 0.90