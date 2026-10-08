from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import ValidationError

from app.mcp_servers.gold.client import (
    GoldPriceAPIAuthError,
    GoldPriceAPIError,
    GoldPriceAPINotFoundError,
    GoldPriceAPIPlanError,
    GoldPriceAPIResponseError,
    GoldPriceAPITimeoutError,
    GoldPriceClient,
)
from app.mcp_servers.gold.models import (
    ConvertGoldInput,
    GetGoldCaratPricesInput,
    GetGoldPriceHistoryInput,
    GetGoldSpotPriceInput,
    GoldCaratPrices,
    GoldConversion,
    GoldPriceHistory,
    GoldSpotPrice,
    ToolError,
    ToolResponse,
)


T = TypeVar("T")


# ======================================================================
# Client factory
# ======================================================================


def _create_client() -> GoldPriceClient:
    """
    Create the GoldPrice.dev client.

    Keeping client creation behind a function makes this layer easier
    to unit-test later by mocking or replacing the client factory.
    """

    return GoldPriceClient()


# ======================================================================
# Error helpers
# ======================================================================


def _error_response(
    error_type: str,
    message: str,
    retryable: bool = False,
) -> ToolResponse[Any]:
    """
    Build a consistent structured error response.
    """

    return ToolResponse(
        status="error",
        data=None,
        error=ToolError(
            type=error_type,
            message=message,
            retryable=retryable,
        ),
        provider="goldprice.dev",
    )


def _validation_error_response(
    exc: Exception,
) -> ToolResponse[Any]:
    """
    Convert input/Pydantic validation failures into a safe tool error.
    """

    if isinstance(exc, ValidationError):
        messages: list[str] = []

        for error in exc.errors():
            location = ".".join(
                str(part)
                for part in error.get("loc", [])
            )

            message = str(
                error.get(
                    "msg",
                    "Invalid value.",
                )
            )

            if location:
                messages.append(
                    f"{location}: {message}"
                )
            else:
                messages.append(message)

        final_message = "; ".join(messages)

        if not final_message:
            final_message = "Invalid tool input."

    else:
        final_message = str(exc).strip()

        if not final_message:
            final_message = "Invalid tool input."

    return _error_response(
        error_type="VALIDATION_ERROR",
        message=final_message,
        retryable=False,
    )


def _provider_error_response(
    exc: Exception,
) -> ToolResponse[Any]:
    """
    Map low-level GoldPrice.dev exceptions into stable tool errors.

    These error types are what the ReAct layer should reason about.
    """

    if isinstance(exc, GoldPriceAPIPlanError):
        return _error_response(
            error_type="PLAN_RESTRICTED",
            message=str(exc),
            retryable=False,
        )

    if isinstance(exc, GoldPriceAPIAuthError):
        return _error_response(
            error_type="AUTHENTICATION_ERROR",
            message="Gold price provider authentication failed.",
            retryable=False,
        )

    if isinstance(exc, GoldPriceAPINotFoundError):
        return _error_response(
            error_type="NOT_FOUND",
            message=str(exc),
            retryable=False,
        )

    if isinstance(exc, GoldPriceAPITimeoutError):
        return _error_response(
            error_type="PROVIDER_TIMEOUT",
            message=str(exc),
            retryable=True,
        )

    if isinstance(exc, GoldPriceAPIResponseError):
        return _error_response(
            error_type="INVALID_PROVIDER_RESPONSE",
            message=str(exc),
            retryable=True,
        )

    if isinstance(exc, GoldPriceAPIError):
        return _error_response(
            error_type="PROVIDER_ERROR",
            message=str(exc),
            retryable=True,
        )

    return _error_response(
        error_type="INTERNAL_ERROR",
        # message="Unexpected gold tool failure.",
        message=f"{type(exc).__name__}: {exc}",
        retryable=False,
    )


# ======================================================================
# Tool execution helper
# ======================================================================


def _execute(
    operation: Callable[[], T],
) -> ToolResponse[T]:
    """
    Execute a GoldPrice.dev operation and normalize provider errors.
    """

    try:
        result = operation()

        return ToolResponse(
            status="success",
            data=result,
            error=None,
            provider="goldprice.dev",
        )

    except (
        GoldPriceAPIPlanError,
        GoldPriceAPIAuthError,
        GoldPriceAPINotFoundError,
        GoldPriceAPITimeoutError,
        GoldPriceAPIResponseError,
        GoldPriceAPIError,
    ) as exc:
        return _provider_error_response(exc)

    except Exception:
        return _error_response(
            error_type="INTERNAL_ERROR",
            # message="Unexpected gold tool failure.",
            message=f"{type(exc).__name__}: {exc}",
            retryable=False,
        )


