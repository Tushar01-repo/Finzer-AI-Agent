from __future__ import annotations

import sys
from typing import Any

from mcp.server import MCPServer

from app.mcp_servers.gold.tools import (
    convert_gold,
    get_gold_carat_prices,
    get_gold_price_history,
    get_gold_spot_price,
)


# ======================================================================
# MCP Server
# ======================================================================

mcp = MCPServer(
    "finzer-gold-mcp"
)


# ======================================================================
# Debug helper
# ======================================================================


def _debug(message: str) -> None:
    """
    Write diagnostic information to stderr.

    IMPORTANT:
    MCP stdio transport uses stdout for protocol communication.
    Debug logging must therefore go to stderr.
    """

    print(
        f"[GOLD MCP DEBUG] {message}",
        file=sys.stderr,
        flush=True,
    )


# ======================================================================
# Tool 1 - Gold spot price
# ======================================================================


@mcp.tool(structured_output=False)
def gold_spot_price(
    currency: str = "INR",
) -> dict[str, Any]:
    """
    Get the current gold spot price.

    Args:
        currency:
            Three-letter quote currency such as INR or USD.

    Returns:
        Structured Finzer tool response containing the current
        gold price per troy ounce and per gram.
    """

    _debug(
        f"gold_spot_price called: currency={currency}"
    )

    try:
        response = get_gold_spot_price(
            currency=currency
        )

        _debug(
            "gold_spot_price service response: "
            f"status={response.status}"
        )

        payload = response.model_dump(
            mode="json"
        )

        _debug(
            f"gold_spot_price payload={payload}"
        )

        return payload

    except Exception as exc:
        _debug(
            "gold_spot_price exception: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


# ======================================================================
# Tool 2 - Gold prices by carat
# ======================================================================


@mcp.tool(structured_output=False)
def gold_carat_prices(
    currency: str = "INR",
) -> dict[str, Any]:
    """
    Get current gold prices per gram by carat/purity.

    Args:
        currency:
            Three-letter quote currency such as INR or USD.

    Returns:
        Structured Finzer tool response containing available
        gold carat prices.
    """

    _debug(
        f"gold_carat_prices called: currency={currency}"
    )

    try:
        response = get_gold_carat_prices(
            currency=currency
        )

        _debug(
            "gold_carat_prices service response: "
            f"status={response.status}"
        )

        payload = response.model_dump(
            mode="json"
        )

        _debug(
            f"gold_carat_prices payload={payload}"
        )

        return payload

    except Exception as exc:
        _debug(
            "gold_carat_prices exception: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


# ======================================================================
# Tool 3 - Historical gold prices
# ======================================================================


@mcp.tool(structured_output=False)
def gold_price_history(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    currency: str = "INR",
) -> dict[str, Any]:
    """
    Get historical gold OHLC price observations.

    Args:
        start_date:
            Beginning of the requested period.
            Recommended format: YYYY-MM-DD.

        end_date:
            End of the requested period.
            Recommended format: YYYY-MM-DD.

        interval:
            Historical bar interval such as 1d.

        currency:
            Three-letter quote currency such as INR or USD.

    Returns:
        Structured Finzer tool response containing historical
        gold OHLC observations.

    Notes:
        Historical availability depends on the configured
        GoldPrice.dev subscription tier.
    """

    _debug(
        "gold_price_history called: "
        f"start_date={start_date}, "
        f"end_date={end_date}, "
        f"interval={interval}, "
        f"currency={currency}"
    )

    try:
        response = get_gold_price_history(
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            currency=currency,
        )

        _debug(
            "gold_price_history service response: "
            f"status={response.status}"
        )

        payload = response.model_dump(
            mode="json"
        )

        _debug(
            f"gold_price_history payload={payload}"
        )

        return payload

    except Exception as exc:
        _debug(
            "gold_price_history exception: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


# ======================================================================
# Tool 4 - Gold conversion
# ======================================================================


@mcp.tool(structured_output=False)
def gold_conversion(
    amount: float,
    from_symbol: str,
    to_symbol: str,
    unit: str = "gram",
) -> dict[str, Any]:
    """
    Convert a gold or currency amount using GoldPrice.dev.

    Example:
        amount=10
        from_symbol=XAU
        to_symbol=INR
        unit=gram

    represents 10 grams of gold converted to INR.

    Args:
        amount:
            Positive amount to convert.

        from_symbol:
            Source metal/currency symbol such as XAU.

        to_symbol:
            Destination symbol such as INR or USD.

        unit:
            Gold measurement unit.
            Supported Finzer values: gram, oz, kg.

    Returns:
        Structured Finzer tool response containing the
        converted value and provider conversion rate.
    """

    _debug(
        "gold_conversion called: "
        f"amount={amount}, "
        f"from_symbol={from_symbol}, "
        f"to_symbol={to_symbol}, "
        f"unit={unit}"
    )

    try:
        response = convert_gold(
            amount=amount,
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            unit=unit,
        )

        _debug(
            "gold_conversion service response: "
            f"status={response.status}"
        )

        payload = response.model_dump(
            mode="json"
        )

        _debug(
            f"gold_conversion payload={payload}"
        )

        return payload

    except Exception as exc:
        _debug(
            "gold_conversion exception: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


# ======================================================================
# Entrypoint
# ======================================================================


if __name__ == "__main__":
    _debug(
        "Starting finzer-gold-mcp server"
    )

    mcp.run()