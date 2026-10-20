"""Finzer Wishlist approval smoke test. Run from ReAct_agent project root.

Uses a unique test asset; approved addition is cleaned up by an approved removal.
No OpenAI API calls are made.
"""
from __future__ import annotations

import re
from uuid import uuid4

from app.agent.graph import AgentDecision, ReActGraph
from app.agent.state import AgentState, ExecutionStatus, ObservationStatus
from app.tools.executor import FinzerToolExecutor
from app.tools.mcp_client import call_mcp_tool
from app.mcp_servers.wishlist.tools import is_in_wishlist

USER = "finzer_poc_test"
ASSET_ID = f"finzer_governance_smoke_{uuid4().hex[:12]}"


class StateAwareDecision:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments
        self.calls = 0

    def decide(self, *, context, available_tools):
        self.calls += 1
        if self.calls == 1:
            names = {c.name for c in available_tools}
            assert self.name in names, f"WRITE tool not available: {self.name}; available={sorted(names)}"
            return AgentDecision(action="tool", tool_name=self.name, arguments=self.arguments)
        return AgentDecision(action="finish", message="Governance smoke test finished")


def build_graph(tool: str, arguments: dict):
    executor = FinzerToolExecutor(
        mcp_call=call_mcp_tool,
        user_context_available=True,
    )
    graph = ReActGraph(
        decision_model=StateAwareDecision(tool, arguments),
        tool_executor=executor,
        user_context_available=True,
        max_steps=5,
        max_tool_calls=3,
    )
    return graph, executor


def request_id_from(state):
    assert state.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL, (
        f"Expected approval pause, got {state.execution_status}; errors={state.errors}"
    )
    assert state.pending_tool_call is not None
    match = re.search(r"\[request_id=([^\]]+)\]$", state.approval.reason or "")
    assert match, f"No approval request ID in state: {state.approval.reason}"
    return match.group(1)


def exists():
    result = is_in_wishlist(user_id=USER, asset_type="MUTUAL_FUND", asset_id=ASSET_ID)
    assert result.status == "success", result.model_dump(mode="json")
    return result.data.exists


def run_pending(tool, arguments):
    graph, executor = build_graph(tool, arguments)
    state = graph.run(AgentState(user_id=USER, user_query=f"Governance smoke test {tool}"))
    return graph, executor, state, request_id_from(state)


def main():
    print("Test asset:", ASSET_ID)
    assert not exists(), "Test asset unexpectedly exists"
    args = {
        "user_id": USER,
        "asset_type": "MUTUAL_FUND",
        "asset_id": ASSET_ID,
        "asset_name": "Finzer governance smoke test (temporary)",
        "metadata": {"test": "governance_smoke"},
    }

    # 1. Approval pause must not write to DB.
    graph, executor, pending, request_id = run_pending("wishlist_add", args)
    assert not exists(), "Unapproved add unexpectedly wrote to database"
    print("PASS: wishlist_add paused; no unapproved write")

    # 2. Approve, execute, and verify persistence.
    resumed = graph.resolve_approval(
        state=pending, request_id=request_id, user_id=USER, approve=True
    )
    assert exists(), f"Approved add did not persist; observations={resumed.observations}"
    assert any(o.tool_name == "wishlist_add" and o.status == ObservationStatus.SUCCESS
               for o in resumed.observations), resumed.observations
    print("PASS: approved wishlist_add persisted")

    # 3. Same approved request must not execute again.
    try:
        executor.execute(
            tool_name="wishlist_add", arguments=args,
            run_id=pending.run_id, user_id=USER,
            call_id=pending.pending_tool_call.call_id,
            approval_request_id=request_id,
        )
    except PermissionError:
        print("PASS: consumed approval replay blocked")
    else:
        raise AssertionError("Consumed approval was replayed")

    remove_args = {k: args[k] for k in ("user_id", "asset_type", "asset_id")}

    # 4. Reject a removal; the item must remain.
    reject_graph, _, reject_state, reject_id = run_pending("wishlist_remove", remove_args)
    denied = reject_graph.resolve_approval(
        state=reject_state, request_id=reject_id, user_id=USER, approve=False
    )
    assert denied.execution_status == ExecutionStatus.FAILED
    assert exists(), "Rejected removal deleted the item"
    print("PASS: rejected wishlist_remove did not delete")

    # 5. Approved removal cleans up the temporary test record.
    cleanup_graph, _, cleanup_state, cleanup_id = run_pending("wishlist_remove", remove_args)
    cleanup = cleanup_graph.resolve_approval(
        state=cleanup_state, request_id=cleanup_id, user_id=USER, approve=True
    )
    assert not exists(), f"Approved cleanup failed; observations={cleanup.observations}"
    print("PASS: approved wishlist_remove cleaned up test item")
    print("ALL WISHLIST GOVERNANCE SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