# ======================================================================
# Tool 1 - Spot price
# ======================================================================


def get_gold_spot_price(
    currency: str = "INR",
) -> ToolResponse[GoldSpotPrice]:
    """
    Get the current gold spot price.

    Args:
        currency:
            Three-letter quote currency such as INR or USD.
    """

    try:
        request = GetGoldSpotPriceInput(
            currency=currency
        )

    except (ValidationError, ValueError) as exc:
        return _validation_error_response(exc)

    def operation() -> GoldSpotPrice:
        client = _create_client()

        return client.get_gold_spot_price(
            currency=request.currency
        )

    return _execute(operation)


# ======================================================================
# Tool 2 - Carat prices
# ======================================================================


def get_gold_carat_prices(
    currency: str = "INR",
) -> ToolResponse[GoldCaratPrices]:
    """
    Get current per-gram gold prices by purity/carat.

    Currently normalized for the carats supplied by GoldPrice.dev,
    including 24K, 22K, 21K, 20K, 18K, 16K, 14K and 10K.

    Args:
        currency:
            Three-letter quote currency such as INR or USD.
    """

    try:
        request = GetGoldCaratPricesInput(
            currency=currency
        )

    except (ValidationError, ValueError) as exc:
        return _validation_error_response(exc)

    def operation() -> GoldCaratPrices:
        client = _create_client()

        return client.get_gold_carat_prices(
            currency=request.currency
        )

    return _execute(operation)


# ======================================================================
# Tool 3 - Historical gold prices
# ======================================================================


def get_gold_price_history(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    currency: str = "INR",
) -> ToolResponse[GoldPriceHistory]:
    """
    Get historical gold OHLC observations.

    Args:
        start_date:
            Start date, preferably YYYY-MM-DD.

        end_date:
            End date, preferably YYYY-MM-DD.

        interval:
            Provider historical bar interval such as 1d.

        currency:
            Three-letter quote currency such as INR or USD.

    Historical availability depends on the configured provider plan.
    """

    try:
        request = GetGoldPriceHistoryInput(
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            currency=currency,
        )

    except (ValidationError, ValueError) as exc:
        return _validation_error_response(exc)

    # The Pydantic model validates shape. The client performs the
    # provider-specific date parsing and start/end relationship check.
    try:
        client = _create_client()

        result = client.get_gold_price_history(
            start_date=request.start_date,
            end_date=request.end_date,
            interval=request.interval,
            currency=request.currency,
        )

        return ToolResponse(
            status="success",
            data=result,
            error=None,
            provider="goldprice.dev",
        )

    except ValueError as exc:
        return _validation_error_response(exc)

    except (
        GoldPriceAPIPlanError,
        GoldPriceAPIAuthError,
        GoldPriceAPINotFoundError,
        GoldPriceAPITimeoutError,
        GoldPriceAPIResponseError,
        GoldPriceAPIError,
    ) as exc:
        return _provider_error_response(exc)

    except Exception:
        return _error_response(
            error_type="INTERNAL_ERROR",
            # message="Unexpected gold tool failure.",
            message=f"{type(exc).__name__}: {exc}",
            retryable=False,
        )


# ======================================================================
# Tool 4 - Gold conversion
# ======================================================================


def convert_gold(
    amount: float,
    from_symbol: str,
    to_symbol: str,
    unit: str = "gram",
) -> ToolResponse[GoldConversion]:
    """
    Convert a gold/currency amount using the provider's conversion API.

    Example:

        convert_gold(
            amount=10,
            from_symbol="XAU",
            to_symbol="INR",
            unit="gram",
        )

    represents 10 grams of gold converted to INR.
    """

    try:
        request = ConvertGoldInput(
            amount=amount,
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            unit=unit,
        )

    except (ValidationError, ValueError) as exc:
        return _validation_error_response(exc)

    try:
        client = _create_client()

        result = client.convert_gold(
            amount=request.amount,
            from_symbol=request.from_symbol,
            to_symbol=request.to_symbol,
            unit=request.unit,
        )

        return ToolResponse(
            status="success",
            data=result,
            error=None,
            provider="goldprice.dev",
        )

    except ValueError as exc:
        return _validation_error_response(exc)

    except (
        GoldPriceAPIPlanError,
        GoldPriceAPIAuthError,
        GoldPriceAPINotFoundError,
        GoldPriceAPITimeoutError,
        GoldPriceAPIResponseError,
        GoldPriceAPIError,
    ) as exc:
        return _provider_error_response(exc)

    except Exception:
        return _error_response(
            error_type="INTERNAL_ERROR",
            # message="Unexpected gold tool failure.",
            message=f"{type(exc).__name__}: {exc}",
            retryable=False,
        )