from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.document_ingestion.models import (
    DocumentElement,
    ParsedDocument,
)


@dataclass
class TOCEntry:
    """
    One entry discovered from a document's table of contents.
    """

    title: str

    page_number: int | None = None

    # Physical PDF page where this TOC entry was found.
    source_page: int | None = None

    # Optional hierarchy level.
    # We do not aggressively infer this yet.
    level: int | None = None

    metadata: dict = field(
        default_factory=dict
    )


@dataclass
class TOCResult:
    """
    Result of TOC detection.
    """

    found: bool

    start_page: int | None = None
    end_page: int | None = None

    entries: list[TOCEntry] = field(
        default_factory=list
    )

    metadata: dict = field(
        default_factory=dict
    )


class TOCDetector:
    """
    Detect a table of contents and extract possible entries.

    This class deliberately does NOT:
        - classify document headings
        - modify ParsedDocument elements
        - assign sections/subsections
        - create chunks

    It only extracts structural evidence that can later be
    consumed by StructureDetector.
    """

    # ----------------------------------------------------------
    # Common TOC titles
    # ----------------------------------------------------------

    TOC_TITLES = {
        "TABLE OF CONTENTS",
        "CONTENTS",
        "INDEX",
    }

    # ----------------------------------------------------------
    # Patterns such as:
    #
    # RISK FACTORS ................ 30
    # OUR BUSINESS ............... 142
    # FINANCIAL INFORMATION ...... 250
    #
    # Also accepts whitespace instead of dots.
    # ----------------------------------------------------------

    PAGE_NUMBER_PATTERN = re.compile(
        r"""
        ^
        (?P<title>.+?)
        (?:
            \.{2,}
            |
            \s{2,}
        )
        (?P<page>\d{1,4})
        $
        """,
        re.VERBOSE,
    )

    # ----------------------------------------------------------
    # Some IPO documents contain:
    #
    # SECTION I: GENERAL
    # SECTION II: RISK FACTORS
    #
    # without page numbers in the same extracted block.
    # ----------------------------------------------------------

    SECTION_PATTERN = re.compile(
        r"""
        ^
        SECTION
        \s+
        (?P<number>
            [IVXLCDM]+
            |
            \d+
        )
        \s*
        [:\-–—]?
        \s*
        (?P<title>.+)
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # Avoid interpreting extremely long paragraphs as
    # TOC entries.
    MAX_ENTRY_LENGTH = 250

    # TOCs are normally near the beginning of IPO PDFs.
    DEFAULT_SEARCH_PAGES = 20

    def detect(
        self,
        document: ParsedDocument,
        *,
        search_pages: int = DEFAULT_SEARCH_PAGES,
    ) -> TOCResult:
        """
        Search the beginning of a ParsedDocument for a TOC.
        """

        candidate_elements = [
            element
            for element in document.elements
            if (
                element.page_number <= search_pages
                and element.text.strip()
            )
        ]

        toc_start = self._find_toc_start(
            candidate_elements
        )

        if toc_start is None:
            return TOCResult(
                found=False,
                metadata={
                    "searched_pages": min(
                        search_pages,
                        document.page_count,
                    ),
                },
            )

        toc_elements = self._collect_toc_elements(
            candidate_elements,
            start_index=toc_start,
        )

        entries: list[TOCEntry] = []

        for element in toc_elements:
            element_entries = (
                self._extract_entries_from_element(
                    element
                )
            )

            entries.extend(
                element_entries
            )

        entries = self._deduplicate_entries(
            entries
        )

        start_page = (
            toc_elements[0].page_number
            if toc_elements
            else candidate_elements[
                toc_start
            ].page_number
        )

        end_page = (
            toc_elements[-1].page_number
            if toc_elements
            else start_page
        )

        return TOCResult(
            found=True,
            start_page=start_page,
            end_page=end_page,
            entries=entries,
            metadata={
                "searched_pages": min(
                    search_pages,
                    document.page_count,
                ),
                "entry_count": len(entries),
            },
        )

    # ==========================================================
    # TOC START
    # ==========================================================

    def _find_toc_start(
        self,
        elements: list[DocumentElement],
    ) -> int | None:

        for index, element in enumerate(
            elements
        ):
            normalized = self._normalize_heading(
                element.text
            )

            if normalized in self.TOC_TITLES:
                return index

            # Sometimes the block contains:
            #
            # TABLE OF CONTENTS
            # SECTION I ...
            #
            # instead of the heading as its own block.

            first_line = (
                element.text
                .splitlines()[0]
                .strip()
            )

            first_line = (
                self._normalize_heading(
                    first_line
                )
            )

            if first_line in self.TOC_TITLES:
                return index

        return None

    # ==========================================================
    # TOC REGION
    # ==========================================================

    def _collect_toc_elements(
        self,
        elements: list[DocumentElement],
        *,
        start_index: int,
    ) -> list[DocumentElement]:
        """
        Collect elements likely belonging to the TOC.

        For the first implementation we use a conservative
        page-based window.

        Later StructureDetector can use the entries as evidence
        even if this window contains some extra text.
        """

        start_element = elements[start_index]

        start_page = start_element.page_number

        # IPO TOCs can span multiple pages, but we don't want
        # to accidentally consume the whole document.
        max_toc_page = start_page + 6

        result: list[DocumentElement] = []

        for element in elements[start_index:]:

            if element.page_number > max_toc_page:
                break

            result.append(element)

        return result

    # ==========================================================
    # ENTRY EXTRACTION
    # ==========================================================

    def _extract_entries_from_element(
        self,
        element: DocumentElement,
    ) -> list[TOCEntry]:

        entries: list[TOCEntry] = []

        lines = [
            self._normalize_line(line)
            for line in element.text.splitlines()
        ]

        lines = [
            line
            for line in lines
            if line
        ]

        for line in lines:

            if len(line) > self.MAX_ENTRY_LENGTH:
                continue

            normalized = self._normalize_heading(
                line
            )

            if normalized in self.TOC_TITLES:
                continue

            # ----------------------------------------------
            # Title + page number
            # ----------------------------------------------

            page_match = (
                self.PAGE_NUMBER_PATTERN.match(
                    line
                )
            )

            if page_match:

                title = (
                    page_match
                    .group("title")
                    .strip(" .")
                )

                page_number = int(
                    page_match.group("page")
                )

                if self._valid_entry_title(
                    title
                ):
                    entries.append(
                        TOCEntry(
                            title=title,
                            page_number=page_number,
                            source_page=(
                                element.page_number
                            ),
                            metadata={
                                "match_type":
                                    "title_page",
                            },
                        )
                    )

                continue

            # ----------------------------------------------
            # SECTION I: GENERAL
            # ----------------------------------------------

            section_match = (
                self.SECTION_PATTERN.match(
                    line
                )
            )

            if section_match:

                section_number = (
                    section_match
                    .group("number")
                    .strip()
                )

                title = (
                    section_match
                    .group("title")
                    .strip()
                )

                if self._valid_entry_title(
                    title
                ):
                    entries.append(
                        TOCEntry(
                            title=(
                                f"SECTION "
                                f"{section_number}: "
                                f"{title}"
                            ),
                            page_number=None,
                            source_page=(
                                element.page_number
                            ),
                            level=1,
                            metadata={
                                "match_type":
                                    "section",
                                "section_number":
                                    section_number,
                            },
                        )
                    )

        return entries

    # ==========================================================
    # DEDUPLICATION
    # ==========================================================

    @staticmethod
    def _deduplicate_entries(
        entries: list[TOCEntry],
    ) -> list[TOCEntry]:

        result: list[TOCEntry] = []

        seen: set[
            tuple[str, int | None]
        ] = set()

        for entry in entries:

            key = (
                " ".join(
                    entry.title
                    .upper()
                    .split()
                ),
                entry.page_number,
            )

            if key in seen:
                continue

            seen.add(key)

            result.append(entry)

        return result

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @staticmethod
    def _valid_entry_title(
        title: str,
    ) -> bool:

        title = title.strip()

        if len(title) < 3:
            return False

        # Require at least one alphabetic character.

        if not any(
            char.isalpha()
            for char in title
        ):
            return False

        return True

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_line(
        value: str,
    ) -> str:

        value = value.replace(
            "\u00a0",
            " ",
        )

        return value.strip()

    @staticmethod
    def _normalize_heading(
        value: str,
    ) -> str:

        return " ".join(
            value.upper().split()
        ).strip()