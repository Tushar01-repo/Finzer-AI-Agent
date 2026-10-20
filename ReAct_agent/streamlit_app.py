"""Finzer AI ReAct Agent — Streamlit conversational UI (Phase 7.5, Step 3).

Run from ReAct_agent root: streamlit run streamlit_app.py
Chat history is session-local. Ordinary turns are independent; pending
WRITE requests can be approved or rejected in the same Streamlit session.
"""
from __future__ import annotations

import os

import streamlit as st

from app.agent.graph import ReActGraph
from app.agent.state import ExecutionStatus
from app.tools.contracts import ToolOperation
from app.tools.registry import require_tool_contract
from app.agent.llm import OpenAIDecisionModel
from app.tools.executor import FinzerToolExecutor
from app.tools.mcp_client import call_mcp_tool
from app.ui.agent_adapter import make_conversation_id, run_chat_turn


POC_USER_ID = "finzer_poc_test"  # Local development only; NOT authenticated.


class ReadOnlyExecutor:
    """Fail closed for concurrent chat turns while a write awaits approval.

    Deliberately has no approval_manager attribute: ReActGraph will not
    advertise WRITE tools to the decision model for these turns.
    """

    def __init__(self, executor):
        self._executor = executor

    def execute(self, *, tool_name, arguments, **kwargs):
        if require_tool_contract(tool_name).operation != ToolOperation.READ:
            raise PermissionError("A write is already awaiting approval")
        return self._executor.execute(tool_name=tool_name, arguments=arguments, **kwargs)


st.set_page_config(page_title="Finzer AI Assistant", page_icon="💬", layout="centered")
st.title("Finzer AI Assistant")
st.caption("ReAct agent · Financial questions · MCP tools · Session chat context")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = make_conversation_id()
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

with st.sidebar:
    st.header("Conversation")
    st.caption("Local POC identity: finzer_poc_test (not authenticated)")
    st.caption(f"Conversation ID: `{st.session_state.conversation_id}`")
    model = st.text_input(
        "Decision model", value=os.getenv("FINZER_UI_MODEL", "gpt-4.1-mini")
    )
    show_details = st.toggle("Show execution details", value=False)
    if st.button("New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pending_approval = None
        st.session_state.conversation_id = make_conversation_id()
        st.rerun()
    st.caption("History is kept only in this browser session; not yet saved to PostgreSQL.")
    st.caption("Approvals work only while this browser session and Python process remain alive.")

for item in st.session_state.messages:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])
        if item["role"] == "assistant" and item.get("status") in (
            "failed", "waiting_for_approval", "waiting_for_user"
        ):
            st.caption(f"Status: {item['status']}")
        if show_details and item.get("details"):
            with st.expander("Execution details"):
                st.json(item["details"])

# A pending WRITE must be resolved against the SAME graph and ApprovalManager.
# Never use chat text as an approval signal.
pending = st.session_state.pending_approval
if pending is not None:
    state = pending["state"]
    call = state.pending_tool_call
    with st.container(border=True):
        st.subheader("Approval required")
        st.warning("Review the exact write operation before deciding.")
        st.write(f"**Tool:** `{call.tool_name}`")
        st.write(f"**Local POC user:** `{state.user_id}`")
        st.json(call.arguments)
        approve_col, reject_col = st.columns(2)
        approved = approve_col.button("Approve", type="primary", use_container_width=True)
        rejected = reject_col.button("Reject", use_container_width=True)
        if approved or rejected:
            # Clear the UI pending marker first so double-clicks cannot resume it.
            st.session_state.pending_approval = None
            try:
                with st.spinner("Resolving approval..."):
                    result = pending["graph"].resolve_approval(
                        state=state,
                        request_id=pending["request_id"],
                        user_id=POC_USER_ID,
                        approve=approved,
                    )
                if result.execution_status == ExecutionStatus.COMPLETED:
                    answer = result.final_answer or "Operation completed."
                elif result.execution_status == ExecutionStatus.FAILED:
                    answer = result.final_answer or (
                        "Operation rejected." if rejected else "Operation failed; inspect execution details."
                    )
                elif result.execution_status == ExecutionStatus.WAITING_FOR_USER:
                    answer = result.final_answer or "Additional information is required."
                else:
                    answer = result.final_answer or f"Status: {result.execution_status.value}"
                details = {
                    "run_id": result.run_id,
                    "status": result.execution_status.value,
                    "tool_calls": result.tool_call_count,
                    "observations": [o.model_dump(mode="json") for o in result.observations],
                    "errors": [e.model_dump(mode="json") for e in result.errors],
                }
                # Replace the pending assistant reply, rather than injecting a new
                # user message or breaking clarification history.
                st.session_state.messages[pending["message_index"]] = {
                    "role": "assistant", "content": answer,
                    "status": result.execution_status.value, "details": details,
                }
            except Exception as exc:
                # Outcome of a failed network write may be ambiguous: do not
                # automatically retry or create a fresh approval request.
                st.session_state.messages[pending["message_index"]] = {
                    "role": "assistant",
                    "content": "Approval resolution failed. Do not retry the write without reconciling its status.",
                    "status": "failed", "details": {"error_type": type(exc).__name__},
                }
            st.rerun()

