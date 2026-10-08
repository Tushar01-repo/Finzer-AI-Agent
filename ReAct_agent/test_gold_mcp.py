from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ======================================================================
# Expected MCP tools
# ======================================================================

EXPECTED_TOOLS = {
    "gold_spot_price",
    "gold_carat_prices",
    "gold_price_history",
    "gold_conversion",
}


# ======================================================================
# Helpers
# ======================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def extract_structured_result(
    result: Any,
) -> dict[str, Any]:
    """
    Extract Finzer's structured dictionary response from an MCP result.

    With structured_output=False, MCP normally serializes the returned
    dictionary into TextContent as JSON.

    This helper also supports structured_content so the test remains
    compatible if the server configuration changes later.
    """

    # ------------------------------------------------------------------
    # First try structured_content
    # ------------------------------------------------------------------

    structured_content = getattr(
        result,
        "structured_content",
        None,
    )

    # Compatibility with SDKs that may expose camelCase.
    if structured_content is None:
        structured_content = getattr(
            result,
            "structuredContent",
            None,
        )

    if structured_content is not None:
        if isinstance(
            structured_content,
            dict,
        ):
            # Some MCP configurations may wrap the actual result.
            if (
                set(structured_content.keys())
                == {"result"}
                and isinstance(
                    structured_content["result"],
                    dict,
                )
            ):
                return structured_content["result"]

            return structured_content

    # ------------------------------------------------------------------
    # Fall back to TextContent
    # ------------------------------------------------------------------

    content = getattr(
        result,
        "content",
        None,
    )

    if not content:
        raise AssertionError(
            "MCP tool returned neither structured content "
            "nor text content."
        )

    for item in content:
        text = getattr(
            item,
            "text",
            None,
        )

        if not text:
            continue

        try:
            parsed = json.loads(text)

        except json.JSONDecodeError:
            continue

        if isinstance(
            parsed,
            dict,
        ):
            return parsed

    raise AssertionError(
        "Unable to extract structured JSON "
        "from MCP tool result."
    )


def assert_mcp_transport_success(
    result: Any,
    test_name: str,
) -> None:
    """
    Verify that MCP itself successfully executed the tool.

    Finzer business/provider errors are returned as normal structured
    ToolResponse payloads and therefore should NOT set is_error=True.
    """

    is_error = getattr(
        result,
        "is_error",
        False,
    )

    assert not is_error, (
        f"{test_name}: MCP returned is_error=True.\n"
        f"Result: {result}"
    )


# ======================================================================
# Main protocol test
# ======================================================================


