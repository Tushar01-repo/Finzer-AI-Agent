from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import requests

from app.mcp_servers.gold.models import (
    GoldCaratPrice,
    GoldCaratPrices,
    GoldConversion,
    GoldPriceHistory,
    GoldPricePoint,
    GoldSpotPrice,
)


TROY_OUNCE_TO_GRAMS = 31.1034768


# ======================================================================
# Exceptions
# ======================================================================


class GoldPriceAPIError(Exception):
    """Base exception for GoldPrice.dev client failures."""


class GoldPriceAPITimeoutError(GoldPriceAPIError):
    """Raised when GoldPrice.dev does not respond within the timeout."""


class GoldPriceAPIAuthError(GoldPriceAPIError):
    """Raised when GoldPrice.dev authentication fails."""


class GoldPriceAPIPlanError(GoldPriceAPIError):
    """Raised when the current API plan does not permit an operation."""


class GoldPriceAPINotFoundError(GoldPriceAPIError):
    """Raised when the requested provider resource does not exist."""


class GoldPriceAPIResponseError(GoldPriceAPIError):
    """Raised when GoldPrice.dev returns invalid or unexpected data."""


# ======================================================================
# GoldPrice.dev Client
# ======================================================================


class GoldPriceClient:
    """
    Low-level GoldPrice.dev client for Finzer.

    Responsibilities:
    - Authentication
    - HTTP communication
    - Provider error handling
    - Input validation
    - Response validation
    - Normalization into Finzer Pydantic models

    This class intentionally contains no MCP or ReAct logic.
    """

    BASE_URL = "https://api.goldprice.dev/v1"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("GOLDPRICE_API_KEY")
        )

        if not self.api_key:
            raise ValueError(
                "GOLDPRICE_API_KEY environment variable is not set."
            )

        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "Finzer-ReAct-Agent/1.0",
            }
        )

    # ==================================================================
    # Spot price
    # ==================================================================

    def get_gold_spot_price(
        self,
        currency: str = "USD",
    ) -> GoldSpotPrice:
        """
        Return the current gold spot price.

        Provider symbol example:

            XAU-USD-SPOT

        The provider reports spot price per troy ounce.

        Finzer additionally calculates price per gram.
        """

        currency = self._normalize_currency(
            currency
        )

        provider_symbol = (
            f"XAU-{currency}-SPOT"
        )

        payload = self._get(
            f"/spot/{provider_symbol}"
        )

        if not isinstance(payload, dict):
            raise GoldPriceAPIResponseError(
                "Invalid gold spot-price response."
            )

        returned_symbol = self._required_string(
            payload.get("symbol"),
            "symbol",
        )

        returned_currency = self._required_string(
            payload.get("quote_currency"),
            "quote_currency",
        ).upper()

        unit = self._required_string(
            payload.get("unit"),
            "unit",
        )

        if unit != "troy_ounce":
            raise GoldPriceAPIResponseError(
                f"Unexpected gold price unit: {unit!r}"
            )

        price_per_ounce = self._parse_non_negative_float(
            payload.get("price"),
            "price",
        )

        price_per_gram = (
            price_per_ounce
            / TROY_OUNCE_TO_GRAMS
        )

        timestamp = self._parse_datetime(
            payload.get("computed_at")
        )

        return GoldSpotPrice(
            symbol=returned_symbol,
            currency=returned_currency,
            price_per_ounce=price_per_ounce,
            price_per_gram=price_per_gram,
            timestamp=timestamp,
        )

    # ==================================================================
    # Carat prices
    # ==================================================================

    def get_gold_carat_prices(
        self,
        currency: str = "USD",
    ) -> GoldCaratPrices:
        """
        Return gold prices per gram for supported carats.

        GoldPrice.dev currently exposes:

        - 24K
        - 22K
        - 21K
        - 20K
        - 18K
        - 16K
        - 14K
        - 10K

        The requested currency is passed directly to the provider.
        """

        currency = self._normalize_currency(
            currency
        )

        payload = self._get(
            "/carat",
            params={
                "currency": currency,
            },
        )

        if not isinstance(payload, dict):
            raise GoldPriceAPIResponseError(
                "Invalid gold carat-price response."
            )

        returned_currency = self._required_string(
            payload.get("currency"),
            "currency",
        ).upper()

        timestamp = self._parse_datetime(
            payload.get("timestamp")
        )

        carat_fields = {
            24: "price_gram_24k",
            22: "price_gram_22k",
            21: "price_gram_21k",
            20: "price_gram_20k",
            18: "price_gram_18k",
            16: "price_gram_16k",
            14: "price_gram_14k",
            10: "price_gram_10k",
        }

        prices: list[GoldCaratPrice] = []

        for carat, field_name in carat_fields.items():
            raw_price = payload.get(
                field_name
            )

            if raw_price is None:
                continue

            price_per_gram = (
                self._parse_non_negative_float(
                    raw_price,
                    field_name,
                )
            )

            prices.append(
                GoldCaratPrice(
                    carat=carat,
                    purity=carat / 24.0,
                    price_per_gram=price_per_gram,
                )
            )

        if not prices:
            raise GoldPriceAPIResponseError(
                "GoldPrice.dev returned no carat prices."
            )

        return GoldCaratPrices(
            currency=returned_currency,
            prices=prices,
            timestamp=timestamp,
        )

    # ==================================================================
    # Historical prices
    # ==================================================================

    def get_gold_price_history(
        self,
        start_date: str,
        end_date: str,
        interval: str = "1d",
        currency: str = "USD",
    ) -> GoldPriceHistory:
        """
        Return historical gold OHLC bars.

        Provider endpoint:

            GET /v1/bars

        Example:

            symbol=XAU-USD-SPOT
            interval=1d
            from=2026-09-03
            to=2026-09-05

        Historical availability may depend on the configured
        GoldPrice.dev subscription tier.
        """

        currency = self._normalize_currency(
            currency
        )

        parsed_start = self._parse_input_date(
            start_date
        )

        parsed_end = self._parse_input_date(
            end_date
        )

        if parsed_start > parsed_end:
            raise ValueError(
                "start_date cannot be later than end_date."
            )

        interval = self._normalize_interval(
            interval
        )

        provider_symbol = (
            f"XAU-{currency}-SPOT"
        )

        payload = self._get(
            "/bars",
            params={
                "symbol": provider_symbol,
                "interval": interval,
                "from": parsed_start.isoformat(),
                "to": parsed_end.isoformat(),
            },
        )

        if not isinstance(payload, dict):
            raise GoldPriceAPIResponseError(
                "Invalid historical gold-price response."
            )

        bars = payload.get(
            "bars",
            [],
        )

        if bars is None:
            bars = []

        if not isinstance(bars, list):
            raise GoldPriceAPIResponseError(
                "GoldPrice.dev 'bars' field must be a list."
            )

        observations: list[GoldPricePoint] = []

        for bar in bars:
            if not isinstance(bar, dict):
                continue

            try:
                timestamp = self._parse_datetime(
                    bar.get("bar_start")
                )

                if timestamp is None:
                    continue

                close_price = (
                    self._parse_non_negative_float(
                        bar.get("close"),
                        "close",
                    )
                )

                observation = GoldPricePoint(
                    timestamp=timestamp,
                    open=self._parse_optional_float(
                        bar.get("open"),
                        "open",
                    ),
                    high=self._parse_optional_float(
                        bar.get("high"),
                        "high",
                    ),
                    low=self._parse_optional_float(
                        bar.get("low"),
                        "low",
                    ),
                    close=close_price,
                )

                observations.append(
                    observation
                )

            except GoldPriceAPIResponseError:
                # A malformed provider observation should not destroy
                # the complete historical response.
                continue

        observations.sort(
            key=lambda item: item.timestamp
        )

        return GoldPriceHistory(
            currency=currency,
            start_date=parsed_start.isoformat(),
            end_date=parsed_end.isoformat(),
            interval=interval,
            observations=observations,
            count=len(observations),
        )

    # ==================================================================
    # Gold conversion
    # ==================================================================

    def convert_gold(
        self,
        amount: float,
        from_symbol: str,
        to_symbol: str,
        unit: str = "gram",
    ) -> GoldConversion:
        """
        Convert a gold/currency amount using GoldPrice.dev.

        Example:

            amount=10
            from_symbol=XAU
            to_symbol=INR
            unit=gram

        This represents 10 grams of gold converted to INR.
        """

        amount = self._validate_amount(
            amount
        )

        from_symbol = self._normalize_symbol(
            from_symbol,
            "from_symbol",
        )

        to_symbol = self._normalize_symbol(
            to_symbol,
            "to_symbol",
        )

        unit = self._normalize_unit(
            unit
        )

        payload = self._get(
            "/convert",
            params={
                "from": from_symbol,
                "to": to_symbol,
                "amount": amount,
                "unit": unit,
            },
        )

        if not isinstance(payload, dict):
            raise GoldPriceAPIResponseError(
                "Invalid gold conversion response."
            )

        returned_from = self._required_string(
            payload.get("from"),
            "from",
        ).upper()

        returned_to = self._required_string(
            payload.get("to"),
            "to",
        ).upper()

        returned_unit = self._required_string(
            payload.get("unit"),
            "unit",
        ).lower()

        returned_amount = (
            self._parse_non_negative_float(
                payload.get("amount"),
                "amount",
            )
        )

        rate = self._parse_optional_float(
            payload.get("rate"),
            "rate",
        )

        converted_value = (
            self._parse_non_negative_float(
                payload.get("result"),
                "result",
            )
        )

        return GoldConversion(
            amount=returned_amount,
            from_symbol=returned_from,
            to_symbol=returned_to,
            unit=returned_unit,
            converted_value=converted_value,
            rate=rate,
        )

    # ==================================================================
    # Account usage
    # ==================================================================

    def get_account_usage(
        self,
    ) -> dict[str, Any]:
        """
        Return GoldPrice.dev API usage.

        Intended for diagnostics/monitoring rather than direct
        exposure as an agent tool.
        """

        payload = self._get(
            "/account/usage"
        )

        if not isinstance(payload, dict):
            raise GoldPriceAPIResponseError(
                "Invalid account usage response."
            )

        return payload

    # ==================================================================
    # HTTP layer
    # ==================================================================

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = (
            f"{self.BASE_URL}{path}"
        )

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout_seconds,
            )

        except requests.Timeout as exc:
            raise GoldPriceAPITimeoutError(
                "GoldPrice.dev request timed out after "
                f"{self.timeout_seconds} seconds."
            ) from exc

        except requests.RequestException as exc:
            raise GoldPriceAPIError(
                "Unable to connect to GoldPrice.dev: "
                f"{exc}"
            ) from exc

        # --------------------------------------------------------------
        # Authentication
        # --------------------------------------------------------------

        if response.status_code == 401:
            raise GoldPriceAPIAuthError(
                "GoldPrice.dev authentication failed."
            )

        # --------------------------------------------------------------
        # Forbidden / plan restriction
        # --------------------------------------------------------------

        if response.status_code == 403:
            self._raise_forbidden_error(
                response
            )

        # --------------------------------------------------------------
        # Resource not found
        # --------------------------------------------------------------

        if response.status_code == 404:
            raise GoldPriceAPINotFoundError(
                "GoldPrice.dev resource not found: "
                f"{path}"
            )

        # --------------------------------------------------------------
        # Remaining HTTP errors
        # --------------------------------------------------------------

        try:
            response.raise_for_status()

        except requests.RequestException as exc:
            message = (
                "GoldPrice.dev returned HTTP "
                f"{response.status_code}."
            )

            provider_message = (
                self._extract_provider_error_message(
                    response
                )
            )

            if provider_message:
                message = (
                    f"{message} {provider_message}"
                )

            raise GoldPriceAPIError(
                message
            ) from exc

        # --------------------------------------------------------------
        # JSON parsing
        # --------------------------------------------------------------

        try:
            return response.json()

        except ValueError as exc:
            raise GoldPriceAPIResponseError(
                "GoldPrice.dev returned a non-JSON response."
            ) from exc

    # ==================================================================
    # HTTP error helpers
    # ==================================================================

    @staticmethod
    def _raise_forbidden_error(
        response: requests.Response,
    ) -> None:
        """
        Convert provider HTTP 403 responses into meaningful
        application exceptions.
        """

        try:
            payload = response.json()

        except ValueError:
            raise GoldPriceAPIAuthError(
                "GoldPrice.dev request was forbidden."
            )

        if not isinstance(payload, dict):
            raise GoldPriceAPIAuthError(
                "GoldPrice.dev request was forbidden."
            )

        error_type = str(
            payload.get(
                "error",
                "",
            )
        ).strip()

        message = str(
            payload.get(
                "message",
                "GoldPrice.dev request was forbidden.",
            )
        ).strip()

        tier = payload.get(
            "tier"
        )

        if error_type == "plan_gated":
            if tier:
                message = (
                    f"{message} "
                    f"Current tier: {tier}."
                )

            raise GoldPriceAPIPlanError(
                message
            )

        raise GoldPriceAPIAuthError(
            message
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_provider_error_message(
        response: requests.Response,
    ) -> str | None:
        try:
            payload = response.json()

        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        message = payload.get(
            "message"
        )

        if message is None:
            return None

        message = str(
            message
        ).strip()

        return (
            message
            if message
            else None
        )

    # ==================================================================
    # Input normalization
    # ==================================================================

    @staticmethod
    def _normalize_currency(
        currency: str,
    ) -> str:
        if not isinstance(currency, str):
            raise ValueError(
                "currency must be a string."
            )

        currency = (
            currency
            .strip()
            .upper()
        )

        if len(currency) != 3:
            raise ValueError(
                "currency must be a 3-letter ISO currency code."
            )

        if not currency.isalpha():
            raise ValueError(
                "currency must contain letters only."
            )

        return currency

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(
        value: str,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{field_name} must be a string."
            )

        value = (
            value
            .strip()
            .upper()
        )

        if not value:
            raise ValueError(
                f"{field_name} cannot be empty."
            )

        if len(value) > 20:
            raise ValueError(
                f"{field_name} is too long."
            )

        return value

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_interval(
        interval: str,
    ) -> str:
        if not isinstance(interval, str):
            raise ValueError(
                "interval must be a string."
            )

        interval = (
            interval
            .strip()
        )

        if not interval:
            raise ValueError(
                "interval cannot be empty."
            )

        return interval

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_unit(
        unit: str,
    ) -> str:
        if not isinstance(unit, str):
            raise ValueError(
                "unit must be a string."
            )

        unit = (
            unit
            .strip()
            .lower()
        )

        allowed_units = {
            "gram",
            "oz",
            "kg",
        }

        if unit not in allowed_units:
            raise ValueError(
                "unit must be one of: gram, oz, kg."
            )

        return unit

    # ------------------------------------------------------------------

    @staticmethod
    def _validate_amount(
        amount: float,
    ) -> float:
        try:
            amount = float(
                amount
            )

        except (TypeError, ValueError) as exc:
            raise ValueError(
                "amount must be numeric."
            ) from exc

        if amount <= 0:
            raise ValueError(
                "amount must be greater than 0."
            )

        return amount

    # ==================================================================
    # Provider response parsing
    # ==================================================================

    @staticmethod
    def _required_string(
        value: Any,
        field_name: str,
    ) -> str:
        if value is None:
            raise GoldPriceAPIResponseError(
                "GoldPrice.dev response is missing "
                f"'{field_name}'."
            )

        text = str(
            value
        ).strip()

        if not text:
            raise GoldPriceAPIResponseError(
                "GoldPrice.dev response contains empty "
                f"'{field_name}'."
            )

        return text

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_non_negative_float(
        value: Any,
        field_name: str,
    ) -> float:
        try:
            number = float(
                value
            )

        except (TypeError, ValueError) as exc:
            raise GoldPriceAPIResponseError(
                "Invalid numeric value for "
                f"'{field_name}': {value!r}"
            ) from exc

        if number < 0:
            raise GoldPriceAPIResponseError(
                f"'{field_name}' cannot be negative."
            )

        return number

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_optional_float(
        value: Any,
        field_name: str,
    ) -> float | None:
        if value is None:
            return None

        try:
            number = float(
                value
            )

        except (TypeError, ValueError) as exc:
            raise GoldPriceAPIResponseError(
                "Invalid numeric value for "
                f"'{field_name}': {value!r}"
            ) from exc

        if number < 0:
            raise GoldPriceAPIResponseError(
                f"'{field_name}' cannot be negative."
            )

        return number

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        # Python 3.10.1 requires normalization of
        # variable-length fractional seconds.
        import re

        match = re.fullmatch(
            r"(.+?\.)(\d+)(Z|[+-]\d{2}:\d{2})?",
            text,
        )

        if match:
            prefix, fraction, timezone = match.groups()

            # Pad to six digits, or truncate excess precision.
            fraction = fraction[:6].ljust(6, "0")

            text = (
                prefix
                + fraction
                + (timezone or "")
            )

        try:
            return datetime.fromisoformat(text)

        except ValueError as exc:
            raise GoldPriceAPIResponseError(
                "Invalid GoldPrice.dev timestamp: "
                f"{value!r}"
            ) from exc

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_input_date(
        value: str,
    ) -> date:
        if not isinstance(value, str):
            raise ValueError(
                "Date must be a string."
            )

        value = (
            value
            .strip()
        )

        if not value:
            raise ValueError(
                "Date cannot be empty."
            )

        supported_formats = (
            "%Y-%m-%d",
            "%d-%m-%Y",
        )

        for date_format in supported_formats:
            try:
                return datetime.strptime(
                    value,
                    date_format,
                ).date()

            except ValueError:
                continue

        raise ValueError(
            f"Invalid date '{value}'. "
            "Use YYYY-MM-DD or DD-MM-YYYY."
        )