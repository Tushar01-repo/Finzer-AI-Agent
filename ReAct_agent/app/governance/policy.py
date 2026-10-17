
"""
Finzer AI Agent - Governance Policy Engine
Phase 5: Governance and Human-in-the-Loop

Responsibilities:
    - Evaluate tool execution permissions
    - Enforce tool registry metadata
    - Apply risk-based authorization
    - Require approval for sensitive operations
    - Deny unknown or unauthorized tools

No MCP execution or approval persistence occurs here.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.agent.state import ToolCall
from app.governance.models import (
    PolicyDecision,
    PolicyEvaluation,
)
from app.tools.contracts import (
    ApprovalPolicy,
    ToolContract,
    ToolOperation,
    ToolRisk,
)
from app.tools.registry import TOOL_REGISTRY


class GovernancePolicyEngine:
    """Evaluates authorization for proposed agent tool calls."""

    def __init__(
        self,
        *,
        registry: Mapping[str, ToolContract] | None = None,
    ) -> None:
        self._registry = (
            TOOL_REGISTRY if registry is None else registry
        )

    def evaluate(
        self,
        *,
        tool_call: ToolCall,
        user_context_available: bool = False,
        explicit_user_authorization: bool = False,
    ) -> PolicyEvaluation:
        """
        Evaluate whether a proposed tool call is authorized.

        explicit_user_authorization must originate from trusted
        application logic, not an LLM-generated claim.
        """

        contract = self._registry.get(tool_call.tool_name)

        if contract is None:
            return self._result(
                tool_call,
                PolicyDecision.DENY,
                "Tool is not registered.",
            )

        if contract.name != tool_call.tool_name:
            return self._result(
                tool_call,
                PolicyDecision.DENY,
                "Tool registry identity mismatch.",
            )

        if (
            contract.requires_user_context
            and not user_context_available
        ):
            return self._result(
                tool_call,
                PolicyDecision.DENY,
                "Required user context is unavailable.",
            )

        if contract.risk == ToolRisk.HIGH:
            if contract.operation == ToolOperation.READ:
                return self._result(
                    tool_call,
                    PolicyDecision.DENY,
                    "High-risk read operation is not permitted.",
                )

            if contract.operation == ToolOperation.WRITE:
                if contract.approval == ApprovalPolicy.NEVER:
                    return self._result(
                        tool_call,
                        PolicyDecision.DENY,
                        "High-risk write has no approval policy.",
                    )

                return self._result(
                    tool_call,
                    PolicyDecision.REQUIRE_APPROVAL,
                    "High-risk write requires human approval.",
                )

        if contract.operation == ToolOperation.READ:
            if contract.approval != ApprovalPolicy.NEVER:
                return self._result(
                    tool_call,
                    PolicyDecision.DENY,
                    "Read tool has inconsistent approval policy.",
                )

            return self._result(
                tool_call,
                PolicyDecision.ALLOW,
                "Registered read-only operation is permitted.",
            )

        if contract.operation == ToolOperation.WRITE:
            if contract.approval == ApprovalPolicy.NEVER:
                return self._result(
                    tool_call,
                    PolicyDecision.DENY,
                    "Write operation has no authorization policy.",
                )

            if contract.approval == ApprovalPolicy.ALWAYS:
                return self._result(
                    tool_call,
                    PolicyDecision.REQUIRE_APPROVAL,
                    "Explicit human approval is required.",
                )

            if contract.approval == ApprovalPolicy.CONDITIONAL:
                if explicit_user_authorization:
                    return self._result(
                        tool_call,
                        PolicyDecision.ALLOW,
                        "Explicit user authorization was verified.",
                    )

                return self._result(
                    tool_call,
                    PolicyDecision.REQUIRE_APPROVAL,
                    "User authorization must be obtained.",
                )

        return self._result(
            tool_call,
            PolicyDecision.DENY,
            "Unsupported tool operation or approval policy.",
        )

    @staticmethod
    def _result(
        tool_call: ToolCall,
        decision: PolicyDecision,
        reason: str,
    ) -> PolicyEvaluation:
        return PolicyEvaluation(
            decision=decision,
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            reason=reason,
        )
