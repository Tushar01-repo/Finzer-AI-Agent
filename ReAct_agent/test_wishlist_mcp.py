from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "wishlist_get",
    "wishlist_check",
    "wishlist_add",
    "wishlist_remove",
}

TEST_USER_ID = "wishlist_mcp_test_user"
TEST_ASSET_TYPE = "MUTUAL_FUND"
TEST_ASSET_ID = "125497"
TEST_ASSET_NAME = "SBI Small Cap Fund - Direct Plan - Growth"


# ======================================================================
# Helpers
# ======================================================================


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def assert_mcp_success(
    result: Any,
    test_name: str,
) -> None:
    assert not getattr(result, "is_error", False), (
        f"{test_name}: MCP returned is_error=True.\n"
        f"Result: {result}"
    )


def extract_payload(
    result: Any,
) -> dict[str, Any]:
    """
    Extract the JSON dictionary returned by the MCP tool.

    structured_output=False means our server normally returns the
    dictionary as JSON inside TextContent.
    """

    structured_content = getattr(
        result,
        "structured_content",
        None,
    )

    if structured_content is None:
        structured_content = getattr(
            result,
            "structuredContent",
            None,
        )

    if isinstance(structured_content, dict):
        if (
            set(structured_content.keys()) == {"result"}
            and isinstance(
                structured_content["result"],
                dict,
            )
        ):
            return structured_content["result"]

        return structured_content

    content = getattr(
        result,
        "content",
        None,
    )

    assert content, (
        "MCP result contains no content."
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
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            return payload

    raise AssertionError(
        "Unable to extract JSON payload "
        "from MCP result."
    )


# ======================================================================
# Test
# ======================================================================


async def main() -> None:
    header(
        "FINZER - WISHLIST MCP PROTOCOL TEST"
    )

    # ==================================================================
    # Environment
    # ==================================================================

    print()
    print("[0] MCP subprocess environment")

    server_env = os.environ.copy()

    database_available = bool(
        server_env.get("DATABASE_URL")
    )

    env_file = server_env.get(
        "FINZER_ENV_FILE"
    )

    print(
        "Python:",
        sys.executable,
    )

    print(
        "DATABASE_URL directly available:",
        database_available,
    )

    print(
        "FINZER_ENV_FILE available:",
        bool(env_file),
    )

    # One of these must be available.
    assert database_available or env_file, (
        "Neither DATABASE_URL nor FINZER_ENV_FILE "
        "is available to the MCP subprocess."
    )

    print("PASS")

    # ==================================================================
    # MCP subprocess
    # ==================================================================

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "app.mcp_servers.wishlist.server",
        ],
        env=server_env,
    )

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
            # 1. Initialize
            # ==========================================================

            print()
            print("[1] MCP initialize")

            initialization = (
                await session.initialize()
            )

            assert initialization is not None

            print(
                "Server:",
                initialization.server_info.name,
            )

            assert (
                initialization.server_info.name
                == "finzer-wishlist-mcp"
            )

            print("PASS")

            # ==========================================================
            # 2. tools/list
            # ==========================================================

            print()
            print("[2] tools/list")

            tools_result = (
                await session.list_tools()
            )

            discovered = {
                tool.name
                for tool in tools_result.tools
            }

            print(
                "Discovered:",
                sorted(discovered),
            )

            missing = (
                EXPECTED_TOOLS
                - discovered
            )

            assert not missing, (
                f"Missing MCP tools: {sorted(missing)}"
            )

            print("PASS")

            # ==========================================================
            # Cleanup before test
            # ==========================================================

            cleanup = await session.call_tool(
                "wishlist_remove",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                cleanup,
                "initial cleanup",
            )

            # ==========================================================
            # 3. Empty wishlist
            # ==========================================================

            print()
            print("[3] wishlist_get - empty")

            result = await session.call_tool(
                "wishlist_get",
                {
                    "user_id": TEST_USER_ID,
                },
            )

            assert_mcp_success(
                result,
                "wishlist_get",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"
            assert payload["error"] is None

            data = payload["data"]

            assert data["count"] == 0
            assert data["items"] == []

            print(
                "Count:",
                data["count"],
            )

            print("PASS")

            # ==========================================================
            # 4. Check absent
            # ==========================================================

            print()
            print("[4] wishlist_check - absent")

            result = await session.call_tool(
                "wishlist_check",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "wishlist_check",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["exists"] is False
            assert data["item"] is None

            print(
                "Exists:",
                data["exists"],
            )

            print("PASS")

            # ==========================================================
            # 5. Add
            # ==========================================================

            print()
            print("[5] wishlist_add")

            result = await session.call_tool(
                "wishlist_add",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                    "asset_name": TEST_ASSET_NAME,
                    "metadata": {
                        "scheme_code": TEST_ASSET_ID,
                        "plan": "DIRECT",
                        "option": "GROWTH",
                        "source": "mfapi",
                    },
                },
            )

            assert_mcp_success(
                result,
                "wishlist_add",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"
            assert payload["error"] is None

            data = payload["data"]

            assert data["created"] is True

            item = data["item"]

            assert item["user_id"] == TEST_USER_ID
            assert item["asset_type"] == TEST_ASSET_TYPE
            assert item["asset_id"] == TEST_ASSET_ID

            wishlist_id = item["wishlist_id"]

            print(
                "wishlist_id:",
                wishlist_id,
            )

            print(
                "created:",
                data["created"],
            )

            print("PASS")

            # ==========================================================
            # 6. Check present
            # ==========================================================

            print()
            print("[6] wishlist_check - present")

            result = await session.call_tool(
                "wishlist_check",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "wishlist_check present",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["exists"] is True
            assert data["item"] is not None

            assert (
                data["item"]["wishlist_id"]
                == wishlist_id
            )

            print(
                "Exists:",
                data["exists"],
            )

            print("PASS")

            # ==========================================================
            # 7. Get populated wishlist
            # ==========================================================

            print()
            print("[7] wishlist_get - populated")

            result = await session.call_tool(
                "wishlist_get",
                {
                    "user_id": TEST_USER_ID,
                },
            )

            assert_mcp_success(
                result,
                "wishlist_get populated",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["count"] == 1
            assert len(data["items"]) == 1

            assert (
                data["items"][0]["asset_id"]
                == TEST_ASSET_ID
            )

            print(
                "Count:",
                data["count"],
            )

            print(
                "Asset:",
                data["items"][0]["asset_name"],
            )

            print("PASS")

            # ==========================================================
            # 8. Duplicate add
            # ==========================================================

            print()
            print(
                "[8] wishlist_add - idempotency"
            )

            result = await session.call_tool(
                "wishlist_add",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": "mutual_fund",
                    "asset_id": TEST_ASSET_ID,
                    "asset_name": TEST_ASSET_NAME,
                    "metadata": {
                        "scheme_code": TEST_ASSET_ID,
                    },
                },
            )

            assert_mcp_success(
                result,
                "duplicate wishlist_add",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["created"] is False

            assert (
                data["item"]["wishlist_id"]
                == wishlist_id
            )

            print(
                "created:",
                data["created"],
            )

            print("PASS")

            # ==========================================================
            # 9. Asset type normalization
            # ==========================================================

            print()
            print("[9] asset_type normalization")

            result = await session.call_tool(
                "wishlist_check",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": "mutual_fund",
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "asset normalization",
            )

            payload = extract_payload(result)

            data = payload["data"]

            assert data["exists"] is True

            assert (
                data["asset_type"]
                == "MUTUAL_FUND"
            )

            print(
                "Normalized:",
                data["asset_type"],
            )

            print("PASS")

            # ==========================================================
            # 10. Structured validation error
            # ==========================================================

            print()
            print(
                "[10] validation error - empty user_id"
            )

            result = await session.call_tool(
                "wishlist_get",
                {
                    "user_id": "",
                },
            )

            # This is a Finzer business validation error,
            # not an MCP transport failure.
            assert_mcp_success(
                result,
                "wishlist validation",
            )

            payload = extract_payload(result)

            assert payload["status"] == "error"
            assert payload["data"] is None

            error = payload["error"]

            assert (
                error["type"]
                == "VALIDATION_ERROR"
            )

            assert (
                error["retryable"]
                is False
            )

            print(
                "Error type:",
                error["type"],
            )

            print(
                "Message:",
                error["message"],
            )

            print("PASS")

            # ==========================================================
            # 11. Remove
            # ==========================================================

            print()
            print("[11] wishlist_remove")

            result = await session.call_tool(
                "wishlist_remove",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "wishlist_remove",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["removed"] is True

            print(
                "removed:",
                data["removed"],
            )

            print("PASS")

            # ==========================================================
            # 12. Verify removed
            # ==========================================================

            print()
            print("[12] verify removed")

            result = await session.call_tool(
                "wishlist_check",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "verify removal",
            )

            payload = extract_payload(result)

            data = payload["data"]

            assert data["exists"] is False
            assert data["item"] is None

            print(
                "Exists:",
                data["exists"],
            )

            print("PASS")

            # ==========================================================
            # 13. Duplicate remove
            # ==========================================================

            print()
            print(
                "[13] wishlist_remove - idempotency"
            )

            result = await session.call_tool(
                "wishlist_remove",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

            assert_mcp_success(
                result,
                "duplicate wishlist_remove",
            )

            payload = extract_payload(result)

            assert payload["status"] == "success"

            data = payload["data"]

            assert data["removed"] is False

            print(
                "removed:",
                data["removed"],
            )

            print("PASS")

            # ==========================================================
            # Final cleanup
            # ==========================================================

            await session.call_tool(
                "wishlist_remove",
                {
                    "user_id": TEST_USER_ID,
                    "asset_type": TEST_ASSET_TYPE,
                    "asset_id": TEST_ASSET_ID,
                },
            )

    header(
        "ALL WISHLIST MCP PROTOCOL TESTS PASSED"
    )


if __name__ == "__main__":
    asyncio.run(main())