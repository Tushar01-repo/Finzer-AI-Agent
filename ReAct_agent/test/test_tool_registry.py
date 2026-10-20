from __future__ import annotations

import asyncio

from app.mcp_servers.gold.server import mcp as gold_mcp
from app.mcp_servers.mutual_fund.server import mcp as mutual_fund_mcp
from app.mcp_servers.wishlist.server import mcp as wishlist_mcp

from app.tools.contracts import (
    ApprovalPolicy,
    ToolOperation,
    ToolSource,
    ToolTransport,
)
from app.tools.registry import (
    GOLD_SERVER,
    MUTUAL_FUND_SERVER,
    TOOL_REGISTRY,
    WISHLIST_SERVER,
    get_approval_capable_tools,
    get_evidence_tools,
    get_read_tools,
    get_tools_by_source,
    get_tools_requiring_user_context,
    get_write_tools,
    require_tool_contract,
    tool_exists,
    validate_tool_registry,
)


EXPECTED_SERVER_TOOLS = {
    MUTUAL_FUND_SERVER: {
        "search_mutual_funds",
        "get_mutual_fund_details",
        "get_latest_nav",
        "get_nav_history",
    },
    GOLD_SERVER: {
        "gold_spot_price",
        "gold_carat_prices",
        "gold_price_history",
        "gold_conversion",
    },
    WISHLIST_SERVER: {
        "wishlist_get",
        "wishlist_check",
        "wishlist_add",
        "wishlist_remove",
    },
}


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


async def get_actual_tool_names(
    mcp_server,
) -> set[str]:
    tools = await mcp_server.list_tools()

    return {
        tool.name
        for tool in tools
    }


