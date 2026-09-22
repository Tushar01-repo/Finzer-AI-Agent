from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.document_ingestion.models import (
    DocumentElement,
    DocumentElementType,
    ParsedDocument,
)


class HeadingLevel(str, Enum):
    """
    Structural role assigned to a detected heading.
    """

    SECTION = "section"
    SUBSECTION = "subsection"
    HEADING = "heading"
    UNSTRUCTURED = "unstructured"


@dataclass
class HierarchyDecision:
    """
    Result of classifying one detected heading.
    """

    level: HeadingLevel
    marker: str | None = None
    title: str | None = None


class DocumentHierarchyAssigner:
    """
    Assign hierarchical context to structured document elements.

    Input
    -----
    ParsedDocument whose elements have already passed through
    StructureDetector.

    Output
    ------
    The same ParsedDocument with hierarchy metadata assigned to
    elements:

        section
        subsection
        heading

    Example
    -------

        1. Summary of the primary business

            a) Business Overview

                paragraph...

            b) Industries Served

                paragraph...

        2. Summary of the industry

    becomes:

        paragraph under a):

            section =
                "1. Summary of the primary business"

            subsection =
                "a) Business Overview"

        paragraph under b):

            section =
                "1. Summary of the primary business"

            subsection =
                "b) Industries Served"

        paragraph under section 2:

            section =
                "2. Summary of the industry"

            subsection = None

    Important
    ---------
    This class does NOT decide whether something visually looks
    like a heading.

    That is StructureDetector's responsibility.

    This class decides the structural ROLE of an already detected
    heading.
    """

    # ----------------------------------------------------------
    # Section patterns
    # ----------------------------------------------------------

    # Examples:
    #
    #   1. Summary of the primary business
    #   2. Summary of the industry
    #   10. Board of Directors
    #
    SECTION_PATTERN = re.compile(
        r"^\s*(\d{1,3})[\.\)]\s*(.+)$",
        re.DOTALL,
    )

    # ----------------------------------------------------------
    # Subsection patterns
    # ----------------------------------------------------------

    # Examples:
    #
    #   a) Business Overview
    #   b) Industries Served
    #   A. Business Overview
    #
    SUBSECTION_PATTERN = re.compile(
        r"^\s*([A-Za-z])[\.\)]\s*(.+)$",
        re.DOTALL,
    )

    # ----------------------------------------------------------
    # Multi-level numbered headings
    # ----------------------------------------------------------

    # Examples:
    #
    #   1.1 Company Overview
    #   1.2 Products
    #   3.4.1 Manufacturing
    #
    NESTED_NUMBER_PATTERN = re.compile(
        r"^\s*"
        r"(\d+(?:\.\d+)+)"
        r"[\.\)]?"
        r"\s+"
        r"(.+)$",
        re.DOTALL,
    )

    # ----------------------------------------------------------
    # Roman numeral headings
    # ----------------------------------------------------------

    # Examples:
    #
    #   i) Domestic Operations
    #   ii) International Operations
    #   IV. Manufacturing
    #
    ROMAN_PATTERN = re.compile(
        r"^\s*"
        r"([ivxlcdm]+)"
        r"[\.\)]"
        r"\s*"
        r"(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    def assign(
        self,
        document: ParsedDocument,
    ) -> ParsedDocument:
        """
        Assign hierarchy to every element in document order.

        The method mutates hierarchy fields on DocumentElement
        instances and returns the ParsedDocument for convenient
        pipeline chaining.
        """

        current_section: str | None = None
        current_subsection: str | None = None
        current_heading: str | None = None

        for element in document.elements:

            # --------------------------------------------------
            # Non-heading elements inherit the current context.
            # --------------------------------------------------

            if (
                element.element_type
                != DocumentElementType.HEADING
            ):
                self._apply_context(
                    element=element,
                    section=current_section,
                    subsection=current_subsection,
                    heading=current_heading,
                )

                continue

            # --------------------------------------------------
            # Heading element:
            # determine structural level.
            # --------------------------------------------------

            decision = self._classify_heading(
                element.text
            )

            normalized_heading = (
                self._normalize_heading_text(
                    element.text
                )
            )

            # Store classification metadata for debugging and
            # downstream chunking.
            element.metadata[
                "hierarchy_level"
            ] = decision.level.value

            element.metadata[
                "hierarchy_marker"
            ] = decision.marker

            element.metadata[
                "hierarchy_title"
            ] = decision.title

            # --------------------------------------------------
            # SECTION
            # --------------------------------------------------

            if (
                decision.level
                == HeadingLevel.SECTION
            ):
                current_section = (
                    normalized_heading
                )

                # New section resets all lower levels.
                current_subsection = None
                current_heading = None

                self._apply_context(
                    element=element,
                    section=current_section,
                    subsection=None,
                    heading=None,
                )

                continue

            # --------------------------------------------------
            # SUBSECTION
            # --------------------------------------------------

            if (
                decision.level
                == HeadingLevel.SUBSECTION
            ):
                current_subsection = (
                    normalized_heading
                )

                # New subsection resets lower heading.
                current_heading = None

                self._apply_context(
                    element=element,
                    section=current_section,
                    subsection=current_subsection,
                    heading=None,
                )

                continue

            # --------------------------------------------------
            # HEADING
            # --------------------------------------------------

            if (
                decision.level
                == HeadingLevel.HEADING
            ):
                current_heading = (
                    normalized_heading
                )

                self._apply_context(
                    element=element,
                    section=current_section,
                    subsection=current_subsection,
                    heading=current_heading,
                )

                continue

            # --------------------------------------------------
            # UNSTRUCTURED
            # --------------------------------------------------
            #
            # Examples from the current PDF:
            #
            #   ON
            #   CLOSES ON
            #
            #   INVESTOR BID/
            #   OFFER PERIOD
            #
            # These may visually resemble headings, but they do
            # not provide reliable structural hierarchy.
            #
            # Therefore they MUST NOT reset section/subsection
            # state.
            # --------------------------------------------------

            self._apply_context(
                element=element,
                section=current_section,
                subsection=current_subsection,
                heading=current_heading,
            )

        return document

    # ==========================================================
    # HEADING CLASSIFICATION
    # ==========================================================

    def _classify_heading(
        self,
        text: str,
    ) -> HierarchyDecision:
        """
        Determine structural role from heading syntax.

        Priority matters.

        Nested numeric patterns are checked before top-level
        numeric sections.
        """

        normalized = (
            self._normalize_heading_text(
                text
            )
        )

        if not normalized:
            return HierarchyDecision(
                level=HeadingLevel.UNSTRUCTURED
            )

        # ------------------------------------------------------
        # Nested numeric heading
        #
        # 1.1 Company Overview
        # 2.3 Products
        # ------------------------------------------------------

        match = self.NESTED_NUMBER_PATTERN.match(
            normalized
        )

        if match:
            marker = match.group(1)
            title = match.group(2).strip()

            return HierarchyDecision(
                level=HeadingLevel.HEADING,
                marker=marker,
                title=title,
            )

        # ------------------------------------------------------
        # Top-level numeric section
        #
        # 1. Summary...
        # 12. Summary...
        # ------------------------------------------------------

        match = self.SECTION_PATTERN.match(
            normalized
        )

        if match:
            marker = match.group(1)
            title = match.group(2).strip()

            return HierarchyDecision(
                level=HeadingLevel.SECTION,
                marker=marker,
                title=title,
            )

        # ------------------------------------------------------
        # Alphabetic subsection
        #
        # a) Business Overview
        # b) Industries Served
        # ------------------------------------------------------

        match = self.SUBSECTION_PATTERN.match(
            normalized
        )

        if match:
            marker = match.group(1)
            title = match.group(2).strip()

            return HierarchyDecision(
                level=HeadingLevel.SUBSECTION,
                marker=marker,
                title=title,
            )

        # ------------------------------------------------------
        # Roman numeral heading
        # ------------------------------------------------------

        match = self.ROMAN_PATTERN.match(
            normalized
        )

        if match:
            marker = match.group(1)
            title = match.group(2).strip()

            return HierarchyDecision(
                level=HeadingLevel.HEADING,
                marker=marker,
                title=title,
            )

        # ------------------------------------------------------
        # Detected visually as heading but without structural
        # numbering.
        #
        # Keep it available as an unstructured heading candidate,
        # but do not let it corrupt hierarchy state.
        # ------------------------------------------------------

        return HierarchyDecision(
            level=HeadingLevel.UNSTRUCTURED,
            marker=None,
            title=normalized,
        )

    # ==========================================================
    # CONTEXT
    # ==========================================================

    @staticmethod
    def _apply_context(
        *,
        element: DocumentElement,
        section: str | None,
        subsection: str | None,
        heading: str | None,
    ) -> None:
        """
        Apply current hierarchy context to one element.
        """

        element.section = section
        element.subsection = subsection
        element.heading = heading

        # Also keep hierarchy context in metadata because this is
        # useful when inspecting/debugging parsed output and when
        # persisting intermediate representations.
        element.metadata[
            "section"
        ] = section

        element.metadata[
            "subsection"
        ] = subsection

        element.metadata[
            "heading"
        ] = heading

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_heading_text(
        text: str,
    ) -> str:
        """
        Convert physical line breaks inside a heading to spaces.

        Example:

            4.
            Objects of the Offer

        becomes:

            4. Objects of the Offer

        Original element.text is NOT modified.
        """

        value = text.replace(
            "\u00a0",
            " ",
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()