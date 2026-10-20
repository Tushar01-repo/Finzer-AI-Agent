
"""Tests for Finzer Context Manager — Phase 3.2.

Run:
    python -m pytest test_context_manager.py -v

Expected:
    16 passed
"""

import pytest

from app.agent.context import ContextManager
from app.agent.state import (
    AgentState,
    ConversationMessage,
    MessageRole,
    ResolvedEntity,
    EntityType,
    ToolObservation,
    ObservationStatus,
    ToolError,
)


def make_message(index: int) -> ConversationMessage:
    return ConversationMessage(
        role=MessageRole.USER,
        content=f"Conversation message {index}",
    )


def make_observation(
    index: int,
    data=None,
) -> ToolObservation:
    return ToolObservation(
        call_id=f"call-{index}",
        tool_name="news_rag",
        status=ObservationStatus.SUCCESS,
        data=(
            data
            if data is not None
            else {"result": f"News result {index}"}
        ),
    )


def make_entity() -> ResolvedEntity:
    return ResolvedEntity(
        entity_type=EntityType.MUTUAL_FUND,
        name="SBI Small Cap Fund",
        canonical_id="125497",
        metadata={
            "plan": "Direct",
            "option": "Growth",
        },
    )


def test_empty_state():
    state = AgentState(
        user_query="What is the latest NAV?"
    )

    context = ContextManager().prepare_context(state)

    assert context.user_query == state.user_query
    assert context.recent_messages == []
    assert context.relevant_observations == []
    assert context.active_entities == []
    assert context.truncated is False
    assert context.estimated_tokens > 0


def test_recent_messages_chronological():
    state = AgentState(
        user_query="Latest NAV?",
        messages=[
            make_message(i)
            for i in range(15)
        ],
    )

    context = ContextManager(
        max_recent_messages=10
    ).prepare_context(state)

    assert len(context.recent_messages) == 10

    assert [
        message.content
        for message in context.recent_messages
    ] == [
        f"Conversation message {i}"
        for i in range(5, 15)
    ]


def test_zero_message_limit():
    state = AgentState(
        user_query="Latest NAV?",
        messages=[
            make_message(i)
            for i in range(5)
        ],
    )

    context = ContextManager(
        max_recent_messages=0
    ).prepare_context(state)

    assert context.recent_messages == []


def test_recent_observations():
    state = AgentState(
        user_query="Latest news?",
        observations=[
            make_observation(i)
            for i in range(8)
        ],
    )

    context = ContextManager(
        max_observations=5
    ).prepare_context(state)

    assert len(context.relevant_observations) == 5

    assert [
        observation.call_id
        for observation in context.relevant_observations
    ] == [
        "call-3",
        "call-4",
        "call-5",
        "call-6",
        "call-7",
    ]


def test_zero_observation_limit():
    state = AgentState(
        user_query="Latest news?",
        observations=[
            make_observation(i)
            for i in range(3)
        ],
    )

    context = ContextManager(
        max_observations=0
    ).prepare_context(state)

    assert context.relevant_observations == []


def test_oversized_observation_is_truncated_without_mutation():
    original_data = {
        "article": "A" * 12000
    }

    state = AgentState(
        user_query="Summarize the news.",
        observations=[
            make_observation(
                1,
                data=original_data,
            )
        ],
    )

    context = ContextManager(
        max_observation_tokens=100,
        max_context_tokens=6000,
    ).prepare_context(state)

    result = context.relevant_observations[0]

    assert result.data["truncated"] is True
    assert len(result.data["preview"]) <= 400

    assert state.observations[0].data == original_data


def test_active_entities_preserved_when_budget_allows():
    entity = make_entity()

    state = AgentState(
        user_query="What is its NAV?",
        active_entities=[entity],
    )

    context = ContextManager().prepare_context(state)

    assert len(context.active_entities) == 1
    assert context.active_entities[0].canonical_id == "125497"


def test_preparing_context_does_not_mutate_state():
    state = AgentState(
        user_query="Tell me about SBI Small Cap Fund.",
        conversation_summary="User is researching mutual funds.",
        messages=[
            make_message(i)
            for i in range(12)
        ],
        observations=[
            make_observation(i)
            for i in range(6)
        ],
        active_entities=[
            make_entity()
        ],
    )

    before = state.model_dump_json()

    ContextManager(
        max_recent_messages=5,
        max_observations=3,
    ).prepare_context(state)

    after = state.model_dump_json()

    assert before == after


