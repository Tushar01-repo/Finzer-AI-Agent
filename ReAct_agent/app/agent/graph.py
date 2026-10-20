
"""Finzer ReAct graph with Phase 5 governance and approved-write resume."""
from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict
import json
from functools import wraps
from time import perf_counter
from typing import Callable, TypeVar

from app.persistence.checkpointer import AgentCheckpointer

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, model_validator

from app.agent.context import ContextManager, PreparedContext
from app.agent.state import (
    AgentError,
    ApprovalStatus,
    AgentState,
    ConversationMessage,
    ExecutionStatus,
    MessageRole,
    NextAction,
    ObservationStatus,
    ToolCall,
    ToolError,
    ToolObservation,
)
from app.tools.contracts import ToolOperation
from app.governance.models import PolicyDecision
from app.governance.policy import GovernancePolicyEngine
from app.governance.approval import ApprovalManager
from app.governance.audit import GovernanceAuditLogger
from app.tools.registry import get_tool_contract, list_tool_contracts
from app.observability.logger import get_logger
from app.observability.tracing import trace_span
from app.observability.metrics import metrics

_observability_log = get_logger("finzer.agent.graph")
_F = TypeVar("_F", bound=Callable[..., Any])


def _observe_graph_operation(operation: str) -> Callable[[_F], _F]:
    """Observe graph operations without changing control flow or tool arguments.

    Only fixed operation names, run IDs and execution status are recorded;
    user prompts, tool arguments and checkpoint contents are never logged.
    """
    metric_operation = {
        "agent_run": "agent",
        "agent_decide": "agent",
        "agent_execute": "agent",
        "agent_resolve_approval": "approval",
    }[operation]

    def decorate(func: _F) -> _F:
        @wraps(func)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            state = kwargs.get("state")
            if state is None and args:
                state = args[0]
            if isinstance(state, dict):
                state = state.get("agent")
            run_id = getattr(state, "run_id", None)
            user_id = getattr(state, "user_id", None)

            started = perf_counter()
            outcome = "error"
            try:
                with trace_span(operation, run_id=run_id, user_id=user_id):
                    try:
                        result = func(self, *args, **kwargs)
                    except Exception as exc:
                        if isinstance(exc, TimeoutError):
                            outcome = "timeout"
                        _observability_log.error(
                            "graph_operation_exception",
                            operation=operation,
                            error_type=type(exc).__name__,
                        )
                        raise

                    observed_state = result
                    if isinstance(result, dict):
                        observed_state = result.get("agent")
                    if observed_state is None:
                        observed_state = state
                    status = getattr(observed_state, "execution_status", None)
                    status_value = getattr(status, "value", status)
                    normalized_status = str(status_value).lower() if status_value is not None else ""

                    if normalized_status == "failed":
                        outcome = "error"
                    elif normalized_status in ("waiting_for_approval", "waiting_for_user"):
                        outcome = "pending"
                    else:
                        # A normal intermediate RUNNING state is not a failure.
                        outcome = "success"

                    _observability_log.info(
                        "graph_operation_finished",
                        operation=operation,
                        execution_status=status_value,
                        outcome=outcome,
                    )
                    return result
            finally:
                # Record exactly one outcome, including normal returns that
                # carry a FAILED or WAITING state instead of raising.
                metrics.record_latency(metric_operation, (perf_counter() - started) * 1000)
                metrics.record_operation(metric_operation, outcome)
        return wrapped  # type: ignore[return-value]
    return decorate



