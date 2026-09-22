from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.document_ingestion.models import DiscoveredDocument
from app.document_ingestion.providers.base import DocumentProvider


class SEBIDocumentProvider(DocumentProvider):
    """
    Discover public-issue documents from the SEBI website.

    Responsibilities:
        - Load the SEBI public-issues listing.
        - Preserve SEBI form state.
        - Handle SEBI AJAX pagination.
        - Extract filing and PDF URLs.
        - Normalize discovered metadata.
        - Yield DiscoveredDocument objects.

    This provider deliberately does NOT download PDFs.
    """

    BASE_URL = "https://www.sebi.gov.in"

    MAIN_URL = (
        "https://www.sebi.gov.in/sebiweb/home/HomeAction.do"
        "?doListing=yes&sid=3&ssid=15&smid=10"
    )

    AJAX_URL = (
        "https://www.sebi.gov.in/"
        "sebiweb/ajax/home/getnewslistinfo.jsp"
    )

    DEFAULT_TIMEOUT = 60

    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout

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
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )

    @property
    def source_name(self) -> str:
        return "sebi"

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def discover(
        self,
        *,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> Iterator[DiscoveredDocument]:
        """
        Discover documents from the SEBI public-issues listing.

        Pages are processed lazily and documents are yielded
        one at a time.
        """

        if start_page < 1:
            raise ValueError("start_page must be >= 1")

        if end_page is not None and end_page < start_page:
            raise ValueError(
                "end_page must be greater than or equal to start_page"
            )

        main_html = self._load_main_page()

        form_data = self._extract_form_data(main_html)

        current_page = 1
        page_html = main_html

        while True:
            # --------------------------------------------------
            # Process current page if requested.
            # --------------------------------------------------

            if current_page >= start_page:
                records = self._extract_records(page_html)

                for record in records:
                    yield self._build_discovered_document(record)

            # --------------------------------------------------
            # Stop when requested end page has been reached.
            # --------------------------------------------------

            if end_page is not None and current_page >= end_page:
                break

            # --------------------------------------------------
            # Page 1 is contained in the main response.
            # Pages 2+ are requested through SEBI's AJAX endpoint.
            # --------------------------------------------------

            try:
                next_page_html = self._get_next_page(form_data)
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Failed to request SEBI page "
                    f"{current_page + 1}"
                ) from exc

            next_value = self._update_next_value(
                form_data,
                next_page_html,
            )

            # Without nextValue we cannot safely continue.
            if not next_value:
                break

            current_page += 1
            page_html = next_page_html

    # ==========================================================
    # MAIN PAGE
    # ==========================================================

    def _load_main_page(self) -> str:
        response = self.session.get(
            self.MAIN_URL,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.text

    # ==========================================================
    # FORM STATE
    # ==========================================================

    @staticmethod
    def _extract_form_data(html: str) -> dict[str, str]:
        """
        Extract the SEBI homeForm state required for AJAX
        pagination.
        """

        soup = BeautifulSoup(html, "html.parser")

        form = soup.find(
            "form",
            {"name": "homeForm"},
        )

        if not form:
            raise RuntimeError(
                "SEBI homeForm was not found"
            )

        data: dict[str, str] = {}

        # ------------------------------------------------------
        # Input fields
        # ------------------------------------------------------

        for input_tag in form.find_all("input"):
            name = input_tag.get("name")

            if not name:
                continue

            input_type = (
                input_tag.get("type", "")
                .strip()
                .lower()
            )

            if input_type in {"submit", "button"}:
                continue

            data[name] = input_tag.get("value", "")

        # ------------------------------------------------------
        # Select fields
        # ------------------------------------------------------

        for select in form.find_all("select"):
            name = select.get("name")

            if not name:
                continue

            selected = select.find(
                "option",
                selected=True,
            )

            if selected:
                data[name] = selected.get(
                    "value",
                    "",
                )
                continue

            first_option = select.find("option")

            if first_option:
                data[name] = first_option.get(
                    "value",
                    "",
                )

        # ------------------------------------------------------
        # Required defaults
        # ------------------------------------------------------

        defaults = {
            "nextValue": "1",
            "next": "n",
            "search": "",
            "fromDate": "",
            "toDate": "",
            "fromYear": "",
            "toYear": "",
            "deptId": "",
            "sid": "3",
            "ssid": "15",
            "smid": "10",
            "ssidhidden": "",
            "intmid": "-1",
            "sectName": "",
            "ssText": "",
            "smText": "",
            "doDirect": "0",
        }

        for key, value in defaults.items():
            data.setdefault(key, value)

        data.setdefault(
            "sText",
            data.get("sectName", ""),
        )

        return data

    # ==========================================================
    # RECORD EXTRACTION
    # ==========================================================

    def _extract_records(
        self,
        html: str,
    ) -> list[dict[str, Any]]:
        """
        Extract records from SEBI table id='sample_1'.

        SEBI-specific quirks:
            - tbody may not exist.
            - PDF anchor may be nested inside filing anchor.
            - filing title should use direct text where possible.
        """

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        table = soup.find(
            "table",
            id="sample_1",
        )

        if not table:
            return []

        records: list[dict[str, Any]] = []

        for row in table.find_all("tr"):
            columns = row.find_all("td")

            if len(columns) < 2:
                continue

            raw_date = columns[0].get_text(
                " ",
                strip=True,
            )

            links = columns[1].find_all(
                "a",
                href=True,
            )

            if not links:
                continue

            filing_link = links[0]

            filing_href = (
                filing_link
                .get("href", "")
                .strip()
            )

            if not filing_href:
                continue

            filing_url = urljoin(
                self.BASE_URL,
                filing_href,
            )

            # --------------------------------------------------
            # Filing title
            #
            # The PDF anchor can be nested inside the first
            # anchor. We therefore prefer only the direct text
            # belonging to the filing anchor.
            # --------------------------------------------------

            direct_text = filing_link.find(
                string=True,
                recursive=False,
            )

            if direct_text:
                title = direct_text.strip()
            else:
                title = filing_link.get_text(
                    " ",
                    strip=True,
                )

            title = self._normalize_whitespace(
                title
            )

            # --------------------------------------------------
            # PDF URL
            # --------------------------------------------------

            pdf_url = None

            for link in columns[1].find_all(
                "a",
                href=True,
            ):
                href = (
                    link.get("href", "")
                    .strip()
                )

                if ".pdf" in href.lower():
                    pdf_url = urljoin(
                        self.BASE_URL,
                        href,
                    )
                    break

            records.append(
                {
                    "date": raw_date,
                    "title": title,
                    "filing_url": filing_url,
                    "pdf_url": pdf_url,
                }
            )

        return records

    # ==========================================================
    # AJAX PAGINATION
    # ==========================================================

    def _get_next_page(
        self,
        form_data: dict[str, str],
    ) -> str:
        """
        Request the next listing page using the same AJAX
        mechanism used by the SEBI website.
        """

        data = form_data.copy()

        data["next"] = "n"
        data["doDirect"] = "1"

        headers = {
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.MAIN_URL,
        }

        response = self.session.post(
            self.AJAX_URL,
            data=data,
            headers=headers,
            timeout=self.timeout,
        )

        response.raise_for_status()

        # SEBI may append extra data separated by #@#.
        return response.text.split("#@#", 1)[0]

    @staticmethod
    def _update_next_value(
        form_data: dict[str, str],
        page_html: str,
    ) -> str | None:
        """
        Update nextValue using the value returned by SEBI.
        """

        soup = BeautifulSoup(
            page_html,
            "html.parser",
        )

        element = soup.find(
            "input",
            {"name": "nextValue"},
        )

        if not element:
            return None

        next_value = (
            element.get("value", "")
            .strip()
        )

        if not next_value:
            return None

        form_data["nextValue"] = next_value

        return next_value

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    def _build_discovered_document(
        self,
        record: dict[str, Any],
    ) -> DiscoveredDocument:
        title = record["title"]

        company_name, document_type = (
            self._parse_title(title)
        )

        return DiscoveredDocument(
            source=self.source_name,
            title=title,
            filing_url=record.get(
                "filing_url"
            ),
            pdf_url=record.get(
                "pdf_url"
            ),
            published_date=self._parse_date(
                record.get("date")
            ),
            company_name=company_name,
            document_type=document_type,
            metadata={
                "source_date_raw": record.get(
                    "date"
                ),
            },
        )

    @staticmethod
    def _parse_title(
        title: str,
    ) -> tuple[str | None, str | None]:
        """
        Attempt to split a SEBI filing title into:

            company_name
            document_type

        The original title is always preserved separately.

        Example:
            ABC LIMITED - DRHP

        becomes:
            company_name = ABC LIMITED
            document_type = DRHP
        """

        title = title.strip()

        if not title:
            return None, None

        # Prefer separators surrounded by whitespace so
        # hyphens inside company names are less likely to
        # cause an incorrect split.
        parts = re.split(
            r"\s+[-–—]\s+",
            title,
            maxsplit=1,
        )

        if len(parts) != 2:
            return title, None

        company_name = parts[0].strip()
        document_type = parts[1].strip()

        return (
            company_name or None,
            document_type or None,
        )

    @staticmethod
    def _parse_date(
        value: str | None,
    ):
        if not value:
            return None

        value = value.strip()

        formats = (
            "%b %d, %Y",
            "%d %b %Y",
            "%d-%m-%Y",
            "%d/%m/%Y",
        )

        for date_format in formats:
            try:
                return datetime.strptime(
                    value,
                    date_format,
                ).date()
            except ValueError:
                continue

        # Don't fail discovery just because SEBI changed
        # date presentation. Preserve raw date in metadata.
        return None

    @staticmethod
    def _normalize_whitespace(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()