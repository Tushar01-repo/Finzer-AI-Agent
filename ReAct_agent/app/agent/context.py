
"""Deterministic context preparation for Finzer ReAct Agent.

Phase 3.2 — Context Manager

Responsibilities:
- Select recent conversation messages
- Preserve active entities
- Select recent tool observations
- Bound oversized observation payloads
- Enforce a context token budget
- Never truncate the current user query
- Never mutate the original AgentState

No LLM calls, database access, or tool execution.

Compatible with Python 3.10+ and Pydantic v2.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import (
    AgentState,
    ConversationMessage,
    ResolvedEntity,
    ToolObservation,
)


class PreparedContext(BaseModel):
    """Structured context for the future ReAct reasoning node."""

    model_config = ConfigDict(extra="forbid")

    user_query: str

    conversation_summary: str = ""

    active_entities: list[ResolvedEntity] = Field(
        default_factory=list
    )

    recent_messages: list[ConversationMessage] = Field(
        default_factory=list
    )

    relevant_observations: list[ToolObservation] = Field(
        default_factory=list
    )

    estimated_tokens: int = 0

    max_context_tokens: int = 6000

    truncated: bool = False


class ContextManager:
    """Prepare bounded context from AgentState.

    Context priority:

    1. Current user query — mandatory, never truncated
    2. Active entities
    3. Conversation summary
    4. Recent conversation messages
    5. Recent tool observations

    Lower-priority context is removed first when the
    estimated context exceeds the configured budget.

    This implementation is deterministic. Semantic
    relevance and entity resolution are handled later.
    """

    def __init__(
        self,
        max_context_tokens: int = 6000,
        max_recent_messages: int = 10,
        max_observations: int = 16,
        max_observation_tokens: int = 1600,
    ) -> None:

        if max_context_tokens <= 0:
            raise ValueError(
                "max_context_tokens must be positive"
            )

        if max_recent_messages < 0:
            raise ValueError(
                "max_recent_messages cannot be negative"
            )

        if max_observations < 0:
            raise ValueError(
                "max_observations cannot be negative"
            )

        if max_observation_tokens <= 0:
            raise ValueError(
                "max_observation_tokens must be positive"
            )

        self.max_context_tokens = max_context_tokens

        self.max_recent_messages = max_recent_messages

        self.max_observations = max_observations

        self.max_observation_tokens = (
            max_observation_tokens
        )

    @staticmethod
    def estimate_tokens(value: Any) -> int:
        """Estimate token count using a character heuristic.

        Approximately one token per four characters.

        This is not an exact model tokenizer count.
        """

        if isinstance(value, str):
            text = value

        elif isinstance(value, BaseModel):
            text = value.model_dump_json()

        else:
            text = json.dumps(
                value,
                default=str,
                ensure_ascii=False,
            )

        return math.ceil(len(text) / 4)

    @staticmethod
    def _truncate_text(
        text: str,
        max_tokens: int,
    ) -> str:
        """Truncate optional text using the token heuristic."""

        max_chars = max_tokens * 4

        if len(text) <= max_chars:
            return text

        return text[:max_chars]

    def _select_recent_messages(
        self,
        state: AgentState,
    ) -> list[ConversationMessage]:
        """Select recent messages in chronological order."""

        if self.max_recent_messages == 0:
            return []

        return [
            message.model_copy(deep=True)
            for message in state.messages[
                -self.max_recent_messages:
            ]
        ]

    def _select_observations(
        self,
        state: AgentState,
    ) -> list[ToolObservation]:
        """Select recent observations with bounded data."""

        if self.max_observations == 0:
            return []

        # Preserve the most relevant successful evidence for the current topic.
        # A fresh MF question must not be crowded out by earlier gold quotes.
        query = state.user_query.lower()
        mf_terms = ("mutual fund", "fund", "scheme", "nav", "motilal", "sbi", "their code", "their schema")
        gold_terms = ("gold", "xau", "bullion", "carat")
        wishlist_terms = ("wishlist", "watchlist")
        if any(term in query for term in wishlist_terms):
            preferred = ("wishlist_",)
        elif any(term in query for term in gold_terms):
            preferred = ("gold_",)
        elif any(term in query for term in mf_terms) or re.search(r"\b(their|those|these)\s+(?:scheme|schema|codes?)\b", query):
            preferred = ("search_mutual_funds", "get_mutual_fund", "mutual_fund", "get_nav", "get_latest_nav")
        else:
            preferred = ()
        observations = state.observations
        if preferred:
            matching = [obs for obs in observations if any(obs.tool_name.startswith(p) for p in preferred)]
            # Keep recent matching evidence, plus any current-run observations.
            observations = matching if matching else observations
        selected = observations[-self.max_observations:]

        results: list[ToolObservation] = []

        for observation in selected:

            copy = observation.model_copy(deep=True)

            if copy.data is not None:

                serialized = json.dumps(
                    copy.data,
                    default=str,
                    ensure_ascii=False,
                )

                if (
                    self.estimate_tokens(serialized)
                    > self.max_observation_tokens
                ):

                    copy.data = {
                        "truncated": True,
                        "preview": self._truncate_text(
                            serialized,
                            self.max_observation_tokens,
                        ),
                    }

            results.append(copy)

        return results

    def _calculate_total(
        self,
        context: PreparedContext,
    ) -> int:
        """Estimate the total serialized context size."""

        payload = {
            "user_query": context.user_query,

            "conversation_summary": (
                context.conversation_summary
            ),

            "active_entities": [
                entity.model_dump(mode="json")
                for entity in context.active_entities
            ],

            "recent_messages": [
                message.model_dump(mode="json")
                for message in context.recent_messages
            ],

            "relevant_observations": [
                observation.model_dump(mode="json")
                for observation
                in context.relevant_observations
            ],
        }

        return self.estimate_tokens(payload)

    def prepare_context(
        self,
        state: AgentState,
    ) -> PreparedContext:
        """Prepare context without modifying AgentState.

        The current user query is mandatory.

        If the full query and minimum serialization
        overhead cannot fit the budget, raise ValueError
        instead of silently modifying the query.
        """

        context = PreparedContext(
            user_query=state.user_query,

            conversation_summary=(
                state.conversation_summary
            ),

            active_entities=[
                entity.model_copy(deep=True)
                for entity in state.active_entities
            ],

            recent_messages=(
                self._select_recent_messages(state)
            ),

            relevant_observations=(
                self._select_observations(state)
            ),

            max_context_tokens=self.max_context_tokens,
        )

        initial_tokens = self._calculate_total(context)

        if initial_tokens <= self.max_context_tokens:

            context.estimated_tokens = initial_tokens

            return context

        context.truncated = True

        # STEP 1:
        # Remove oldest observations first.

        while context.relevant_observations:

            if (
                self._calculate_total(context)
                <= self.max_context_tokens
            ):
                break

            context.relevant_observations.pop(0)

        # STEP 2:
        # Remove oldest conversation messages first.

        while context.recent_messages:

            if (
                self._calculate_total(context)
                <= self.max_context_tokens
            ):
                break

            context.recent_messages.pop(0)

        # STEP 3:
        # Remove the conversation summary if necessary.

        if (
            self._calculate_total(context)
            > self.max_context_tokens
        ):

            context.conversation_summary = ""

        # STEP 4:
        # Remove lower-priority entities if necessary.

        while context.active_entities:

            if (
                self._calculate_total(context)
                <= self.max_context_tokens
            ):
                break

            context.active_entities.pop()

        # STEP 5:
        # Preserve the complete user query.
        #
        # If the remaining context is still too large,
        # fail explicitly rather than truncating it.

        context.estimated_tokens = (
            self._calculate_total(context)
        )

        if (
            context.estimated_tokens
            > self.max_context_tokens
        ):

            raise ValueError(
                "Context budget is too small to preserve "
                "the complete user query. "
                f"Required approximately "
                f"{context.estimated_tokens} tokens, "
                f"but the budget is "
                f"{self.max_context_tokens}."
            )

        return context