if st.session_state.pending_approval is not None:
    st.caption("One write is awaiting approval. You can still ask READ questions; resolve it before requesting another write.")

prompt = st.chat_input("Ask about gold, mutual funds, news, or IPO documents...")
if prompt and prompt.strip():
    # The adapter expects only PRIOR turns. Capture before adding this prompt.
    prior_history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        details = {}
        status = "failed"
        if not os.getenv("OPENAI_API_KEY"):
            answer = "OPENAI_API_KEY is not configured for this process."
            st.error(answer)
        elif not model.strip():
            answer = "Choose a decision model in the sidebar."
            st.error(answer)
        else:
            try:
                # Per-request construction avoids sharing a graph across browser sessions.
                executor = FinzerToolExecutor(
                    mcp_call=call_mcp_tool,
                    user_context_available=True,
                )
                # Only one pending WRITE at a time. Other turns can READ.
                if st.session_state.pending_approval is not None:
                    executor = ReadOnlyExecutor(executor)
                graph = ReActGraph(
                    decision_model=OpenAIDecisionModel(model=model.strip()),
                    tool_executor=executor,
                    user_context_available=True,
                    max_steps=8,
                    max_tool_calls=5,
                )
                with st.spinner("Finzer is working..."):
                    turn = run_chat_turn(
                        graph=graph,
                        prompt=prompt,
                        user_id=POC_USER_ID,
                        conversation_id=st.session_state.conversation_id,
                        history=prior_history,
                        max_history_messages=10,
                    )
                answer, status, details = turn.answer, turn.status, turn.details
                if turn.pending_state is not None:
                    if st.session_state.pending_approval is not None:
                        raise RuntimeError("Another write approval is already pending")
                    state = turn.pending_state
                    call = state.pending_tool_call
                    # The request ID is generated by the graph and stored on the
                    # approval state; never invent it from a chat message.
                    import re
                    match = re.search(r"\[request_id=([^\]]+)\]$", state.approval.reason or "")
                    if call is None or match is None:
                        raise RuntimeError("Pending approval state is missing its request identity")
                    st.session_state.pending_approval = {
                        "graph": graph,
                        "state": state,
                        "request_id": match.group(1),
                        "message_index": len(st.session_state.messages),
                    }
                if status == "waiting_for_approval":
                    st.warning(answer)
                elif status == "waiting_for_user":
                    st.info(answer)
                elif status == "failed":
                    st.error(answer)
                else:
                    st.markdown(answer)
                if show_details:
                    with st.expander("Execution details"):
                        st.json(details)
            except Exception as exc:
                # Don't expose raw exceptions (which may include secrets) to the UI.
                answer = "The agent encountered an error. Check the application terminal logs."
                details = {"error_type": type(exc).__name__}
                st.error(answer)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "status": status, "details": details}
        )

# Render pending approval controls on the next rerun after the chat response.
if prompt and st.session_state.pending_approval is not None:
    st.rerun()
