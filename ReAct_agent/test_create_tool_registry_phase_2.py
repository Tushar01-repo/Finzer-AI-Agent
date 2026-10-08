from __future__ import annotations

from app.tools.contracts import (
    ApprovalPolicy,
    ToolOperation,
    ToolRisk,
    ToolSource,
    ToolTransport,
)
from app.tools.document_rag import DocumentRAGTool
from app.tools.news_rag import NewsRAGTool
from app.tools.registry import (
    TOOL_REGISTRY,
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


EXPECTED_MUTUAL_FUND_TOOLS = {
    "search_mutual_funds",
    "get_mutual_fund_details",
    "get_latest_nav",
    "get_nav_history",
}

EXPECTED_GOLD_TOOLS = {
    "gold_spot_price",
    "gold_carat_prices",
    "gold_price_history",
    "gold_conversion",
}

EXPECTED_WISHLIST_TOOLS = {
    "wishlist_get",
    "wishlist_check",
    "wishlist_add",
    "wishlist_remove",
}

EXPECTED_RAG_TOOLS = {
    "document_rag",
    "news_rag",
}


def names(contracts) -> set[str]:
    return {
        contract.name
        for contract in contracts
    }


def test_registry_contains_14_tools():
    assert len(TOOL_REGISTRY) == 14


def test_registry_internal_validation():
    validate_tool_registry()


def test_mutual_fund_registry():
    actual = names(
        get_tools_by_source(
            ToolSource.MUTUAL_FUND
        )
    )

    assert actual == EXPECTED_MUTUAL_FUND_TOOLS


def test_gold_registry():
    actual = names(
        get_tools_by_source(
            ToolSource.GOLD
        )
    )

    assert actual == EXPECTED_GOLD_TOOLS


def test_wishlist_registry():
    actual = names(
        get_tools_by_source(
            ToolSource.WISHLIST
        )
    )

    assert actual == EXPECTED_WISHLIST_TOOLS


def test_document_rag_registry():
    contracts = get_tools_by_source(
        ToolSource.DOCUMENT_RAG
    )

    assert len(contracts) == 1

    contract = contracts[0]

    assert contract.name == "document_rag"
    assert contract.transport == ToolTransport.LOCAL
    assert contract.operation == ToolOperation.READ
    assert contract.risk == ToolRisk.LOW
    assert contract.approval == ApprovalPolicy.NEVER

    assert contract.server_name is None
    assert contract.requires_user_context is False
    assert contract.returns_evidence is True


def test_news_rag_registry():
    contracts = get_tools_by_source(
        ToolSource.NEWS_RAG
    )

    assert len(contracts) == 1

    contract = contracts[0]

    assert contract.name == "news_rag"
    assert contract.transport == ToolTransport.LOCAL
    assert contract.operation == ToolOperation.READ
    assert contract.risk == ToolRisk.LOW
    assert contract.approval == ApprovalPolicy.NEVER

    assert contract.server_name is None
    assert contract.requires_user_context is False
    assert contract.returns_evidence is True


def test_rag_implementations_exist():
    """
    Registry names must correspond to real agent-facing
    implementations.
    """

    assert DocumentRAGTool is not None
    assert NewsRAGTool is not None

    assert tool_exists("document_rag")
    assert tool_exists("news_rag")


def test_read_write_counts():
    read_tools = get_read_tools()
    write_tools = get_write_tools()

    assert len(read_tools) == 12
    assert len(write_tools) == 2

    assert names(write_tools) == {
        "wishlist_add",
        "wishlist_remove",
    }


def test_only_wishlist_writes_can_require_approval():
    approval_tools = get_approval_capable_tools()

    assert names(approval_tools) == {
        "wishlist_add",
        "wishlist_remove",
    }

    for contract in approval_tools:
        assert contract.operation == ToolOperation.WRITE
        assert contract.approval == ApprovalPolicy.CONDITIONAL


def test_user_context_tools():
    context_tools = get_tools_requiring_user_context()

    assert names(context_tools) == {
        "wishlist_get",
        "wishlist_check",
        "wishlist_add",
        "wishlist_remove",
    }


def test_evidence_tools():
    evidence_tools = get_evidence_tools()

    expected = (
        EXPECTED_MUTUAL_FUND_TOOLS
        | EXPECTED_GOLD_TOOLS
        | EXPECTED_RAG_TOOLS
    )

    assert names(evidence_tools) == expected

    assert len(evidence_tools) == 10


def test_rag_tools_are_read_only_and_no_approval():
    for tool_name in (
        "document_rag",
        "news_rag",
    ):
        contract = require_tool_contract(
            tool_name
        )

        assert contract.transport == ToolTransport.LOCAL
        assert contract.operation == ToolOperation.READ
        assert contract.approval == ApprovalPolicy.NEVER
        assert contract.returns_evidence is True


def test_unknown_tool():
    assert tool_exists(
        "definitely_not_a_real_tool"
    ) is False

    try:
        require_tool_contract(
            "definitely_not_a_real_tool"
        )
    except KeyError:
        pass
    else:
        raise AssertionError(
            "Unknown tool should raise KeyError."
        )