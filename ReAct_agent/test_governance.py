"""Phase 5 consolidated governance tests (offline; no OpenAI or real MCP calls)."""
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.agent.graph import AgentDecision, ReActGraph
from app.agent.state import AgentState, ApprovalStatus, ExecutionStatus, ToolCall
from app.governance.approval import (
    ApprovalAlreadyResolvedError,
    ApprovalExpiredError,
    ApprovalManager,
    ApprovalPermissionError,
)
from app.governance.audit import AuditEventType, GovernanceAuditLogger
from app.governance.models import (
    ApprovalRequest,
    ApprovalResolution,
    PolicyDecision,
    PolicyEvaluation,
    utc_now,
)
from app.governance.policy import GovernancePolicyEngine
from app.tools.executor import FinzerToolExecutor


class ScriptedModel:
    """Deterministic replacement for OpenAI; checks tool visibility."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.visible_tools = []

    def decide(self, *, context, available_tools):
        self.visible_tools.append({tool.name for tool in available_tools})
        assert self.decisions, "Decision model invoked unexpectedly"
        return self.decisions.pop(0)


def tool_decision(name, **arguments):
    return AgentDecision(action="tool", tool_name=name, arguments=arguments)


def finish_decision():
    return AgentDecision(action="finish", message="Completed using tool data.")


def make_system(*decisions, user_context=True):
    calls = []

    def fake_mcp(server, tool, args):
        calls.append((server, tool, dict(args)))
        return {"status": "success", "data": {"tool": tool, "ok": True}}

    approvals = ApprovalManager()
    audit = GovernanceAuditLogger()
    executor = FinzerToolExecutor(
        mcp_call=fake_mcp,
        approval_manager=approvals,
        user_context_available=user_context,
    )
    model = ScriptedModel(*decisions)
    graph = ReActGraph(
        decision_model=model,
        tool_executor=executor,
        approval_manager=approvals,
        audit_logger=audit,
        user_context_available=user_context,
    )
    return graph, executor, approvals, audit, model, calls


def pending_request(graph, approvals, *, user="user-1"):
    state = graph.run(AgentState(user_query="Add a fund to my wishlist", user_id=user))
    assert state.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL
    assert state.pending_tool_call is not None
    assert state.approval.status == ApprovalStatus.PENDING
    # Request ID is currently encoded in the Approval.reason field.
    request_id = state.approval.reason.rsplit("[request_id=", 1)[1].rstrip("]")
    request = approvals.get_request(request_id)
    return state, request


# ---- Models ----

def test_policy_evaluation_model():
    result = PolicyEvaluation(
        decision=PolicyDecision.ALLOW,
        call_id="call-1",
        tool_name="gold_spot_price",
        reason="Read-only tool",
    )
    assert result.decision == PolicyDecision.ALLOW
    with pytest.raises(ValidationError):
        PolicyEvaluation(decision="invalid", call_id="1", tool_name="x", reason="x")


def test_approval_models_validate_lifecycle():
    call = ToolCall(tool_name="wishlist_add", arguments={"asset": "Example"})
    request = ApprovalRequest(
        run_id="run-1", user_id="user-1", tool_call=call,
        reason="Write operation", expires_at=utc_now() + timedelta(minutes=10),
    )
    assert request.status == ApprovalStatus.PENDING
    assert request.tool_call == call
    assert ApprovalResolution(
        request_id=request.request_id, call_id=call.call_id,
        user_id="user-1", decision=ApprovalStatus.APPROVED,
    ).decision == ApprovalStatus.APPROVED
    with pytest.raises(ValidationError):
        ApprovalResolution(
            request_id=request.request_id, call_id=call.call_id,
            user_id="user-1", decision=ApprovalStatus.PENDING,
        )
    with pytest.raises(ValidationError):
        ApprovalRequest(
            run_id="run-1", user_id="user-1", tool_call=call,
            reason="Expired", expires_at=utc_now() - timedelta(minutes=1),
        )


# ---- Policy ----

def test_policy_allows_registered_read_and_denies_unknown():
    engine = GovernancePolicyEngine()
    assert engine.evaluate(
        tool_call=ToolCall(tool_name="gold_spot_price")
    ).decision == PolicyDecision.ALLOW
    assert engine.evaluate(
        tool_call=ToolCall(tool_name="nonexistent_tool")
    ).decision == PolicyDecision.DENY


def test_policy_wishlist_requires_context_and_approval():
    engine = GovernancePolicyEngine()
    call = ToolCall(tool_name="wishlist_add", arguments={"asset": "Example"})
    assert engine.evaluate(tool_call=call).decision == PolicyDecision.DENY
    assert engine.evaluate(
        tool_call=call, user_context_available=True
    ).decision == PolicyDecision.REQUIRE_APPROVAL
    assert engine.evaluate(
        tool_call=call, user_context_available=True,
        explicit_user_authorization=True,
    ).decision == PolicyDecision.ALLOW


# ---- Approval manager ----

def test_approval_manager_approve_and_exact_resume():
    manager = ApprovalManager()
    call = ToolCall(tool_name="wishlist_add", arguments={"asset": "Example"})
    request = manager.create_request(
        run_id="run-1", user_id="user-1", tool_call=call, reason="Write",
    )
    with pytest.raises(ApprovalPermissionError):
        manager.resolve(request_id=request.request_id, user_id="another", approve=True)
    resolution = manager.resolve(
        request_id=request.request_id, user_id="user-1", approve=True,
    )
    assert resolution.decision == ApprovalStatus.APPROVED
    assert manager.validate_resume(
        request_id=request.request_id, run_id="run-1", user_id="user-1", tool_call=call,
    )
    assert not manager.validate_resume(
        request_id=request.request_id, run_id="run-1", user_id="user-1",
        tool_call=ToolCall(call_id=call.call_id, tool_name=call.tool_name, arguments={"asset": "Changed"}),
    )
    with pytest.raises(ApprovalAlreadyResolvedError):
        manager.resolve(request_id=request.request_id, user_id="user-1", approve=True)


def test_approval_rejection_and_expiration():
    manager = ApprovalManager()
    call = ToolCall(tool_name="wishlist_add")
    denied = manager.create_request(run_id="r", user_id="u", tool_call=call, reason="Write")
    manager.resolve(request_id=denied.request_id, user_id="u", approve=False)
    assert not manager.validate_resume(
        request_id=denied.request_id, run_id="r", user_id="u", tool_call=call,
    )
    expired = manager.create_request(run_id="r", user_id="u", tool_call=call, reason="Write")
    # Force expiry in the in-memory test store; do not wait for wall-clock time.
    object.__setattr__(
        manager._requests[expired.request_id], "expires_at", utc_now() - timedelta(seconds=1)
    )
    with pytest.raises(ApprovalExpiredError):
        manager.resolve(request_id=expired.request_id, user_id="u", approve=True)


# ---- Audit ----

def test_audit_records_and_filters():
    audit = GovernanceAuditLogger()
    audit.record_policy(run_id="r1", evaluation=PolicyEvaluation(
        decision=PolicyDecision.DENY, call_id="c1", tool_name="unknown", reason="Not registered",
    ))
    audit.record_tool_blocked(run_id="r1", tool_name="unknown", call_id="c1", reason="Not registered")
    audit.record_tool_executed(run_id="r2", tool_name="gold_spot_price", call_id="c2", success=True)
    assert len(audit.get_events()) == 3
    assert len(audit.get_events(run_id="r1")) == 2
    assert len(audit.get_events(event_type=AuditEventType.TOOL_EXECUTED)) == 1
    assert "arguments" not in audit.get_events()[0].model_dump()


# ---- Executor + graph integration ----

def test_executor_rejects_unapproved_write():
    _, executor, _, _, _, calls = make_system(finish_decision())
    with pytest.raises(PermissionError):
        executor.execute(tool_name="wishlist_add", arguments={"asset": "Example"})
    assert not calls


def test_read_only_graph_regression():
    graph, _, _, audit, model, calls = make_system(
        tool_decision("gold_spot_price", currency="INR"), finish_decision(),
        user_context=False,
    )
    state = graph.run(AgentState(user_query="Gold price in INR"))
    assert state.execution_status == ExecutionStatus.COMPLETED
    assert state.tool_call_count == 1
    assert len(calls) == 1 and calls[0][1] == "gold_spot_price"
    assert "wishlist_add" not in model.visible_tools[0]
    assert audit.get_events(event_type=AuditEventType.TOOL_EXECUTED)


def test_approved_write_executes_once_and_resumes():
    graph, executor, approvals, audit, model, calls = make_system(
        tool_decision("wishlist_add", asset="Example"), finish_decision(),
    )
    state, request = pending_request(graph, approvals)
    assert not calls  # Nothing executes before human approval.
    assert "wishlist_add" in model.visible_tools[0]
    result = graph.resolve_approval(
        state=state, request_id=request.request_id, user_id="user-1", approve=True,
    )
    assert result.execution_status == ExecutionStatus.COMPLETED
    assert result.tool_call_count == 1
    assert len(calls) == 1 and calls[0][1] == "wishlist_add"
    assert audit.get_events(event_type=AuditEventType.AGENT_RESUMED)
    with pytest.raises(PermissionError):
        executor.execute(
            tool_name="wishlist_add", arguments=request.tool_call.arguments,
            run_id=request.run_id, user_id=request.user_id,
            call_id=request.tool_call.call_id, approval_request_id=request.request_id,
        )
    assert len(calls) == 1


def test_rejected_write_never_executes():
    graph, _, approvals, _, _, calls = make_system(
        tool_decision("wishlist_add", asset="Example"), finish_decision(),
    )
    state, request = pending_request(graph, approvals)
    result = graph.resolve_approval(
        state=state, request_id=request.request_id, user_id="user-1", approve=False,
    )
    assert result.execution_status == ExecutionStatus.FAILED
    assert not calls


def test_wrong_user_cannot_approve_graph_request():
    graph, _, approvals, _, _, calls = make_system(
        tool_decision("wishlist_add", asset="Example"), finish_decision(),
    )
    state, request = pending_request(graph, approvals)
    with pytest.raises(ValueError):
        graph.resolve_approval(
            state=state, request_id=request.request_id, user_id="attacker", approve=True,
        )
    assert not calls
