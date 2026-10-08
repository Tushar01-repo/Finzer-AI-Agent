from __future__ import annotations

from dataclasses import dataclass, field

from app.document_ingestion.models import ExtractedTable


@dataclass
class TableValidationResult:
    """
    Result of validating one pdfplumber table candidate.

    The validator does not modify the table itself. It only decides whether
    the candidate is reliable enough to be treated as a real table.
    """

    is_valid: bool
    score: float

    reasons: list[str] = field(default_factory=list)

    row_count: int = 0
    column_count: int = 0

    non_empty_cells: int = 0
    total_cells: int = 0

    density: float = 0.0
    numeric_cell_ratio: float = 0.0

    long_cell_ratio: float = 0.0
    single_cell_row_ratio: float = 0.0


@dataclass
class TableValidatorConfig:
    """
    Validation thresholds.

    These are deliberately conservative because a false-positive table can
    remove useful prose from the TEXT chunking pipeline.
    """

    min_score: float = 3.0

    min_rows: int = 2
    min_columns: int = 2
    min_non_empty_cells: int = 4

    sparse_density_threshold: float = 0.18

    long_cell_char_threshold: int = 220
    excessive_long_cell_ratio: float = 0.35

    excessive_single_cell_row_ratio: float = 0.60

    many_columns_threshold: int = 12

    numeric_ratio_bonus_threshold: float = 0.20


