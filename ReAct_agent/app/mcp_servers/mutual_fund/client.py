from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from app.mcp_servers.mutual_fund.models import (
    LatestNAV,
    MutualFundDetails,
    MutualFundSummary,
    NAVHistory,
    NAVPoint,
)


class MFAPIError(Exception):
    """Base exception for MFAPI client failures."""


class MFAPITimeoutError(MFAPIError):
    """Raised when MFAPI does not respond within the configured timeout."""


class MFAPINotFoundError(MFAPIError):
    """Raised when the requested mutual fund cannot be found."""


class MFAPIResponseError(MFAPIError):
    """Raised when MFAPI returns an unexpected or invalid response."""


class MFAPIClient:
    """
    HTTP client for MFAPI.

    Responsibilities:
    - Call MFAPI endpoints.
    - Handle HTTP/network errors.
    - Validate basic response structure.
    - Normalize provider responses into internal models.
    - Enforce NAV date filtering locally.

    This class contains no MCP or agent-specific logic.
    """

    BASE_URL = "https://api.mfapi.in"

    def __init__(
        self,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Finzer-ReAct-Agent/1.0",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_mutual_funds(
        self,
        query: str,
    ) -> list[MutualFundSummary]:
        query = query.strip()

        if not query:
            raise ValueError("query cannot be empty")

        payload = self._get(
            "/mf/search",
            params={"q": query},
        )

        if not isinstance(payload, list):
            raise MFAPIResponseError(
                "Unexpected response from MFAPI search endpoint."
            )

        results: list[MutualFundSummary] = []

        for item in payload:
            if not isinstance(item, dict):
                continue

            scheme_code = item.get("schemeCode")
            scheme_name = item.get("schemeName")

            if scheme_code is None or not scheme_name:
                continue

            try:
                results.append(
                    MutualFundSummary(
                        scheme_code=int(scheme_code),
                        scheme_name=str(scheme_name).strip(),
                    )
                )
            except (TypeError, ValueError):
                continue

        return results

    def get_mutual_fund_details(
        self,
        scheme_code: int,
    ) -> MutualFundDetails:
        self._validate_scheme_code(scheme_code)

        payload = self._get(f"/mf/{scheme_code}")

        meta = self._extract_meta(payload, scheme_code)

        return MutualFundDetails(
            scheme_code=self._parse_scheme_code(
                meta.get("scheme_code"),
                fallback=scheme_code,
            ),
            scheme_name=self._required_string(
                meta.get("scheme_name"),
                "scheme_name",
            ),
            fund_house=self._optional_string(
                meta.get("fund_house")
            ),
            scheme_type=self._optional_string(
                meta.get("scheme_type")
            ),
            scheme_category=self._optional_string(
                meta.get("scheme_category")
            ),
        )

    def get_latest_nav(
        self,
        scheme_code: int,
    ) -> LatestNAV:
        self._validate_scheme_code(scheme_code)

        payload = self._get(
            f"/mf/{scheme_code}/latest"
        )

        meta = self._extract_meta(
            payload,
            scheme_code,
        )

        data = self._extract_data(payload)

        if not data:
            raise MFAPINotFoundError(
                f"No NAV data found for scheme {scheme_code}."
            )

        latest = data[0]

        if not isinstance(latest, dict):
            raise MFAPIResponseError(
                f"Invalid latest NAV response for scheme "
                f"{scheme_code}."
            )

        return LatestNAV(
            scheme_code=self._parse_scheme_code(
                meta.get("scheme_code"),
                fallback=scheme_code,
            ),
            scheme_name=self._required_string(
                meta.get("scheme_name"),
                "scheme_name",
            ),
            nav=self._parse_nav(
                latest.get("nav")
            ),
            date=self._parse_date(
                latest.get("date")
            ),
        )

    def get_nav_history(
        self,
        scheme_code: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> NAVHistory:
        """
        Return NAV history for a mutual fund.

        MFAPI may return the full historical dataset even when
        startDate/endDate query parameters are supplied.

        Because of that, the requested range is also enforced
        locally after parsing the provider response.
        """

        self._validate_scheme_code(scheme_code)

        # ----------------------------------------------------------
        # Parse requested dates BEFORE calling MFAPI.
        # ----------------------------------------------------------

        parsed_start_date = (
            self._parse_input_date(start_date)
            if start_date
            else None
        )

        parsed_end_date = (
            self._parse_input_date(end_date)
            if end_date
            else None
        )

        if (
            parsed_start_date is not None
            and parsed_end_date is not None
            and parsed_start_date > parsed_end_date
        ):
            raise ValueError(
                "start_date cannot be later than end_date."
            )

        # ----------------------------------------------------------
        # Still send the date range to MFAPI.
        #
        # If MFAPI supports/uses it, this can reduce response size.
        # We do not rely on it for correctness.
        # ----------------------------------------------------------

        params: dict[str, str] = {}

        if start_date:
            params["startDate"] = start_date

        if end_date:
            params["endDate"] = end_date

        payload = self._get(
            f"/mf/{scheme_code}",
            params=params or None,
        )

        meta = self._extract_meta(
            payload,
            scheme_code,
        )

        data = self._extract_data(payload)

        # ----------------------------------------------------------
        # Parse provider observations.
        # ----------------------------------------------------------

        observations: list[NAVPoint] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            try:
                observation = NAVPoint(
                    date=self._parse_date(
                        item.get("date")
                    ),
                    nav=self._parse_nav(
                        item.get("nav")
                    ),
                )
            except (
                ValueError,
                TypeError,
                MFAPIResponseError,
            ):
                continue

            # ------------------------------------------------------
            # LOCAL DATE FILTER
            #
            # Do not trust MFAPI query filtering alone.
            # ------------------------------------------------------

            if (
                parsed_start_date is not None
                and observation.date < parsed_start_date
            ):
                continue

            if (
                parsed_end_date is not None
                and observation.date > parsed_end_date
            ):
                continue

            observations.append(observation)

        # ----------------------------------------------------------
        # Keep newest NAV first.
        #
        # MFAPI currently returns this ordering, but explicitly
        # sorting makes our internal contract deterministic.
        # ----------------------------------------------------------

        observations.sort(
            key=lambda observation: observation.date,
            reverse=True,
        )

        return NAVHistory(
            scheme_code=self._parse_scheme_code(
                meta.get("scheme_code"),
                fallback=scheme_code,
            ),
            scheme_name=self._required_string(
                meta.get("scheme_name"),
                "scheme_name",
            ),
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            observations=observations,
            count=len(observations),
        )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.BASE_URL}{path}"

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout_seconds,
            )

        except requests.Timeout as exc:
            raise MFAPITimeoutError(
                f"MFAPI request timed out after "
                f"{self.timeout_seconds} seconds."
            ) from exc

        except requests.RequestException as exc:
            raise MFAPIError(
                f"Unable to connect to MFAPI: {exc}"
            ) from exc

        if response.status_code == 404:
            raise MFAPINotFoundError(
                f"MFAPI resource not found: {path}"
            )

        try:
            response.raise_for_status()

        except requests.RequestException as exc:
            raise MFAPIError(
                f"MFAPI returned HTTP "
                f"{response.status_code}."
            ) from exc

        try:
            return response.json()

        except ValueError as exc:
            raise MFAPIResponseError(
                "MFAPI returned a non-JSON response."
            ) from exc

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_meta(
        payload: Any,
        scheme_code: int,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MFAPIResponseError(
                f"Invalid response for scheme {scheme_code}."
            )

        meta = payload.get("meta")

        if not isinstance(meta, dict):
            raise MFAPIResponseError(
                f"Missing metadata for scheme {scheme_code}."
            )

        return meta

    @staticmethod
    def _extract_data(
        payload: Any,
    ) -> list[Any]:
        if not isinstance(payload, dict):
            raise MFAPIResponseError(
                "Invalid MFAPI response."
            )

        data = payload.get("data")

        if data is None:
            return []

        if not isinstance(data, list):
            raise MFAPIResponseError(
                "MFAPI 'data' field must be a list."
            )

        return data

    # ------------------------------------------------------------------
    # Validation / parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_scheme_code(
        scheme_code: int,
    ) -> None:
        if (
            isinstance(scheme_code, bool)
            or not isinstance(scheme_code, int)
            or scheme_code <= 0
        ):
            raise ValueError(
                "scheme_code must be a positive integer."
            )

    @staticmethod
    def _parse_scheme_code(
        value: Any,
        fallback: int,
    ) -> int:
        if value is None:
            return fallback

        try:
            return int(value)

        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _required_string(
        value: Any,
        field_name: str,
    ) -> str:
        if value is None:
            raise MFAPIResponseError(
                f"MFAPI response is missing "
                f"'{field_name}'."
            )

        text = str(value).strip()

        if not text:
            raise MFAPIResponseError(
                f"MFAPI response contains empty "
                f"'{field_name}'."
            )

        return text

    @staticmethod
    def _optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        return text or None

    @staticmethod
    def _parse_nav(
        value: Any,
    ) -> float:
        try:
            nav = float(value)

        except (TypeError, ValueError) as exc:
            raise MFAPIResponseError(
                f"Invalid NAV value: {value!r}"
            ) from exc

        if nav < 0:
            raise MFAPIResponseError(
                f"NAV cannot be negative: {nav}"
            )

        return nav

    @staticmethod
    def _parse_date(
        value: Any,
    ):
        if value is None:
            raise MFAPIResponseError(
                "NAV date is missing."
            )

        try:
            return datetime.strptime(
                str(value),
                "%d-%m-%Y",
            ).date()

        except ValueError as exc:
            raise MFAPIResponseError(
                f"Invalid MFAPI date: {value!r}"
            ) from exc

    @staticmethod
    def _parse_input_date(
        value: str,
    ):
        """
        Accept date formats useful to our application.

        Supported:
        - DD-MM-YYYY
        - YYYY-MM-DD
        """

        formats = (
            "%d-%m-%Y",
            "%Y-%m-%d",
        )

        for date_format in formats:
            try:
                return datetime.strptime(
                    value,
                    date_format,
                ).date()

            except ValueError:
                continue

        raise ValueError(
            f"Invalid date '{value}'. "
            "Use DD-MM-YYYY or YYYY-MM-DD."
        )