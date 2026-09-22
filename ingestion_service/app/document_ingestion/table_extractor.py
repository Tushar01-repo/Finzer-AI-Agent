from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber

from app.document_ingestion.models import (
    BoundingBox,
    DownloadedDocument,
    ExtractedTable,
)


class TableExtractionError(RuntimeError):
    """
    Raised when table extraction from a PDF fails.
    """


class PDFTableExtractor:
    """
    Extract structured tables from a PDF using pdfplumber.

    Responsibilities:
        - Detect tables page-by-page.
        - Preserve rows and columns.
        - Preserve page number.
        - Preserve table bounding box.
        - Clean extracted cell text.

    This component does NOT:
        - Determine section/subsection hierarchy.
        - Create retrieval chunks.
        - Generate embeddings.
    """

    def extract(
        self,
        document: DownloadedDocument,
    ) -> list[ExtractedTable]:

        file_path = Path(document.file_path)

        if not file_path.exists():
            raise TableExtractionError(
                f"PDF does not exist: {file_path}"
            )

        tables: list[ExtractedTable] = []

        try:
            with pdfplumber.open(file_path) as pdf:

                for page_index, page in enumerate(
                    pdf.pages,
                    start=1,
                ):
                    page_tables = self._extract_page_tables(
                        page=page,
                        page_number=page_index,
                    )

                    tables.extend(page_tables)

        except Exception as exc:
            raise TableExtractionError(
                f"Failed to extract tables from PDF: {file_path}"
            ) from exc

        return tables

    def _extract_page_tables(
        self,
        *,
        page: Any,
        page_number: int,
    ) -> list[ExtractedTable]:

        extracted_tables: list[ExtractedTable] = []

        # find_tables() is preferable here because it gives
        # us both the detected table location and its cells.

        detected_tables = page.find_tables()

        for table_index, table in enumerate(
            detected_tables
        ):
            raw_rows = table.extract()

            if not raw_rows:
                continue

            rows = self._clean_rows(raw_rows)

            if not self._is_useful_table(rows):
                continue

            bbox = self._build_bbox(
                table.bbox
            )

            table_id = (
                f"p{page_number}_t{table_index}"
            )

            extracted_tables.append(
                ExtractedTable(
                    table_id=table_id,
                    page_number=page_number,
                    rows=rows,
                    bbox=bbox,
                    metadata={
                        "table_index_on_page": table_index,
                        "row_count": len(rows),
                        "column_count": self._column_count(
                            rows
                        ),
                    },
                )
            )

        return extracted_tables

    @staticmethod
    def _clean_rows(
        rows: list[list[Any]],
    ) -> list[list[str | None]]:

        cleaned_rows: list[list[str | None]] = []

        for row in rows:

            cleaned_row: list[str | None] = []

            for cell in row:

                if cell is None:
                    cleaned_row.append(None)
                    continue

                text = str(cell)

                # Preserve meaningful content while removing
                # layout newlines inside cells.

                text = " ".join(
                    text.split()
                ).strip()

                cleaned_row.append(
                    text if text else None
                )

            # Ignore completely empty rows.

            if any(
                cell is not None
                for cell in cleaned_row
            ):
                cleaned_rows.append(
                    cleaned_row
                )

        return cleaned_rows

    @staticmethod
    def _is_useful_table(
        rows: list[list[str | None]],
    ) -> bool:
        """
        Reject obvious false-positive table detections.

        Keep this deliberately conservative for now.
        We will tune it using actual IPO documents.
        """

        if not rows:
            return False

        if len(rows) < 2:
            return False

        max_columns = max(
            (len(row) for row in rows),
            default=0,
        )

        if max_columns < 2:
            return False

        non_empty_cells = sum(
            1
            for row in rows
            for cell in row
            if cell
        )

        return non_empty_cells >= 4

    @staticmethod
    def _column_count(
        rows: list[list[str | None]],
    ) -> int:

        return max(
            (len(row) for row in rows),
            default=0,
        )

    @staticmethod
    def _build_bbox(
        value: Any,
    ) -> BoundingBox | None:

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