class TableValidator:
    """
    Score table candidates produced by pdfplumber.

    Why this exists
    ---------------
    pdfplumber detects spatial table-like regions. In IPO documents that can
    include:

        - genuine financial tables
        - shareholder tables
        - litigation tables
        - page-layout grids
        - bordered disclosure boxes
        - large prose regions

    Therefore:

        pdfplumber candidate != guaranteed semantic table

    We use deterministic structural signals before allowing a candidate into
    the TABLE chunking pipeline.
    """

    def __init__(
        self,
        config: TableValidatorConfig | None = None,
    ) -> None:
        self.config = config or TableValidatorConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        table: ExtractedTable,
    ) -> TableValidationResult:
        rows = self._normalize_rows(table.rows)

        row_count = len(rows)

        column_count = max(
            (len(row) for row in rows),
            default=0,
        )

        padded_rows = [
            row + [""] * (column_count - len(row))
            for row in rows
        ]

        total_cells = row_count * column_count

        non_empty_cells = sum(
            1
            for row in padded_rows
            for cell in row
            if cell
        )

        density = (
            non_empty_cells / total_cells
            if total_cells
            else 0.0
        )

        non_empty_values = [
            cell
            for row in padded_rows
            for cell in row
            if cell
        ]

        numeric_cells = sum(
            1
            for cell in non_empty_values
            if self._looks_numeric(cell)
        )

        numeric_cell_ratio = (
            numeric_cells / len(non_empty_values)
            if non_empty_values
            else 0.0
        )

        long_cells = sum(
            1
            for cell in non_empty_values
            if len(cell) >= self.config.long_cell_char_threshold
        )

        long_cell_ratio = (
            long_cells / len(non_empty_values)
            if non_empty_values
            else 0.0
        )

        single_cell_rows = sum(
            1
            for row in padded_rows
            if self._non_empty_count(row) <= 1
        )

        single_cell_row_ratio = (
            single_cell_rows / row_count
            if row_count
            else 0.0
        )

        score = 0.0
        reasons: list[str] = []

        # --------------------------------------------------------------
        # Hard minimum requirements
        # --------------------------------------------------------------

        if row_count < self.config.min_rows:
            reasons.append("too_few_rows")

        if column_count < self.config.min_columns:
            reasons.append("too_few_columns")

        if non_empty_cells < self.config.min_non_empty_cells:
            reasons.append("too_few_non_empty_cells")

        if (
            row_count < self.config.min_rows
            or column_count < self.config.min_columns
            or non_empty_cells < self.config.min_non_empty_cells
        ):
            return TableValidationResult(
                is_valid=False,
                score=-10.0,
                reasons=reasons,
                row_count=row_count,
                column_count=column_count,
                non_empty_cells=non_empty_cells,
                total_cells=total_cells,
                density=density,
                numeric_cell_ratio=numeric_cell_ratio,
                long_cell_ratio=long_cell_ratio,
                single_cell_row_ratio=single_cell_row_ratio,
            )

        # --------------------------------------------------------------
        # Positive signals
        # --------------------------------------------------------------

        if row_count >= 3:
            score += 1.0
            reasons.append("multiple_rows")

        if column_count >= 2:
            score += 1.0
            reasons.append("multiple_columns")

        if non_empty_cells >= 8:
            score += 1.0
            reasons.append("enough_populated_cells")

        if density >= 0.35:
            score += 1.5
            reasons.append("good_cell_density")

        elif density >= 0.22:
            score += 0.75
            reasons.append("moderate_cell_density")

        if (
            numeric_cell_ratio
            >= self.config.numeric_ratio_bonus_threshold
        ):
            score += 1.0
            reasons.append("numeric_table_signal")

        structured_rows = sum(
            1
            for row in padded_rows
            if self._non_empty_count(row) >= 2
        )

        structured_row_ratio = (
            structured_rows / row_count
            if row_count
            else 0.0
        )

        if structured_row_ratio >= 0.70:
            score += 1.5
            reasons.append("consistent_multi_cell_rows")

        elif structured_row_ratio >= 0.50:
            score += 0.75
            reasons.append("moderate_multi_cell_rows")

        # --------------------------------------------------------------
        # Negative signals
        # --------------------------------------------------------------

        if density < self.config.sparse_density_threshold:
            score -= 2.0
            reasons.append("very_sparse")

        if (
            long_cell_ratio
            >= self.config.excessive_long_cell_ratio
        ):
            score -= 3.0
            reasons.append("too_many_long_prose_cells")

        elif long_cell_ratio >= 0.20:
            score -= 1.5
            reasons.append("several_long_prose_cells")

        if (
            single_cell_row_ratio
            >= self.config.excessive_single_cell_row_ratio
        ):
            score -= 2.5
            reasons.append("too_many_single_cell_rows")

        elif single_cell_row_ratio >= 0.40:
            score -= 1.0
            reasons.append("many_single_cell_rows")

        # A huge number of columns is common when pdfplumber interprets
        # page-layout geometry as a table.
        if (
            column_count
            >= self.config.many_columns_threshold
            and density < 0.35
        ):
            score -= 2.0
            reasons.append("many_sparse_columns")

        # --------------------------------------------------------------
        # Prose-dominance check
        # --------------------------------------------------------------

        if self._looks_like_prose_container(
            padded_rows
        ):
            score -= 4.0
            reasons.append("prose_container")

        is_valid = score >= self.config.min_score

        return TableValidationResult(
            is_valid=is_valid,
            score=round(score, 2),
            reasons=reasons,
            row_count=row_count,
            column_count=column_count,
            non_empty_cells=non_empty_cells,
            total_cells=total_cells,
            density=round(density, 4),
            numeric_cell_ratio=round(
                numeric_cell_ratio,
                4,
            ),
            long_cell_ratio=round(
                long_cell_ratio,
                4,
            ),
            single_cell_row_ratio=round(
                single_cell_row_ratio,
                4,
            ),
        )

    def filter_valid_tables(
        self,
        tables: list[ExtractedTable],
    ) -> list[ExtractedTable]:
        """
        Return only candidates considered valid.

        Validation diagnostics are stored in table.metadata so we can inspect
        why each candidate was accepted or rejected.
        """

        valid_tables: list[ExtractedTable] = []

        for table in tables:
            result = self.validate(table)

            table.metadata["table_validation"] = {
                "is_valid": result.is_valid,
                "score": result.score,
                "reasons": result.reasons,
                "row_count": result.row_count,
                "column_count": result.column_count,
                "non_empty_cells": result.non_empty_cells,
                "total_cells": result.total_cells,
                "density": result.density,
                "numeric_cell_ratio": result.numeric_cell_ratio,
                "long_cell_ratio": result.long_cell_ratio,
                "single_cell_row_ratio": (
                    result.single_cell_row_ratio
                ),
            }

            if result.is_valid:
                valid_tables.append(table)

        return valid_tables

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_rows(
        self,
        rows: list[list[str | None]],
    ) -> list[list[str]]:
        cleaned_rows: list[list[str]] = []

        for row in rows:
            cleaned = [
                self._clean_cell(cell)
                for cell in row
            ]

            if any(cleaned):
                cleaned_rows.append(cleaned)

        return cleaned_rows

    def _clean_cell(
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

        return " ".join(" ".join(parts).split())

    # ------------------------------------------------------------------
    # Structural signals
    # ------------------------------------------------------------------

    def _non_empty_count(
        self,
        row: list[str],
    ) -> int:
        return sum(
            1
            for cell in row
            if cell
        )

    def _looks_numeric(
        self,
        value: str,
    ) -> bool:
        """
        Identify cells that look like financial/table values.

        Examples:

            1,646.51
            39.47
            45.22%
            ₹ 1,259.69
            (125.50)
            2026
        """

        value = value.strip()

        if not value:
            return False

        allowed = set(
            "0123456789"
            ".,%-+()₹$€£ "
        )

        numeric_chars = sum(
            1
            for char in value
            if char in allowed
        )

        ratio = numeric_chars / len(value)

        has_digit = any(
            char.isdigit()
            for char in value
        )

        return has_digit and ratio >= 0.75

    def _looks_like_prose_container(
        self,
        rows: list[list[str]],
    ) -> bool:
        """
        Detect page-layout regions that pdfplumber interpreted as tables.

        Typical false positive:

            | This being the first public issue of Equity Shares ... |

        rather than a repeated row/column structure.
        """

        values = [
            cell
            for row in rows
            for cell in row
            if cell
        ]

        if not values:
            return False

        total_chars = sum(
            len(value)
            for value in values
        )

        if total_chars == 0:
            return False

        longest_cell = max(
            len(value)
            for value in values
        )

        longest_share = (
            longest_cell / total_chars
        )

        paragraph_like_cells = sum(
            1
            for value in values
            if (
                len(value) >= 180
                and self._word_count(value) >= 25
            )
        )

        paragraph_ratio = (
            paragraph_like_cells / len(values)
        )

        # One or a few large prose cells dominate the detected region.
        if longest_share >= 0.45:
            return True

        if paragraph_ratio >= 0.30:
            return True

        return False

    def _word_count(
        self,
        value: str,
    ) -> int:
        return len(
            [
                token
                for token in value.split()
                if token
            ]
        )