"""Phase 4: isolated ReActGraph tests (no network or real LLM calls)."""

from __future__ import annotations

from collections import deque

import pytest

from app.agent.graph import AgentDecision, ReActGraph
from app.agent.state import AgentState, ExecutionStatus, NextAction, ObservationStatus


class ScriptedDecisionModel:
    def __init__(self, *decisions):
        self.decisions = deque(decisions)
        self.contexts = []
        self.available_tools = []

    def decide(self, *, context, available_tools):
        self.contexts.append(context)
        self.available_tools.append(available_tools)
        if not self.decisions:
            raise AssertionError("Unexpected extra decision")
        return self.decisions.popleft()


class FakeToolExecutor:
    def __init__(self, results=None):
        self.results = deque(results or [])
        self.calls = []

    def execute(self, *, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if not self.results:
            raise AssertionError("Unexpected tool invocation")
        value = self.results.popleft()
        if isinstance(value, Exception):
            raise value
        return value


def make_graph(*decisions, results=None, max_steps=8, max_tool_calls=5):
    model = ScriptedDecisionModel(*decisions)
    executor = FakeToolExecutor(results)
    graph = ReActGraph(
        decision_model=model,
        tool_executor=executor,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
    )
    return graph, model, executor


def test_finish_without_tools():
    graph, model, executor = make_graph(AgentDecision(action="finish", message="Hello"))
    original = AgentState(user_query="Hello")
    result = graph.run(original)
    assert result.execution_status == ExecutionStatus.COMPLETED
    assert result.next_action == NextAction.FINISH
    assert result.final_answer == "Hello"
    assert result.step_count == 1
    assert result.tool_call_count == 0
    assert not executor.calls
    assert original.step_count == 0  # run must not mutate input


def test_tool_observation_then_finish():
    graph, model, executor = make_graph(
        AgentDecision(action="tool", tool_name="gold_spot_price", arguments={"currency": "INR"}),
        AgentDecision(action="finish", message="Gold data retrieved"),
        results=[{"price": 9000}],
    )
    result = graph.run(AgentState(user_query="Gold price?"))
    assert result.execution_status == ExecutionStatus.COMPLETED
    assert result.tool_call_count == 1
    assert result.step_count == 2
    assert len(result.observations) == 1
    assert result.observations[0].status == ObservationStatus.SUCCESS
    assert result.observations[0].data == {"price": 9000}
    assert executor.calls == [("gold_spot_price", {"currency": "INR"})]
    assert len(model.contexts[1].relevant_observations) == 1


def test_two_tools_then_finish():
    graph, _, executor = make_graph(
        AgentDecision(action="tool", tool_name="gold_spot_price"),
        AgentDecision(action="tool", tool_name="gold_carat_prices"),
        AgentDecision(action="finish", message="Done"),
        results=[{"spot": 1}, {"carats": [22, 24]}],
    )
    result = graph.run(AgentState(user_query="Compare gold prices"))
    assert result.execution_status == ExecutionStatus.COMPLETED
    assert result.tool_call_count == 2
    assert result.step_count == 3
    assert len(result.observations) == 2
    assert len(executor.calls) == 2


def test_clarification_waits_for_user():
    graph, _, executor = make_graph(
        AgentDecision(action="clarify", message="Which mutual fund plan?")
    )
    result = graph.run(AgentState(user_query="SBI Small Cap NAV"))
    assert result.execution_status == ExecutionStatus.WAITING_FOR_USER
    assert result.next_action == NextAction.CLARIFY
    assert result.final_answer == "Which mutual fund plan?"
    assert not executor.calls


def test_unknown_tool_is_rejected():
    graph, _, executor = make_graph(
        AgentDecision(action="tool", tool_name="nonexistent_tool")
    )
    result = graph.run(AgentState(user_query="Run a tool"))
    assert result.execution_status == ExecutionStatus.FAILED
    assert result.errors[-1].type == "UNKNOWN_TOOL"
    assert not executor.calls


def test_write_tool_is_blocked():
    graph, model, executor = make_graph(
        AgentDecision(action="tool", tool_name="wishlist_add", arguments={"asset": "gold"})
    )
    result = graph.run(AgentState(user_query="Add gold to wishlist"))
    assert result.execution_status == ExecutionStatus.FAILED
    assert result.errors[-1].type == "WRITE_BLOCKED"
    assert not executor.calls
    assert all(contract.name != "wishlist_add" for contract in model.available_tools[0])


@pytest.mark.parametrize("failure", [RuntimeError("service unavailable"), {"status": "error", "error": "upstream failed"}])
def test_tool_errors_become_observations(failure):
    graph, _, _ = make_graph(
        AgentDecision(action="tool", tool_name="gold_spot_price"),
        AgentDecision(action="finish", message="Could not get a price"),
        results=[failure],
    )
    result = graph.run(AgentState(user_query="Gold price?"))
    assert result.execution_status == ExecutionStatus.COMPLETED
    assert result.observations[0].status == ObservationStatus.ERROR
    assert result.observations[0].error.type == "TOOL_EXECUTION_ERROR"


def test_step_limit_fails_safely():
    graph, _, _ = make_graph(
        AgentDecision(action="tool", tool_name="gold_spot_price"),
        AgentDecision(action="finish", message="Would finish but limit reached"),
        results=[{"price": 1}],
        max_steps=1,
    )
    result = graph.run(AgentState(user_query="Gold price?"))
    assert result.execution_status == ExecutionStatus.FAILED
    assert result.errors[-1].type == "STEP_LIMIT"
    assert result.tool_call_count == 1


def test_tool_limit_fails_safely():
    graph, _, _ = make_graph(
        AgentDecision(action="tool", tool_name="gold_spot_price"),
        AgentDecision(action="finish", message="Would finish but limit reached"),
        results=[{"price": 1}],
        max_tool_calls=1,
    )
    result = graph.run(AgentState(user_query="Gold price?"))
    assert result.execution_status == ExecutionStatus.FAILED
    assert result.errors[-1].type == "TOOL_LIMIT"
    assert result.tool_call_count == 1


def test_invalid_initial_state_is_rejected():
    graph, _, _ = make_graph(AgentDecision(action="finish", message="Done"))
    with pytest.raises(ValueError, match="execution_status=RUNNING"):
        graph.run(AgentState(user_query="Hello", execution_status=ExecutionStatus.FAILED))
