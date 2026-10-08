from __future__ import annotations

from app.tools.contracts import (
    ApprovalPolicy,
    ToolContract,
    ToolOperation,
    ToolRisk,
    ToolSource,
    ToolTransport,
)


# ======================================================================
# MCP server names
# ======================================================================

MUTUAL_FUND_SERVER = "finzer-mutual-fund-mcp"
GOLD_SERVER = "finzer-gold-mcp"
WISHLIST_SERVER = "finzer-wishlist-mcp"


# ======================================================================
# Tool Registry
# ======================================================================

TOOL_REGISTRY: dict[str, ToolContract] = {

    # ==================================================================
    # MUTUAL FUND MCP
    # ==================================================================

    "search_mutual_funds": ToolContract(
        name="search_mutual_funds",
        description=(
            "Search for mutual fund schemes by name or query."
        ),
        source=ToolSource.MUTUAL_FUND,
        transport=ToolTransport.MCP,
        server_name=MUTUAL_FUND_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "get_mutual_fund_details": ToolContract(
        name="get_mutual_fund_details",
        description=(
            "Get detailed information for a mutual fund "
            "using its scheme code."
        ),
        source=ToolSource.MUTUAL_FUND,
        transport=ToolTransport.MCP,
        server_name=MUTUAL_FUND_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "get_latest_nav": ToolContract(
        name="get_latest_nav",
        description=(
            "Get the latest available NAV for a mutual fund "
            "scheme."
        ),
        source=ToolSource.MUTUAL_FUND,
        transport=ToolTransport.MCP,
        server_name=MUTUAL_FUND_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "get_nav_history": ToolContract(
        name="get_nav_history",
        description=(
            "Get historical NAV observations for a mutual fund "
            "within a bounded date range."
        ),
        source=ToolSource.MUTUAL_FUND,
        transport=ToolTransport.MCP,
        server_name=MUTUAL_FUND_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    # ==================================================================
    # GOLD MCP
    # ==================================================================

    "gold_spot_price": ToolContract(
        name="gold_spot_price",
        description=(
            "Get the current gold spot price in the requested "
            "currency."
        ),
        source=ToolSource.GOLD,
        transport=ToolTransport.MCP,
        server_name=GOLD_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "gold_carat_prices": ToolContract(
        name="gold_carat_prices",
        description=(
            "Get current per-gram gold prices for supported "
            "carat purities."
        ),
        source=ToolSource.GOLD,
        transport=ToolTransport.MCP,
        server_name=GOLD_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "gold_price_history": ToolContract(
        name="gold_price_history",
        description=(
            "Get historical gold OHLC price observations for "
            "a requested date range and interval."
        ),
        source=ToolSource.GOLD,
        transport=ToolTransport.MCP,
        server_name=GOLD_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    "gold_conversion": ToolContract(
        name="gold_conversion",
        description=(
            "Convert a quantity of gold into a requested "
            "currency or supported target representation."
        ),
        source=ToolSource.GOLD,
        transport=ToolTransport.MCP,
        server_name=GOLD_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=30.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    # ==================================================================
    # WISHLIST MCP
    # ==================================================================

    "wishlist_get": ToolContract(
        name="wishlist_get",
        description=(
            "Return the assets currently stored in the user's "
            "wishlist."
        ),
        source=ToolSource.WISHLIST,
        transport=ToolTransport.MCP,
        server_name=WISHLIST_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=15.0,
        max_retries=1,
        requires_user_context=True,
        returns_evidence=False,
    ),

    "wishlist_check": ToolContract(
        name="wishlist_check",
        description=(
            "Check whether a specific asset is currently stored "
            "in the user's wishlist."
        ),
        source=ToolSource.WISHLIST,
        transport=ToolTransport.MCP,
        server_name=WISHLIST_SERVER,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=15.0,
        max_retries=1,
        requires_user_context=True,
        returns_evidence=False,
    ),

    "wishlist_add": ToolContract(
        name="wishlist_add",
        description=(
            "Add an asset to the user's wishlist."
        ),
        source=ToolSource.WISHLIST,
        transport=ToolTransport.MCP,
        server_name=WISHLIST_SERVER,
        operation=ToolOperation.WRITE,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.CONDITIONAL,
        idempotent=True,
        timeout_seconds=15.0,
        max_retries=1,
        requires_user_context=True,
        returns_evidence=False,
    ),

    "wishlist_remove": ToolContract(
        name="wishlist_remove",
        description=(
            "Remove an asset from the user's wishlist."
        ),
        source=ToolSource.WISHLIST,
        transport=ToolTransport.MCP,
        server_name=WISHLIST_SERVER,
        operation=ToolOperation.WRITE,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.CONDITIONAL,
        idempotent=True,
        timeout_seconds=15.0,
        max_retries=1,
        requires_user_context=True,
        returns_evidence=False,
    ),

    # ==================================================================
    # DOCUMENT / IPO RAG
    # ==================================================================

    "document_rag": ToolContract(
        name="document_rag",
        description=(
            "Retrieve grounded evidence from an indexed IPO or "
            "financial document using semantic vector retrieval."
        ),
        source=ToolSource.DOCUMENT_RAG,
        transport=ToolTransport.LOCAL,
        server_name=None,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=60.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),

    # ==================================================================
    # NEWS RAG
    # ==================================================================

    "news_rag": ToolContract(
        name="news_rag",
        description=(
            "Retrieve grounded financial-news evidence using "
            "semantic search with optional company and "
            "publication-date filters."
        ),
        source=ToolSource.NEWS_RAG,
        transport=ToolTransport.LOCAL,
        server_name=None,
        operation=ToolOperation.READ,
        risk=ToolRisk.LOW,
        approval=ApprovalPolicy.NEVER,
        idempotent=True,
        timeout_seconds=60.0,
        max_retries=1,
        requires_user_context=False,
        returns_evidence=True,
    ),
}


# ======================================================================
# Registry access
# ======================================================================


def get_tool_contract(
    tool_name: str,
) -> ToolContract | None:
    """
    Return the contract for a tool.

    Returns None when the tool is not registered.
    """

    return TOOL_REGISTRY.get(tool_name)


def require_tool_contract(
    tool_name: str,
) -> ToolContract:
    """
    Return a registered tool contract.

    Raises KeyError if the tool is unknown.
    """

    contract = get_tool_contract(
        tool_name
    )

    if contract is None:
        raise KeyError(
            f"Unknown tool: {tool_name}"
        )

    return contract


def tool_exists(
    tool_name: str,
) -> bool:
    return tool_name in TOOL_REGISTRY


def list_tool_contracts() -> list[ToolContract]:
    """
    Return every registered tool contract.
    """

    return list(
        TOOL_REGISTRY.values()
    )


# ======================================================================
# Filtering
# ======================================================================


def get_tools_by_source(
    source: ToolSource,
) -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.source == source
    ]


def get_read_tools() -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.operation
        == ToolOperation.READ
    ]


def get_write_tools() -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.operation
        == ToolOperation.WRITE
    ]


def get_tools_requiring_user_context(
) -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.requires_user_context
    ]


def get_evidence_tools() -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.returns_evidence
    ]


def get_approval_capable_tools(
) -> list[ToolContract]:
    return [
        contract
        for contract in TOOL_REGISTRY.values()
        if contract.approval
        != ApprovalPolicy.NEVER
    ]


# ======================================================================
# Registry validation
# ======================================================================


def validate_tool_registry() -> None:
    """
    Validate internal registry consistency.

    This catches configuration mistakes during application startup/tests.
    """

    for registry_name, contract in TOOL_REGISTRY.items():

        # --------------------------------------------------------------
        # Dictionary key must match canonical contract name
        # --------------------------------------------------------------

        if registry_name != contract.name:
            raise ValueError(
                "Tool registry key/name mismatch: "
                f"key={registry_name!r}, "
                f"name={contract.name!r}"
            )

        # --------------------------------------------------------------
        # MCP tools require a server
        # --------------------------------------------------------------

        if (
            contract.transport
            == ToolTransport.MCP
            and not contract.server_name
        ):
            raise ValueError(
                f"MCP tool {contract.name!r} "
                "does not define server_name."
            )

        # --------------------------------------------------------------
        # LOCAL tools must not declare an MCP server
        # --------------------------------------------------------------

        if (
            contract.transport
            == ToolTransport.LOCAL
            and contract.server_name is not None
        ):
            raise ValueError(
                f"LOCAL tool {contract.name!r} "
                "must not define server_name."
            )

        # --------------------------------------------------------------
        # Read operations should not require approval
        # --------------------------------------------------------------

        if (
            contract.operation
            == ToolOperation.READ
            and contract.approval
            != ApprovalPolicy.NEVER
        ):
            raise ValueError(
                f"Read tool {contract.name!r} "
                "must not require approval."
            )

        # --------------------------------------------------------------
        # ALWAYS approval only makes sense for mutations
        # --------------------------------------------------------------

        if (
            contract.approval
            == ApprovalPolicy.ALWAYS
            and contract.operation
            != ToolOperation.WRITE
        ):
            raise ValueError(
                f"Tool {contract.name!r} uses ALWAYS approval "
                "but is not a WRITE operation."
            )

        # --------------------------------------------------------------
        # Retry configuration
        # --------------------------------------------------------------

        if contract.max_retries < 0:
            raise ValueError(
                f"Tool {contract.name!r} has invalid "
                f"max_retries={contract.max_retries}."
            )

        # --------------------------------------------------------------
        # Timeout configuration
        # --------------------------------------------------------------

        if contract.timeout_seconds <= 0:
            raise ValueError(
                f"Tool {contract.name!r} has invalid "
                f"timeout_seconds={contract.timeout_seconds}."
            )