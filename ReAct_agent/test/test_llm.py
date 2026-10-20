"""Offline tests for app.agent.llm.OpenAIDecisionModel.

Run from ReAct_agent: python -m pytest .\test_llm.py -v
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent.context import PreparedContext
from app.agent.llm import OpenAIDecisionModel
from app.tools.registry import require_tool_contract


def make_model(response_text, *, choices=True):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))]
        if choices else []
    )
    return OpenAIDecisionModel(client=client), client


def decide(model, tools=None):
    return model.decide(
        context=PreparedContext(user_query="What is the gold price in INR?"),
        available_tools=tools if tools is not None else [require_tool_contract("gold_spot_price")],
    )


def test_selects_read_tool_and_passes_context():
    model, client = make_model(json.dumps({
        "action": "tool", "tool_name": "gold_spot_price",
        "arguments": {"currency": "INR"}, "message": None,
    }))
    result = decide(model)
    assert result.action == "tool"
    assert result.tool_name == "gold_spot_price"
    assert result.arguments == {"currency": "INR"}
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    payload = json.loads(kwargs["messages"][1]["content"])
    assert payload["user_query"] == "What is the gold price in INR?"
    assert [tool["name"] for tool in payload["available_tools"]] == ["gold_spot_price"]


def test_clarifies_missing_input():
    model, _ = make_model(json.dumps({"action": "clarify", "message": "Which currency?"}))
    result = decide(model)
    assert result.action == "clarify"
    assert result.message == "Which currency?"


def test_finishes_without_tool():
    model, _ = make_model(json.dumps({"action": "finish", "message": "I can explain NAV."}))
    result = decide(model)
    assert result.action == "finish"
    assert result.message == "I can explain NAV."


@pytest.mark.parametrize("content", ["not json", "{}", '{"action":"tool"}', '{"action":"finish","message":""}'])
def test_rejects_invalid_decision_json(content):
    model, _ = make_model(content)
    with pytest.raises(ValueError, match="invalid AgentDecision JSON"):
        decide(model)


@pytest.mark.parametrize("content, error", [
    (None, "empty content"),
    ("", "empty content"),
])
def test_rejects_empty_content(content, error):
    model, _ = make_model(content)
    with pytest.raises(ValueError, match=error):
        decide(model)


def test_rejects_no_choices():
    model, _ = make_model(None, choices=False)
    with pytest.raises(ValueError, match="no choices"):
        decide(model)


def test_rejects_unknown_tool():
    model, _ = make_model(json.dumps({"action": "tool", "tool_name": "invented_tool"}))
    with pytest.raises(ValueError, match="unavailable tool"):
        decide(model)


def test_filters_and_rejects_write_tool():
    model, client = make_model(json.dumps({"action": "tool", "tool_name": "wishlist_add"}))
    with pytest.raises(ValueError, match="unavailable tool"):
        decide(model, [require_tool_contract("wishlist_add"), require_tool_contract("gold_spot_price")])
    payload = json.loads(client.chat.completions.create.call_args.kwargs["messages"][1]["content"])
    assert [t["name"] for t in payload["available_tools"]] == ["gold_spot_price"]


@pytest.mark.parametrize("content", [
    {"action": "finish", "message": "Done", "tool_name": "gold_spot_price"},
    {"action": "clarify", "message": "Which fund?", "arguments": {"foo": 1}},
])
def test_rejects_tool_fields_on_non_tool_decisions(content):
    model, _ = make_model(json.dumps(content))
    with pytest.raises(ValueError, match="Non-tool decisions"):
        decide(model)


def test_rejects_invalid_configuration():
    client = Mock()
    with pytest.raises(ValueError, match="model must be non-empty"):
        OpenAIDecisionModel(model=" ", client=client)
    with pytest.raises(ValueError, match="max_completion_tokens"):
        OpenAIDecisionModel(max_completion_tokens=0, client=client)
