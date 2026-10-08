from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ======================================================================
# Tool source
# ======================================================================


class ToolSource(str, Enum):
    """
    Logical source/provider of a tool.

    This identifies which subsystem owns the tool.
    """

    MUTUAL_FUND = "mutual_fund"
    GOLD = "gold"
    WISHLIST = "wishlist"

    # These will be used in Phase 2.
    DOCUMENT_RAG = "document_rag"
    NEWS_RAG = "news_rag"


# ======================================================================
# Operation type
# ======================================================================


class ToolOperation(str, Enum):
    """
    Describes whether execution changes application/user state.
    """

    READ = "read"
    WRITE = "write"


# ======================================================================
# Risk level
# ======================================================================


class ToolRisk(str, Enum):
    """
    Coarse risk classification used later by the execution gate.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ======================================================================
# Approval policy
# ======================================================================


class ApprovalPolicy(str, Enum):
    """
    Metadata describing whether a tool can require user approval.

    NEVER:
        The tool is safe to execute without approval.

    CONDITIONAL:
        Approval depends on conversation context.

        Example:
            User explicitly says:
                "Add SBI Small Cap to my wishlist."

            The request itself can serve as authorization.

            But an agent should not infer a wishlist mutation from:
                "I like SBI Small Cap."

    ALWAYS:
        Explicit approval must be obtained immediately before execution.

    The actual approval decision belongs to the future execution gate,
    not this contract.
    """

    NEVER = "never"
    CONDITIONAL = "conditional"
    ALWAYS = "always"


# ======================================================================
# Tool transport
# ======================================================================


class ToolTransport(str, Enum):
    """
    Mechanism used to invoke the tool.
    """

    MCP = "mcp"
    LOCAL = "local"


# ======================================================================
# Tool contract
# ======================================================================


class ToolContract(BaseModel):
    """
    Normalized metadata describing a tool available to the Finzer agent.

    This model intentionally contains policy-relevant facts but does
    not perform policy decisions.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name: str = Field(
        ...,
        min_length=1,
        description=(
            "Canonical tool name exposed to the agent."
        ),
    )

    description: str = Field(
        ...,
        min_length=1,
        description=(
            "Short description of what the tool does."
        ),
    )

    # ------------------------------------------------------------------
    # Ownership / routing
    # ------------------------------------------------------------------

    source: ToolSource

    transport: ToolTransport = ToolTransport.MCP

    server_name: str | None = Field(
        default=None,
        description=(
            "Logical MCP server name when transport=MCP."
        ),
    )

    # ------------------------------------------------------------------
    # Operation characteristics
    # ------------------------------------------------------------------

    operation: ToolOperation

    risk: ToolRisk = ToolRisk.LOW

    approval: ApprovalPolicy = ApprovalPolicy.NEVER

    idempotent: bool = Field(
        default=True,
        description=(
            "Whether repeating the same tool call is safe "
            "from an application-state perspective."
        ),
    )

    # ------------------------------------------------------------------
    # Runtime controls
    # ------------------------------------------------------------------

    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description=(
            "Maximum execution time allowed for one tool call."
        ),
    )

    max_retries: int = Field(
        default=1,
        ge=0,
        description=(
            "Maximum number of retries permitted after the "
            "initial attempt."
        ),
    )

    # ------------------------------------------------------------------
    # Agent behavior
    # ------------------------------------------------------------------

    requires_user_context: bool = Field(
        default=False,
        description=(
            "Whether execution requires authenticated/current "
            "user context."
        ),
    )

    returns_evidence: bool = Field(
        default=False,
        description=(
            "Whether the result can contribute factual evidence "
            "to the final response."
        ),
    )


# ======================================================================
# Convenience properties
# ======================================================================


def is_read_tool(
    contract: ToolContract,
) -> bool:
    return (
        contract.operation
        == ToolOperation.READ
    )


def is_write_tool(
    contract: ToolContract,
) -> bool:
    return (
        contract.operation
        == ToolOperation.WRITE
    )


def can_require_approval(
    contract: ToolContract,
) -> bool:
    return contract.approval in {
        ApprovalPolicy.CONDITIONAL,
        ApprovalPolicy.ALWAYS,
    }