def test_prepared_context_is_independent_copy():
    state = AgentState(
        user_query="Latest NAV?",
        messages=[make_message(1)],
        active_entities=[make_entity()],
        observations=[make_observation(1)],
    )

    context = ContextManager().prepare_context(state)

    context.recent_messages[0].content = "Modified"
    context.active_entities[0].name = "Modified Fund"
    context.relevant_observations[0].data["result"] = "Modified"

    assert state.messages[0].content == "Conversation message 1"
    assert state.active_entities[0].name == "SBI Small Cap Fund"
    assert state.observations[0].data["result"] == "News result 1"


def test_budget_removes_observations_before_messages():
    state = AgentState(
        user_query="Latest NAV?",
        messages=[
            ConversationMessage(
                role=MessageRole.USER,
                content="M" * 100,
            )
        ],
        observations=[
            make_observation(
                1,
                data={"text": "O" * 4000},
            )
        ],
    )

    context = ContextManager(
        max_context_tokens=300,
        max_observation_tokens=1200,
    ).prepare_context(state)

    assert context.truncated is True
    assert context.relevant_observations == []
    assert len(context.recent_messages) == 1
    assert context.estimated_tokens <= 300


def test_budget_removes_oldest_messages_first():
    state = AgentState(
        user_query="Latest NAV?",
        messages=[
            ConversationMessage(
                role=MessageRole.USER,
                content=f"{i}:" + ("X" * 300),
            )
            for i in range(5)
        ],
    )

    context = ContextManager(
        max_context_tokens=350,
        max_recent_messages=5,
    ).prepare_context(state)

    assert context.truncated is True
    assert len(context.recent_messages) < 5

    remaining = [
        message.content
        for message in context.recent_messages
    ]

    assert remaining == [
        message.content
        for message in state.messages[-len(remaining):]
    ]


def test_summary_dropped_after_history():
    state = AgentState(
        user_query="Latest NAV?",
        conversation_summary="S" * 2000,
        messages=[
            ConversationMessage(
                role=MessageRole.USER,
                content="M" * 200,
            )
        ],
    )

    context = ContextManager(
        max_context_tokens=200
    ).prepare_context(state)

    assert context.truncated is True
    assert context.conversation_summary == ""
    assert context.recent_messages == []


def test_invalid_configuration():
    with pytest.raises(ValueError):
        ContextManager(max_context_tokens=0)

    with pytest.raises(ValueError):
        ContextManager(max_recent_messages=-1)

    with pytest.raises(ValueError):
        ContextManager(max_observations=-1)

    with pytest.raises(ValueError):
        ContextManager(max_observation_tokens=0)


def test_impossibly_small_budget_raises():
    state = AgentState(
        user_query="What is the latest NAV?"
    )

    with pytest.raises(ValueError):
        ContextManager(
            max_context_tokens=1
        ).prepare_context(state)


def test_query_is_preserved_with_sufficient_budget():
    query = (
        "Compare SBI Small Cap Fund with gold "
        "over the last 30 days."
    )

    state = AgentState(
        user_query=query,
        conversation_summary="S" * 5000,
        observations=[
            make_observation(
                1,
                data={"text": "X" * 5000},
            )
        ],
    )

    context = ContextManager(
        max_context_tokens=250,
        max_observation_tokens=1000,
    ).prepare_context(state)

    assert context.user_query == query
    assert context.truncated is True
    assert context.estimated_tokens <= 250


def test_query_must_never_be_truncated_even_with_tiny_budget():
    """The complete query must be preserved or an error raised."""

    query = (
        "Compare SBI Small Cap Fund with gold "
        "over the last 30 days and explain "
        "their relative performance."
    )

    state = AgentState(
        user_query=query
    )

    with pytest.raises(
        ValueError,
        match="Context budget is too small",
    ):
        ContextManager(
            max_context_tokens=10
        ).prepare_context(state)

    # The original query must remain unchanged.
    assert state.user_query == query
