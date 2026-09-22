from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from app.document_ingestion.models import (
    DiscoveredDocument,
    DownloadedDocument,
)


class PDFDownloadError(RuntimeError):
    """
    Raised when a PDF cannot be downloaded or validated.
    """


class PDFDownloader:
    """
    Source-independent PDF downloader.

    Responsibilities:
        - Download a PDF from DiscoveredDocument.pdf_url.
        - Stream the response instead of loading the entire file in memory.
        - Validate that the downloaded content is actually a PDF.
        - Generate a safe filename.
        - Calculate SHA-256.
        - Return DownloadedDocument.

    This class does NOT:
        - Parse the PDF.
        - Extract text.
        - Extract tables.
        - Detect sections.
        - Write to PostgreSQL.
    """

    DEFAULT_TIMEOUT = 60
    DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB

    def __init__(
        self,
        download_dir: str | Path,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        session: requests.Session | None = None,
    ) -> None:
        self.download_dir = Path(download_dir)
        self.timeout = timeout
        self.chunk_size = chunk_size

        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/139.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "application/pdf,"
                    "application/octet-stream;q=0.9,"
                    "*/*;q=0.8"
                ),
            }
        )

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def download(
        self,
        document: DiscoveredDocument,
    ) -> DownloadedDocument:
        """
        Download and validate one discovered PDF.
        """

        if not document.pdf_url:
            raise PDFDownloadError(
                f"Document has no PDF URL: {document.title}"
            )

        file_name = self._build_file_name(document)

        destination = self.download_dir / file_name

        # Download into a temporary file first.
        #
        # We do NOT write directly to the final path because a
        # network failure could otherwise leave a partial PDF
        # that looks like a completed download.

        temp_path: Path | None = None

        try:
            with self.session.get(
                document.pdf_url,
                stream=True,
                timeout=self.timeout,
                allow_redirects=True,
            ) as response:

                response.raise_for_status()

                content_type = (
                    response.headers
                    .get("Content-Type", "")
                    .lower()
                )

                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    delete=False,
                    dir=self.download_dir,
                    prefix=".finzer_download_",
                    suffix=".tmp",
                ) as temp_file:

                    temp_path = Path(temp_file.name)

                    sha256 = hashlib.sha256()
                    file_size = 0
                    first_bytes = b""

                    for chunk in response.iter_content(
                        chunk_size=self.chunk_size
                    ):
                        if not chunk:
                            continue

                        if len(first_bytes) < 5:
                            required = 5 - len(first_bytes)
                            first_bytes += chunk[:required]

                        temp_file.write(chunk)

                        sha256.update(chunk)

                        file_size += len(chunk)

            # --------------------------------------------------
            # Validate content
            # --------------------------------------------------

            if file_size == 0:
                raise PDFDownloadError(
                    f"Downloaded file is empty: {document.pdf_url}"
                )

            # A real PDF normally starts with:
            #
            # %PDF-
            #
            # This is stronger than trusting Content-Type because
            # servers sometimes return an HTML error page with a
            # misleading header.

            if first_bytes != b"%PDF-":
                raise PDFDownloadError(
                    "Downloaded content does not have a valid "
                    f"PDF signature. URL: {document.pdf_url}, "
                    f"Content-Type: {content_type or 'unknown'}"
                )

            # --------------------------------------------------
            # Move validated file into final location
            # --------------------------------------------------

            os.replace(
                temp_path,
                destination,
            )

            temp_path = None

            return DownloadedDocument(
                discovered_document=document,
                file_path=destination,
                file_name=file_name,
                file_size_bytes=file_size,
                file_sha256=sha256.hexdigest(),
            )

        except requests.RequestException as exc:
            raise PDFDownloadError(
                f"Failed to download PDF: {document.pdf_url}"
            ) from exc

        finally:
            # Remove partial temporary file if anything failed.

            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ==========================================================
    # FILE NAME
    # ==========================================================

    def _build_file_name(
        self,
        document: DiscoveredDocument,
    ) -> str:
        """
        Prefer the filename from the PDF URL.

        If it is unavailable, derive one from the document title.
        """

        if document.pdf_url:
            parsed_url = urlparse(
                document.pdf_url
            )

            file_name = Path(
                unquote(parsed_url.path)
            ).name
        else:
            file_name = ""

        if not file_name:
            file_name = document.title

        file_name = self._sanitize_filename(
            file_name
        )

        if not file_name.lower().endswith(".pdf"):
            file_name += ".pdf"

        return file_name

    @staticmethod
    def _sanitize_filename(
        file_name: str,
    ) -> str:
        """
        Make a filename safe for Windows/Linux.
        """

        file_name = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            file_name,
        )

        file_name = re.sub(
            r"\s+",
            " ",
            file_name,
        ).strip()

        # Windows does not like filenames ending in
        # a period or space.

        file_name = file_name.rstrip(
            ". "
        )

        if not file_name:
            file_name = "document"

        # Keep filenames manageable.

        max_length = 180

        if len(file_name) > max_length:
            path = Path(file_name)

            suffix = path.suffix

            stem_limit = (
                max_length - len(suffix)
            )

            file_name = (
                path.stem[:stem_limit]
                + suffix
            )

        return file_name