class AgentDecision(BaseModel):
    """Structured output expected from a decision-model adapter."""

    action: Literal["tool", "clarify", "finish"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None

    @model_validator(mode="after")
    def check_action(self) -> "AgentDecision":
        if self.action == "tool" and not self.tool_name:
            raise ValueError("Tool decisions require tool_name")
        if self.action in ("clarify", "finish") and not (self.message or "").strip():
            raise ValueError("Clarify/finish decisions require message")
        return self


class DecisionModel(Protocol):
    def decide(
        self,
        *,
        context: PreparedContext,
        available_tools: list[Any],
    ) -> AgentDecision: ...


class ToolExecutor(Protocol):
    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> Any: ...


class _GraphState(TypedDict):
    agent: AgentState


class ReActGraph:
    """Synchronous ReAct graph with governance and approval support."""

    def __init__(
        self,
        *,
        decision_model: DecisionModel,
        tool_executor: ToolExecutor,
        context_manager: ContextManager | None = None,
        max_steps: int = 16,
        max_tool_calls: int = 12,
        policy_engine: GovernancePolicyEngine | None = None,
        approval_manager: ApprovalManager | None = None,
        audit_logger: GovernanceAuditLogger | None = None,
        user_context_available: bool = False,
        checkpointer: AgentCheckpointer | None = None,
    ) -> None:
        if max_steps < 1 or max_tool_calls < 1:
            raise ValueError(
                "max_steps and max_tool_calls must be positive"
            )

        self.decision_model = decision_model
        self.tool_executor = tool_executor
        self.context_manager = context_manager or ContextManager()
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

        self.policy_engine = policy_engine or GovernancePolicyEngine()
        self.approval_manager = approval_manager or ApprovalManager()
        self.audit_logger = audit_logger or GovernanceAuditLogger()
        self.user_context_available = user_context_available
        self.checkpointer = checkpointer
        # Versions are checked against PostgreSQL on every checkpoint save.
        self._checkpoint_versions: dict[str, int] = {}
        self._read_call_cache: dict[str, set[str]] = {}

        # Graph and executor must share the same approval manager.
        if not hasattr(tool_executor, "approval_manager"):
            self._write_executor_ready = False
        else:
            configured_manager = tool_executor.approval_manager

            if configured_manager is None:
                tool_executor.approval_manager = self.approval_manager
            elif configured_manager is not self.approval_manager:
                raise ValueError(
                    "Graph and executor must share one ApprovalManager"
                )

            self._write_executor_ready = True

        builder = StateGraph(_GraphState)

        builder.add_node("decide", self._checkpointed_decide)
        builder.add_node("execute", self._checkpointed_execute)

        builder.add_edge(START, "decide")

        builder.add_conditional_edges(
            "decide",
            self._route,
            {"execute": "execute", "end": END},
        )

        builder.add_edge("execute", "decide")

        self.graph = builder.compile()

    def _save_checkpoint(self, state: AgentState) -> None:
        """Persist a validated snapshot when checkpointing is enabled.

        A failure is propagated, rather than silently continuing after
        durable storage becomes unavailable.
        """
        if self.checkpointer is None:
            return
        _, version = self.checkpointer.save(
            state,
            expected_version=self._checkpoint_versions.get(state.run_id),
        )
        self._checkpoint_versions[state.run_id] = version

    def load_checkpoint(self, run_id: str) -> AgentState:
        """Load the latest state without automatically replaying tool calls.

        WAITING_FOR_APPROVAL must be resumed through resolve_approval after
        the approval store has also been made durable. Other incomplete
        states require operator reconciliation, not automatic execution.
        """
        if self.checkpointer is None:
            raise RuntimeError("Checkpointing is not enabled")
        saved = self.checkpointer.latest(run_id)
        if saved is None:
            raise LookupError(f"No checkpoint for run {run_id}")
        return saved.state.model_copy(deep=True)

    @staticmethod
    def _fail(
        state: AgentState,
        error_type: str,
        message: str,
    ) -> None:
        state.errors.append(
            AgentError(
                type=error_type,
                message=message,
                step=state.step_count,
            )
        )
        state.next_action = NextAction.FINISH
        state.pending_tool_call = None
        state.execution_status = ExecutionStatus.FAILED

    @staticmethod
    def _read_evidence(state: AgentState) -> str:
        """Summarize verified results without pretending old NAVs are current."""
        lines = []
        seen = set()
        for obs in state.observations:
            if obs.status != ObservationStatus.SUCCESS or not isinstance(obs.data, dict):
                continue
            envelope = obs.data
            if envelope.get("historical_context_only"):
                continue
            if envelope.get("status") != "success":
                continue
            data = envelope.get("data")
            if obs.tool_name == "get_latest_nav" and isinstance(data, dict):
                code = data.get("scheme_code")
                if code in seen:
                    continue
                seen.add(code)
                lines.append(f"- {data.get('scheme_name', 'Unknown fund')} (scheme {code}): "
                             f"NAV {data.get('nav', 'unavailable')}, dated {data.get('date', 'unknown')}")
        return "\n".join(lines)

    def _finish_with_partial(self, state: AgentState, reason: str) -> None:
        evidence = self._read_evidence(state)
        if evidence:
            state.final_answer = ("I could verify the following NAV results:\n" + evidence +
                                  "\n\nI could not complete every requested lookup (" + reason +
                                  "). These NAV dates may be historical; I have not verified that "
                                  "the schemes are currently active.")
            state.next_action = NextAction.FINISH
            state.pending_tool_call = None
            state.execution_status = ExecutionStatus.COMPLETED
            state.messages.append(ConversationMessage(role=MessageRole.ASSISTANT,
                                                      content=state.final_answer))
        else:
            self._fail(state, "TOOL_LIMIT" if "tool" in reason else "STEP_LIMIT", reason)

    @_observe_graph_operation("agent_decide")
    def _checkpointed_decide(self, graph_state: _GraphState) -> _GraphState:
        result = self._decide(graph_state)
        self._save_checkpoint(result["agent"])
        return result

    @_observe_graph_operation("agent_execute")
    def _checkpointed_execute(self, graph_state: _GraphState) -> _GraphState:
        # Persist intent before execution; a crash here requires reconciliation.
        self._save_checkpoint(graph_state["agent"])
        result = self._execute(graph_state)
        self._save_checkpoint(result["agent"])
        return result

    def _decide(self, graph_state: _GraphState) -> _GraphState:
        state = graph_state["agent"].model_copy(deep=True)

        if state.step_count >= self.max_steps:
            self._finish_with_partial(state, "reasoning step limit reached")
            return {"agent": state}

        if state.tool_call_count >= self.max_tool_calls:
            self._finish_with_partial(state, "tool call limit reached")
            return {"agent": state}

        state.step_count += 1
        state.next_action = NextAction.DECIDE

        try:
            context = self.context_manager.prepare_context(state)

            # Write tools are discoverable only with a user identity
            # and an approval-aware executor.
            available = [
                contract
                for contract in list_tool_contracts()
                if contract.operation == ToolOperation.READ
                or (state.user_id and self._write_executor_ready)
            ]

            decision = self.decision_model.decide(
                context=context,
                available_tools=available,
            )

            if not isinstance(decision, AgentDecision):
                decision = AgentDecision.model_validate(decision)

        except Exception as exc:
            self._fail(state, "DECISION_ERROR", str(exc))
            return {"agent": state}

        if decision.action == "tool":
            contract = get_tool_contract(decision.tool_name or "")

            if contract is None:
                self._fail(
                    state,
                    "UNKNOWN_TOOL",
                    f"Unknown tool: {decision.tool_name}",
                )
            else:
                # Normalize before creating the ToolCall: the exact same
                # arguments must be bound to approval and eventual execution.
                arguments = dict(decision.arguments)
                if decision.tool_name in {
                    "wishlist_add", "wishlist_remove", "wishlist_check"
                }:
                    asset_id = arguments.get("asset_id")
                    if isinstance(asset_id, int) and not isinstance(asset_id, bool):
                        arguments["asset_id"] = str(asset_id)

                call = ToolCall(
                    tool_name=decision.tool_name or "",
                    arguments=arguments,
                )
                if contract.operation == ToolOperation.READ:
                    fingerprint = json.dumps([call.tool_name, call.arguments], sort_keys=True, default=str)
                    if fingerprint in self._read_call_cache.get(state.run_id, set()):
                        self._finish_with_partial(state, "the agent repeated an identical READ request")
                        return {"agent": state}
                state.pending_tool_call = call
                self._authorize_or_pause(state, call)

        elif decision.action == "clarify":
            state.pending_tool_call = None
            state.final_answer = decision.message
            state.next_action = NextAction.CLARIFY
            state.execution_status = ExecutionStatus.WAITING_FOR_USER

            state.messages.append(
                ConversationMessage(
                    role=MessageRole.ASSISTANT,
                    content=decision.message or "",
                )
            )

        else:
            state.pending_tool_call = None
            state.final_answer = decision.message
            state.next_action = NextAction.FINISH
            state.execution_status = ExecutionStatus.COMPLETED

            state.messages.append(
                ConversationMessage(
                    role=MessageRole.ASSISTANT,
                    content=decision.message or "",
                )
            )

        return {"agent": state}

    def _authorize_or_pause(
        self,
        state: AgentState,
        call: ToolCall,
    ) -> None:
        evaluation = self.policy_engine.evaluate(
            tool_call=call,
            user_context_available=self.user_context_available,
            explicit_user_authorization=False,
        )

        self.audit_logger.record_policy(
            run_id=state.run_id,
            evaluation=evaluation,
        )

        if evaluation.decision == PolicyDecision.DENY:
            self.audit_logger.record_tool_blocked(
                run_id=state.run_id,
                tool_name=call.tool_name,
                call_id=call.call_id,
                reason=evaluation.reason,
            )
            self._fail(
                state,
                "POLICY_DENIED",
                evaluation.reason,
            )
            return

        if evaluation.decision == PolicyDecision.REQUIRE_APPROVAL:
            if not state.user_id:
                self._fail(
                    state,
                    "USER_ID_REQUIRED",
                    "Approval requires authenticated user identity",
                )
                return

            request = self.approval_manager.create_request(
                run_id=state.run_id,
                user_id=state.user_id,
                tool_call=call,
                reason=evaluation.reason,
            )

            self.audit_logger.record_approval_request(
                request=request
            )

            state.approval.status = ApprovalStatus.PENDING
            state.approval.call_id = call.call_id
            state.approval.reason = (
                f"{evaluation.reason} "
                f"[request_id={request.request_id}]"
            )

            state.next_action = NextAction.WAIT_APPROVAL
            state.execution_status = (
                ExecutionStatus.WAITING_FOR_APPROVAL
            )
            return

        state.approval.status = ApprovalStatus.NOT_REQUIRED
        state.approval.call_id = None
        state.approval.reason = None
        state.next_action = NextAction.TOOL

    @staticmethod
    def _route(
        graph_state: _GraphState,
    ) -> Literal["execute", "end"]:
        state = graph_state["agent"]

        if (
            state.execution_status == ExecutionStatus.RUNNING
            and state.next_action == NextAction.TOOL
        ):
            return "execute"

        return "end"

    def _execute(self, graph_state: _GraphState) -> _GraphState:
        state = graph_state["agent"].model_copy(deep=True)
        self._execute_tool(state)
        return {"agent": state}

    def _execute_tool(
        self,
        state: AgentState,
        *,
        approval_request_id: str | None = None,
    ) -> None:
        call = state.pending_tool_call

        if call is None:
            self._fail(
                state,
                "MISSING_TOOL_CALL",
                "No pending tool call",
            )
            return

        if state.tool_call_count >= self.max_tool_calls:
            self._finish_with_partial(state, "tool call limit reached")
            return

        contract = get_tool_contract(call.tool_name)

        if contract is None:
            self._fail(
                state,
                "UNKNOWN_TOOL",
                "Unregistered tool",
            )
            return

        if approval_request_id is None:
            if state.approval.status == ApprovalStatus.PENDING:
                self._fail(
                    state,
                    "APPROVAL_PENDING",
                    "Tool is awaiting approval",
                )
                return

            evaluation = self.policy_engine.evaluate(
                tool_call=call,
                user_context_available=self.user_context_available,
                explicit_user_authorization=False,
            )

            if (
                evaluation.decision != PolicyDecision.ALLOW
                or contract.operation != ToolOperation.READ
            ):
                self._fail(
                    state,
                    "POLICY_DENIED",
                    evaluation.reason,
                )
                return

        else:
            if (
                contract.operation != ToolOperation.WRITE
                or state.approval.status != ApprovalStatus.APPROVED
            ):
                self._fail(
                    state,
                    "APPROVAL_INVALID",
                    "Approved write required",
                )
                return

            if not state.user_id or not self._write_executor_ready:
                self._fail(
                    state,
                    "APPROVAL_INVALID",
                    "Verified write executor unavailable",
                )
                return

        if contract.operation == ToolOperation.READ:
            fingerprint = json.dumps([call.tool_name, call.arguments], sort_keys=True, default=str)
            self._read_call_cache.setdefault(state.run_id, set()).add(fingerprint)

        state.tool_call_count += 1

        try:
            kwargs = {}

            if approval_request_id is not None:
                kwargs = {
                    "run_id": state.run_id,
                    "user_id": state.user_id,
                    "call_id": call.call_id,
                    "approval_request_id": approval_request_id,
                }

            result = self.tool_executor.execute(
                tool_name=call.tool_name,
                arguments=call.arguments,
                **kwargs,
            )

            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json")

            if isinstance(result, dict) and (
                result.get("status") == "error"
                or result.get("isError") is True
            ):
                raise RuntimeError(
                    str(result.get("error") or result)
                )

            observation = ToolObservation(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ObservationStatus.SUCCESS,
                data=result,
            )

        except Exception as exc:
            observation = ToolObservation(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ObservationStatus.ERROR,
                error=ToolError(
                    type="TOOL_EXECUTION_ERROR",
                    message=str(exc),
                ),
            )

        self.audit_logger.record_tool_executed(
            run_id=state.run_id,
            tool_name=call.tool_name,
            call_id=call.call_id,
            success=(
                observation.status == ObservationStatus.SUCCESS
            ),
        )

        state.observations.append(observation)

        # Never re-plan or automatically request another approval after an
        # approved WRITE fails. The backend outcome can be uncertain.
        if (
            contract.operation == ToolOperation.WRITE
            and observation.status == ObservationStatus.ERROR
        ):
            self._fail(
                state,
                "WRITE_EXECUTION_FAILED",
                "Approved write failed or has an uncertain outcome. "
                "Check the backend state before submitting a new request.",
            )
            return

        # Change the action before clearing the pending tool call.
        # AgentState validates every field assignment.
        state.next_action = NextAction.DECIDE
        state.pending_tool_call = None

    @_observe_graph_operation("agent_resolve_approval")
    def resolve_approval(
        self,
        *,
        state: AgentState,
        request_id: str,
        user_id: str,
        approve: bool,
    ) -> AgentState:
        """
        Resolve a pending approval, execute the approved
        write once, and resume the ReAct reasoning loop.
        """

        resumed = state.model_copy(deep=True)
        if self.checkpointer is not None and resumed.run_id not in self._checkpoint_versions:
            from app.persistence.repository import AgentRunRepository
            persisted = AgentRunRepository().get(resumed.run_id)
            if persisted is None:
                raise LookupError(f"No persisted run {resumed.run_id}")
            persisted_state, version = persisted
            if persisted_state.model_dump(mode="json") != resumed.model_dump(mode="json"):
                raise ValueError("Approval state is stale; reload latest checkpoint")
            self._checkpoint_versions[resumed.run_id] = version

        if (
            resumed.execution_status
            != ExecutionStatus.WAITING_FOR_APPROVAL
            or resumed.pending_tool_call is None
            or resumed.approval.status != ApprovalStatus.PENDING
        ):
            raise ValueError(
                "Agent is not waiting for approval"
            )

        # Request ID is stored in the existing Approval.reason.
        if not (
            resumed.approval.reason or ""
        ).endswith(f"[request_id={request_id}]"):
            raise ValueError(
                "Approval request does not belong to this state"
            )

        request = self.approval_manager.get_request(request_id)

        if (
            request.run_id != resumed.run_id
            or request.user_id != user_id
            or request.tool_call != resumed.pending_tool_call
            or resumed.user_id != user_id
        ):
            raise ValueError(
                "Approval request does not match run, user, or tool"
            )

        resolution = self.approval_manager.resolve(
            request_id=request_id,
            user_id=user_id,
            approve=approve,
        )

        self.audit_logger.record_approval_resolution(
            run_id=resumed.run_id,
            resolution=resolution,
        )

        if not approve:
            resumed.approval.status = ApprovalStatus.DENIED
            self._fail(
                resumed,
                "APPROVAL_DENIED",
                "User rejected the tool operation",
            )
            self._save_checkpoint(resumed)
            return resumed

        call = resumed.pending_tool_call

        if not self.approval_manager.validate_resume(
            request_id=request_id,
            run_id=resumed.run_id,
            user_id=user_id,
            tool_call=call,
        ):
            self._fail(
                resumed,
                "APPROVAL_INVALID",
                "Approval is invalid or expired",
            )
            self._save_checkpoint(resumed)
            return resumed

        resumed.approval.status = ApprovalStatus.APPROVED
        resumed.execution_status = ExecutionStatus.RUNNING
        resumed.next_action = NextAction.TOOL

        self.audit_logger.record_agent_resumed(
            run_id=resumed.run_id,
            request_id=request_id,
        )

        # Durable intent is written before the approved write is attempted.
        self._save_checkpoint(resumed)
        self._execute_tool(
            resumed,
            approval_request_id=request_id,
        )

        self._save_checkpoint(resumed)

        if resumed.execution_status != ExecutionStatus.RUNNING:
            return resumed

        # Continue reasoning with the new tool observation.
        return self.graph.invoke(
            {"agent": resumed},
            config={
                "recursion_limit": 2 * self.max_steps + 4
            },
        )["agent"]

    @_observe_graph_operation("agent_run")
    def run(self, state: AgentState) -> AgentState:
        """Execute one bounded ReAct run."""

        initial = state.model_copy(deep=True)

        if initial.execution_status != ExecutionStatus.RUNNING:
            raise ValueError(
                "AgentState must have execution_status=RUNNING"
            )

        if initial.run_id in self._checkpoint_versions:
            raise ValueError("Run already checkpointed; use a new run ID")
        self._save_checkpoint(initial)

        result = self.graph.invoke(
            {"agent": initial},
            config={
                "recursion_limit": 2 * self.max_steps + 4
            },
        )

        return result["agent"]