async def main() -> None:
    header(
        "FINZER - TOOL REGISTRY TEST"
    )

    # ==================================================================
    # 1. Internal validation
    # ==================================================================

    print()
    print("[1] registry internal validation")

    validate_tool_registry()

    assert len(TOOL_REGISTRY) == 12

    print(
        "Tool count:",
        len(TOOL_REGISTRY),
    )

    print("PASS")

    # ==================================================================
    # 2. Tool lookup
    # ==================================================================

    print()
    print("[2] registry lookup")

    assert tool_exists(
        "gold_spot_price"
    )

    assert tool_exists(
        "wishlist_add"
    )

    assert not tool_exists(
        "nonexistent_tool"
    )

    contract = require_tool_contract(
        "wishlist_add"
    )

    assert (
        contract.source
        == ToolSource.WISHLIST
    )

    assert (
        contract.operation
        == ToolOperation.WRITE
    )

    print(
        "wishlist_add source:",
        contract.source.value,
    )

    print(
        "wishlist_add operation:",
        contract.operation.value,
    )

    print("PASS")

    # ==================================================================
    # 3. All tools currently use MCP
    # ==================================================================

    print()
    print("[3] transport contracts")

    for contract in TOOL_REGISTRY.values():

        assert (
            contract.transport
            == ToolTransport.MCP
        )

        assert contract.server_name

    print("PASS")

    # ==================================================================
    # 4. Read/write classification
    # ==================================================================

    print()
    print("[4] READ / WRITE classification")

    read_names = {
        tool.name
        for tool in get_read_tools()
    }

    write_names = {
        tool.name
        for tool in get_write_tools()
    }

    assert len(read_names) == 10

    assert write_names == {
        "wishlist_add",
        "wishlist_remove",
    }

    assert (
        read_names
        & write_names
        == set()
    )

    assert (
        read_names
        | write_names
        == set(TOOL_REGISTRY)
    )

    print(
        "READ:",
        sorted(read_names),
    )

    print(
        "WRITE:",
        sorted(write_names),
    )

    print("PASS")

    # ==================================================================
    # 5. Approval policy
    # ==================================================================

    print()
    print("[5] approval classification")

    approval_names = {
        tool.name
        for tool in get_approval_capable_tools()
    }

    assert approval_names == {
        "wishlist_add",
        "wishlist_remove",
    }

    for name in read_names:
        assert (
            TOOL_REGISTRY[name].approval
            == ApprovalPolicy.NEVER
        )

    for name in write_names:
        assert (
            TOOL_REGISTRY[name].approval
            == ApprovalPolicy.CONDITIONAL
        )

    print(
        "Approval capable:",
        sorted(approval_names),
    )

    print("PASS")

    # ==================================================================
    # 6. User-context tools
    # ==================================================================

    print()
    print("[6] user-context classification")

    user_context_names = {
        tool.name
        for tool
        in get_tools_requiring_user_context()
    }

    assert user_context_names == {
        "wishlist_get",
        "wishlist_check",
        "wishlist_add",
        "wishlist_remove",
    }

    print(
        "User-context tools:",
        sorted(user_context_names),
    )

    print("PASS")

    # ==================================================================
    # 7. Evidence tools
    # ==================================================================

    print()
    print("[7] evidence classification")

    evidence_names = {
        tool.name
        for tool in get_evidence_tools()
    }

    expected_evidence = {
        "search_mutual_funds",
        "get_mutual_fund_details",
        "get_latest_nav",
        "get_nav_history",
        "gold_spot_price",
        "gold_carat_prices",
        "gold_price_history",
        "gold_conversion",
    }

    assert (
        evidence_names
        == expected_evidence
    )

    print(
        "Evidence tools:",
        sorted(evidence_names),
    )

    print("PASS")

    # ==================================================================
    # 8. Source classification
    # ==================================================================

    print()
    print("[8] source classification")

    mutual_fund_tools = {
        tool.name
        for tool in get_tools_by_source(
            ToolSource.MUTUAL_FUND
        )
    }

    gold_tools = {
        tool.name
        for tool in get_tools_by_source(
            ToolSource.GOLD
        )
    }

    wishlist_tools = {
        tool.name
        for tool in get_tools_by_source(
            ToolSource.WISHLIST
        )
    }

    assert (
        mutual_fund_tools
        == EXPECTED_SERVER_TOOLS[
            MUTUAL_FUND_SERVER
        ]
    )

    assert (
        gold_tools
        == EXPECTED_SERVER_TOOLS[
            GOLD_SERVER
        ]
    )

    assert (
        wishlist_tools
        == EXPECTED_SERVER_TOOLS[
            WISHLIST_SERVER
        ]
    )

    print(
        "Mutual Fund:",
        sorted(mutual_fund_tools),
    )

    print(
        "Gold:",
        sorted(gold_tools),
    )

    print(
        "Wishlist:",
        sorted(wishlist_tools),
    )

    print("PASS")

    # ==================================================================
    # 9. Discover actual Mutual Fund MCP tools
    # ==================================================================

    print()
    print(
        "[9] Mutual Fund registry ↔ MCP"
    )

    actual_mutual_fund = (
        await get_actual_tool_names(
            mutual_fund_mcp
        )
    )

    expected_mutual_fund = (
        EXPECTED_SERVER_TOOLS[
            MUTUAL_FUND_SERVER
        ]
    )

    assert (
        actual_mutual_fund
        == expected_mutual_fund
    ), (
        "Mutual Fund MCP registry mismatch.\n"
        f"Expected: {sorted(expected_mutual_fund)}\n"
        f"Actual: {sorted(actual_mutual_fund)}"
    )

    print(
        "Actual:",
        sorted(actual_mutual_fund),
    )

    print("PASS")

    # ==================================================================
    # 10. Discover actual Gold MCP tools
    # ==================================================================

    print()
    print(
        "[10] Gold registry ↔ MCP"
    )

    actual_gold = (
        await get_actual_tool_names(
            gold_mcp
        )
    )

    expected_gold = (
        EXPECTED_SERVER_TOOLS[
            GOLD_SERVER
        ]
    )

    assert (
        actual_gold
        == expected_gold
    ), (
        "Gold MCP registry mismatch.\n"
        f"Expected: {sorted(expected_gold)}\n"
        f"Actual: {sorted(actual_gold)}"
    )

    print(
        "Actual:",
        sorted(actual_gold),
    )

    print("PASS")

    # ==================================================================
    # 11. Discover actual Wishlist MCP tools
    # ==================================================================

    print()
    print(
        "[11] Wishlist registry ↔ MCP"
    )

    actual_wishlist = (
        await get_actual_tool_names(
            wishlist_mcp
        )
    )

    expected_wishlist = (
        EXPECTED_SERVER_TOOLS[
            WISHLIST_SERVER
        ]
    )

    assert (
        actual_wishlist
        == expected_wishlist
    ), (
        "Wishlist MCP registry mismatch.\n"
        f"Expected: {sorted(expected_wishlist)}\n"
        f"Actual: {sorted(actual_wishlist)}"
    )

    print(
        "Actual:",
        sorted(actual_wishlist),
    )

    print("PASS")

    # ==================================================================
    # 12. Every registry MCP tool exists on its server
    # ==================================================================

    print()
    print(
        "[12] complete registry ↔ server consistency"
    )

    actual_by_server = {
        MUTUAL_FUND_SERVER:
            actual_mutual_fund,

        GOLD_SERVER:
            actual_gold,

        WISHLIST_SERVER:
            actual_wishlist,
    }

    for (
        tool_name,
        contract,
    ) in TOOL_REGISTRY.items():

        assert contract.server_name is not None

        server_tools = actual_by_server.get(
            contract.server_name
        )

        assert server_tools is not None, (
            "Unknown MCP server in registry: "
            f"{contract.server_name}"
        )

        assert tool_name in server_tools, (
            f"Registry tool {tool_name!r} "
            f"is not exposed by "
            f"{contract.server_name!r}."
        )

    print("PASS")

    header(
        "ALL TOOL REGISTRY TESTS PASSED"
    )


if __name__ == "__main__":
    asyncio.run(main())