async def main() -> None:
    print_header(
        "FINZER - GOLD MCP PROTOCOL TEST"
    )

    # ==================================================================
    # MCP subprocess environment
    # ==================================================================

    print()
    print("[0] MCP subprocess environment")

    server_env = os.environ.copy()

    api_key_available = bool(
        server_env.get(
            "GOLDPRICE_API_KEY"
        )
    )

    print(
        "Python:",
        sys.executable,
    )

    print(
        "GOLDPRICE_API_KEY available:",
        api_key_available,
    )

    # Never print the actual API key.
    assert api_key_available, (
        "GOLDPRICE_API_KEY is not available "
        "to the MCP test process."
    )

    print("PASS")

    # ==================================================================
    # Server configuration
    # ==================================================================

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "app.mcp_servers.gold.server",
        ],
        env=server_env,
    )

    # ==================================================================
    # Start MCP server subprocess
    # ==================================================================

    async with stdio_client(
        server_params
    ) as (
        read_stream,
        write_stream,
    ):

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            # ==========================================================
            # TEST 1 - Initialize
            # ==========================================================

            print()
            print("[1] MCP initialize")

            initialize_result = (
                await session.initialize()
            )

            assert (
                initialize_result
                is not None
            )

            print("PASS")

            print(
                "Server:",
                initialize_result.server_info.name,
            )

            # ==========================================================
            # TEST 2 - tools/list
            # ==========================================================

            print()
            print("[2] tools/list")

            tools_result = (
                await session.list_tools()
            )

            discovered_tools = {
                tool.name
                for tool in tools_result.tools
            }

            print(
                "Discovered:",
                sorted(
                    discovered_tools
                ),
            )

            missing_tools = (
                EXPECTED_TOOLS
                - discovered_tools
            )

            assert not missing_tools, (
                "Missing expected Gold MCP tools: "
                f"{sorted(missing_tools)}"
            )

            print("PASS")

            # ==========================================================
            # TEST 3 - Spot price
            # ==========================================================

            print()
            print(
                "[3] gold_spot_price - INR"
            )

            result = await session.call_tool(
                "gold_spot_price",
                {
                    "currency": "INR",
                },
            )

            assert_mcp_transport_success(
                result,
                "gold_spot_price",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "success"
            ), payload

            assert (
                payload.get("error")
                is None
            )

            data = payload.get(
                "data"
            )

            assert isinstance(
                data,
                dict,
            )

            assert (
                data.get("symbol")
                == "XAU"
            )

            assert (
                data.get("currency")
                == "INR"
            )

            assert (
                data.get(
                    "price_per_ounce",
                    0,
                )
                > 0
            )

            assert (
                data.get(
                    "price_per_gram",
                    0,
                )
                > 0
            )

            print(
                "Price per ounce:",
                data["price_per_ounce"],
            )

            print(
                "Price per gram:",
                data["price_per_gram"],
            )

            print(
                "Timestamp:",
                data.get("timestamp"),
            )

            print("PASS")

            # ==========================================================
            # TEST 4 - Carat prices
            # ==========================================================

            print()
            print(
                "[4] gold_carat_prices - INR"
            )

            result = await session.call_tool(
                "gold_carat_prices",
                {
                    "currency": "INR",
                },
            )

            assert_mcp_transport_success(
                result,
                "gold_carat_prices",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "success"
            ), payload

            assert (
                payload.get("error")
                is None
            )

            data = payload.get(
                "data"
            )

            assert isinstance(
                data,
                dict,
            )

            assert (
                data.get("currency")
                == "INR"
            )

            prices = data.get(
                "prices"
            )

            assert isinstance(
                prices,
                list,
            )

            assert prices

            carats = {
                item.get("carat")
                for item in prices
                if isinstance(
                    item,
                    dict,
                )
            }

            assert 24 in carats
            assert 22 in carats

            print(
                "Carats:",
                sorted(
                    carats,
                    reverse=True,
                ),
            )

            price_24k = next(
                (
                    item
                    for item in prices
                    if item.get("carat")
                    == 24
                ),
                None,
            )

            if price_24k:
                print(
                    "24K price per gram:",
                    price_24k.get(
                        "price_per_gram"
                    ),
                )

            print("PASS")

            # ==========================================================
            # TEST 5 - Historical prices
            # ==========================================================

            print()
            print(
                "[5] gold_price_history"
            )

            result = await session.call_tool(
                "gold_price_history",
                {
                    "start_date":
                        "2026-09-03",
                    "end_date":
                        "2026-09-05",
                    "interval":
                        "1d",
                    "currency":
                        "USD",
                },
            )

            assert_mcp_transport_success(
                result,
                "gold_price_history",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "success"
            ), payload

            assert (
                payload.get("error")
                is None
            )

            data = payload.get(
                "data"
            )

            assert isinstance(
                data,
                dict,
            )

            assert (
                data.get("currency")
                == "USD"
            )

            assert (
                data.get("start_date")
                == "2026-09-03"
            )

            assert (
                data.get("end_date")
                == "2026-09-05"
            )

            assert (
                data.get("interval")
                == "1d"
            )

            observations = data.get(
                "observations"
            )

            assert isinstance(
                observations,
                list,
            )

            assert (
                data.get("count")
                == len(
                    observations
                )
            )

            print(
                "Observations:",
                len(
                    observations
                ),
            )

            if observations:
                print(
                    "First observation:",
                    observations[0],
                )

            print("PASS")

            # ==========================================================
            # TEST 6 - Gold conversion
            # ==========================================================

            print()
            print(
                "[6] gold_conversion"
            )

            result = await session.call_tool(
                "gold_conversion",
                {
                    "amount": 10,
                    "from_symbol": "XAU",
                    "to_symbol": "INR",
                    "unit": "gram",
                },
            )

            assert_mcp_transport_success(
                result,
                "gold_conversion",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "success"
            ), payload

            assert (
                payload.get("error")
                is None
            )

            data = payload.get(
                "data"
            )

            assert isinstance(
                data,
                dict,
            )

            assert (
                data.get("from_symbol")
                == "XAU"
            )

            assert (
                data.get("to_symbol")
                == "INR"
            )

            assert (
                data.get("amount")
                == 10
            )

            assert (
                data.get("unit")
                == "gram"
            )

            assert (
                data.get(
                    "converted_value",
                    0,
                )
                > 0
            )

            print(
                "Converted value:",
                data["converted_value"],
            )

            print(
                "Rate:",
                data.get("rate"),
            )

            print("PASS")

            # ==========================================================
            # TEST 7 - Invalid currency
            # ==========================================================

            print()
            print(
                "[7] invalid currency "
                "- structured error"
            )

            result = await session.call_tool(
                "gold_spot_price",
                {
                    "currency": "IN",
                },
            )

            # Finzer validation errors are business-level structured
            # responses, not MCP transport errors.
            assert_mcp_transport_success(
                result,
                "invalid currency",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "error"
            ), payload

            assert (
                payload.get("data")
                is None
            )

            error = payload.get(
                "error"
            )

            assert isinstance(
                error,
                dict,
            )

            assert (
                error.get("type")
                == "VALIDATION_ERROR"
            )

            assert (
                error.get("retryable")
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error.get("message"),
            )

            print("PASS")

            # ==========================================================
            # TEST 8 - Reversed historical range
            # ==========================================================

            print()
            print(
                "[8] reversed historical range"
            )

            result = await session.call_tool(
                "gold_price_history",
                {
                    "start_date":
                        "2026-09-05",
                    "end_date":
                        "2026-09-03",
                    "interval":
                        "1d",
                    "currency":
                        "USD",
                },
            )

            assert_mcp_transport_success(
                result,
                "reversed historical range",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "error"
            ), payload

            error = payload.get(
                "error"
            )

            assert isinstance(
                error,
                dict,
            )

            assert (
                error.get("type")
                == "VALIDATION_ERROR"
            )

            assert (
                error.get("retryable")
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error.get("message"),
            )

            print("PASS")

            # ==========================================================
            # TEST 9 - Invalid amount
            # ==========================================================

            print()
            print(
                "[9] invalid conversion amount"
            )

            result = await session.call_tool(
                "gold_conversion",
                {
                    "amount": -10,
                    "from_symbol": "XAU",
                    "to_symbol": "INR",
                    "unit": "gram",
                },
            )

            assert_mcp_transport_success(
                result,
                "invalid conversion amount",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "error"
            ), payload

            error = payload.get(
                "error"
            )

            assert isinstance(
                error,
                dict,
            )

            assert (
                error.get("type")
                == "VALIDATION_ERROR"
            )

            assert (
                error.get("retryable")
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error.get("message"),
            )

            print("PASS")

            # ==========================================================
            # TEST 10 - Invalid unit
            # ==========================================================

            print()
            print(
                "[10] invalid conversion unit"
            )

            result = await session.call_tool(
                "gold_conversion",
                {
                    "amount": 10,
                    "from_symbol": "XAU",
                    "to_symbol": "INR",
                    "unit": "pound",
                },
            )

            assert_mcp_transport_success(
                result,
                "invalid conversion unit",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "error"
            ), payload

            error = payload.get(
                "error"
            )

            assert isinstance(
                error,
                dict,
            )

            assert (
                error.get("type")
                == "VALIDATION_ERROR"
            )

            assert (
                error.get("retryable")
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error.get("message"),
            )

            print("PASS")

            # ==========================================================
            # TEST 11 - Free plan historical restriction
            # ==========================================================

            print()
            print(
                "[11] historical plan restriction"
            )

            result = await session.call_tool(
                "gold_price_history",
                {
                    "start_date":
                        "2026-09-01",
                    "end_date":
                        "2026-09-05",
                    "interval":
                        "1d",
                    "currency":
                        "USD",
                },
            )

            assert_mcp_transport_success(
                result,
                "historical plan restriction",
            )

            payload = extract_structured_result(
                result
            )

            assert (
                payload.get("status")
                == "error"
            ), payload

            error = payload.get(
                "error"
            )

            assert isinstance(
                error,
                dict,
            )

            assert (
                error.get("type")
                == "PLAN_RESTRICTED"
            )

            assert (
                error.get("retryable")
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error.get("message"),
            )

            print("PASS")

    # ==================================================================
    # Finished
    # ==================================================================

    print_header(
        "ALL GOLD MCP PROTOCOL TESTS PASSED"
    )


# ======================================================================
# Entrypoint
# ======================================================================


if __name__ == "__main__":
    asyncio.run(
        main()
    )