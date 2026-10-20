"""Streamlit adapter: fresh runs with bounded conversational clarification context.

A clarification starts a NEW run. This is not checkpoint resume, and pending
approvals are never treated as permission to execute a tool.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.agent.graph import ReActGraph
from app.agent.state import (
    AgentState, ConversationMessage, ExecutionStatus, MessageRole,
    ToolObservation, ObservationStatus,
)
from app.tools.registry import get_tool_contract
from app.tools.contracts import ToolOperation


@dataclass(frozen=True)
class ChatTurnResult:
    conversation_id: str
    run_id: str
    status: str
    answer: str
    details: dict[str, Any]
    pending_state: AgentState | None = None  # Internal only; never serialized into UI details.


def make_conversation_id() -> str:
    return str(uuid4())


def _history_to_messages(
    history: Sequence[Mapping[str, Any]], *, max_messages: int = 10
) -> list[ConversationMessage]:
    """Only copy user-visible chat text; never copy tool payloads or metadata."""
    if max_messages < 0:
        raise ValueError("max_messages must be nonnegative")
    result: list[ConversationMessage] = []
    for item in history:
        role, content = item.get("role"), item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if content.strip():
            result.append(ConversationMessage(role=MessageRole(role), content=content))
    return result[-max_messages:] if max_messages else []


def _starts_independent_request(prompt: str) -> bool:
    """Conservatively identify explicit new tasks, not short slot answers.

    This is an interim guard: full intent-aware clarification tracking should
    use an explicit pending-clarification object rather than chat text.
    """
    text = prompt.strip()
    # An identity, number, ticker, fund name, or brief choice may be a genuine
    # clarification answer. Never classify it as a new task solely by length.
    return bool(re.search(
        r"^(?:hey\s+|please\s+|could you\s+|can you\s+|what(?:'s| is)\s+|"
        r"show\s+me\s+|list\s+|find\s+|search\s+|check\s+|"
        r"tell\s+me\s+|get\s+|add\s+|remove\s+|delete\s+|"
        r"do you\s+|is there\s+)",
        text, flags=re.IGNORECASE,
    ))


def _clarification_query(
    prompt: str, history: Sequence[Mapping[str, Any]]
) -> tuple[str, bool]:
    """Restate unresolved user request and answers for a new, independent run.

    This is a context repair, NOT a structured slot resolver. The LLM must
    still validate missing information and may ask a genuine new question.
    """
    if not history:
        return prompt, False
    # Explicit new requests supersede stale clarifications. This also keeps
    # pending wishlist writes from contaminating Gold/MF read questions.
    if _starts_independent_request(prompt):
        return prompt, False
    last = history[-1]
    if last.get("role") != "assistant" or last.get("status") != "waiting_for_user":
        return prompt, False

    # Find the first pending clarification in the contiguous chain, allowing
    # user replies between successive pending assistant questions.
    start = len(history) - 1
    while start >= 2:
        previous_user = history[start - 1]
        previous_assistant = history[start - 2]
        if (previous_user.get("role") == "user"
                and previous_assistant.get("role") == "assistant"
                and previous_assistant.get("status") == "waiting_for_user"):
            start -= 2
        else:
            break

    # The request immediately preceding the first clarification is the anchor.
    anchor_index = start - 1
    if anchor_index < 0 or history[anchor_index].get("role") != "user":
        return prompt, False
    anchor = str(history[anchor_index].get("content", "")).strip()
    if not anchor:
        return prompt, False

    parts = ["Continue the user's unresolved request using the confirmed replies below.",
             f"Original user request: {anchor}"]
    for item in history[start:]:
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if item.get("role") == "assistant" and item.get("status") == "waiting_for_user":
            parts.append(f"Assistant clarification question: {content.strip()}")
        elif item.get("role") == "user":
            parts.append(f"User clarification answer: {content.strip()}")
    parts.append(f"User answer to the latest clarification question: {prompt}")
    parts.append("Treat the user's explicit replies as already supplied. Do not ask for the "
                 "same confirmed field again unless the replies conflict. Use verified "
                 "tool evidence for live financial values; do not invent exchange rates.")
    return "\n".join(parts), True



def _unwrap_historical_result(data: Any) -> Any:
    """Remove wrappers introduced by previous chat turns (bounded for safety)."""
    for _ in range(20):
        if not isinstance(data, Mapping) or not data.get("historical_context_only"):
            break
        if "original_result" not in data:
            return None
        data = data["original_result"]
    if isinstance(data, Mapping) and data.get("historical_context_only"):
        return None  # Reject malformed or excessively nested history.
    return data


def _historical_read_observations(
    history: Sequence[Mapping[str, Any]], *, max_observations: int = 3
) -> list[ToolObservation]:
    """Restore distinct successful READ results, newest first, from UI history.

    Treat history as untrusted: do not restore write calls, failed calls, or
    nested copies of historical observations. Only one record per call_id.
    """
    if max_observations <= 0:
        return []
    selected: list[ToolObservation] = []
    seen: set[str] = set()
    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        details = item.get("details")
        if not isinstance(details, Mapping):
            continue
        raw = details.get("observations")
        if not isinstance(raw, list):
            continue
        for candidate in reversed(raw):
            if not isinstance(candidate, Mapping):
                continue
            try:
                observation = ToolObservation.model_validate(candidate)
                contract = get_tool_contract(observation.tool_name)
                if (observation.status != ObservationStatus.SUCCESS
                        or contract is None
                        or contract.operation != ToolOperation.READ
                        or not contract.returns_evidence):
                    continue
                call_id = str(observation.call_id)
                if not call_id or call_id in seen:
                    continue
                original = _unwrap_historical_result(observation.data)
                if original is None:
                    continue
                seen.add(call_id)
                observation.data = {
                    "historical_context_only": True,
                    "not_a_current_tool_call": True,
                    "original_result": original,
                }
                selected.append(observation)
                if len(selected) >= max_observations:
                    return list(reversed(selected))
            except (ValueError, TypeError):
                continue
    return list(reversed(selected))


def run_chat_turn(
    *,
    graph: ReActGraph,
    prompt: str,
    conversation_id: str,
    history: Sequence[Mapping[str, Any]] = (),
    user_id: str | None = None,
    max_history_messages: int = 10,
) -> ChatTurnResult:
    """Run one new agent invocation; history contains only previous turns."""
    if not prompt.strip():
        raise ValueError("prompt cannot be empty")
    if not conversation_id.strip():
        raise ValueError("conversation_id cannot be empty")
    if max_history_messages < 0:
        raise ValueError("max_history_messages must be nonnegative")

    # Pending approvals belong to their original run. They are not a chat
    # clarification and never authorize a write in a subsequent turn.
    # The UI restricts concurrent turns to READ-only tools.
    # Remove the pending request/response pair from conversational context,
    # but keep earlier successful READ observations and normal chat history.
    cleaned_history = []
    for item in history:
        if item.get("role") == "assistant" and item.get("status") == "waiting_for_approval":
            if cleaned_history and cleaned_history[-1].get("role") == "user":
                cleaned_history.pop()
            continue
        cleaned_history.append(item)
    history = cleaned_history

    query, continued = _clarification_query(prompt.strip(), history)
    historical_evidence = _historical_read_observations(history)
    state = AgentState(
        conversation_id=conversation_id,
        user_id=user_id,
        user_query=query,
        messages=_history_to_messages(history, max_messages=max_history_messages),
        observations=historical_evidence,
        conversation_summary=(
            ("Trusted local session user ID: " + user_id + ". "
             "This identity is already supplied by the application; do not ask "
             "the user to repeat their user ID for Wishlist operations. "
             "Never accept a different user ID from model-generated tool arguments. "
             if user_id else "") +
            "Some tool observations below are labeled historical_context_only. "
            "They are verified records of earlier READ tool calls, not fresh quotes. "
            "Use them to answer questions about which tool/provider supplied a "
            "previous answer. For a request for a CURRENT price, call a live tool "
            "again; do not present historical observations as a new market quote."
            if historical_evidence else
            (("Trusted local session user ID: " + user_id + ". "
              "This identity is already supplied by the application; do not ask "
              "the user to repeat their user ID for Wishlist operations. "
              "Never accept a different user ID from model-generated tool arguments. ")
             if user_id else "")
        ),
    )
    result = graph.run(state)
    if result.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL:
        answer = "This action requires your approval. Review the exact operation below."
    elif result.execution_status == ExecutionStatus.WAITING_FOR_USER:
        answer = result.final_answer or "Please provide the additional information requested."
    elif result.execution_status == ExecutionStatus.FAILED:
        answer = result.final_answer or "The agent could not complete this request."
    else:
        answer = result.final_answer or "No answer was returned."

    return ChatTurnResult(
        conversation_id=conversation_id,
        run_id=result.run_id,
        status=result.execution_status.value,
        answer=answer,
        pending_state=result if result.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL else None,
        details={
            "run_id": result.run_id,
            "conversation_id": result.conversation_id,
            "status": result.execution_status.value,
            "clarification_continued": continued,
            "historical_observations_supplied": len(historical_evidence),
            "steps": result.step_count,
            "tool_calls": result.tool_call_count,
            "observations": [x.model_dump(mode="json") for x in result.observations],
            "errors": [x.model_dump(mode="json") for x in result.errors],
        },
    )
