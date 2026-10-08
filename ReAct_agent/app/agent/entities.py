
"""Deterministic entity resolution for Finzer ReAct Agent.

Phase 3.3 — Entity tracking and conversational references.

No LLM calls, database access, or MCP tool execution.
Python 3.10+ and Pydantic v2.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import (
    AgentState,
    EntityType,
    ResolvedEntity,
)


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class EntityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResolutionStatus
    entity: ResolvedEntity | None = None
    candidates: list[ResolvedEntity] = Field(default_factory=list)
    entity_type: EntityType | None = None
    reason: str = ""


class EntityResolver:
    """Resolve known entities and simple follow-up references.

    This is a conservative resolver. It does not guess
    canonical IDs or treat unfamiliar entity names as
    verified entities.
    """

    TYPE_PATTERNS = {
        EntityType.MUTUAL_FUND: (
            r"\b(?:mutual fund|fund|scheme|nav)\b"
        ),
        EntityType.IPO_DOCUMENT: (
            r"\b(?:ipo|drhp|rhp|prospectus|"
            r"offer document)\b"
        ),
        EntityType.GOLD: (
            r"\b(?:gold|bullion|carat|karat)\b"
        ),
        EntityType.COMPANY: (
            r"\b(?:company|stock|share|equity)\b"
        ),
        EntityType.NEWS_TOPIC: (
            r"\b(?:news|article|headline)\b"
        ),
    }

    REFERENCE_PATTERN = re.compile(
        r"\b(?:it|its|that|this|same|"
        r"those|these|their|them)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    def _detect_types(self, query: str) -> list[EntityType]:
        return [
            entity_type
            for entity_type, pattern in self.TYPE_PATTERNS.items()
            if re.search(pattern, query, re.IGNORECASE)
        ]

    def _match_named_entity(
        self,
        query: str,
        entities: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        normalized_query = self._normalize(query)

        return [
            entity
            for entity in entities
            if self._normalize(entity.name) in normalized_query
            or (
                entity.canonical_id is not None
                and re.search(
                    rf"(?<!\w){re.escape(entity.canonical_id)}(?!\w)",
                    query,
                    re.IGNORECASE,
                )
            )
        ]

    @staticmethod
    def _unique(
        entities: list[ResolvedEntity],
    ) -> list[ResolvedEntity]:
        seen = set()
        result = []

        for entity in entities:
            key = (
                entity.entity_type.value,
                entity.canonical_id or entity.name.casefold(),
            )

            if key not in seen:
                seen.add(key)
                result.append(entity.model_copy(deep=True))

        return result

    def resolve(
        self,
        query: str,
        state: AgentState,
    ) -> EntityResolution:
        """Resolve an entity from the current conversation.

        Resolution order:
        1. Explicit mention of a known name or canonical ID
        2. Typed conversational reference
        3. Untyped conversational reference
        4. Unknown/new entity or no entity reference
        """

        if not query.strip():
            return EntityResolution(
                status=ResolutionStatus.NOT_APPLICABLE,
                reason="Empty query.",
            )

        active = self._unique(state.active_entities)

        explicit = self._unique(
            self._match_named_entity(query, active)
        )

        if len(explicit) == 1:
            return EntityResolution(
                status=ResolutionStatus.RESOLVED,
                entity=explicit[0],
                entity_type=explicit[0].entity_type,
                reason="Matched an active entity by name or ID.",
            )

        if len(explicit) > 1:
            return EntityResolution(
                status=ResolutionStatus.AMBIGUOUS,
                candidates=explicit,
                reason="Multiple active entities explicitly matched.",
            )

        detected_types = self._detect_types(query)
        has_reference = bool(
            self.REFERENCE_PATTERN.search(query)
        )

        if has_reference:
            candidates = [
                entity
                for entity in active
                if (
                    not detected_types
                    or entity.entity_type in detected_types
                )
            ]

            if len(candidates) == 1:
                return EntityResolution(
                    status=ResolutionStatus.RESOLVED,
                    entity=candidates[0],
                    entity_type=candidates[0].entity_type,
                    reason="Resolved a conversational reference.",
                )

            if len(candidates) > 1:
                return EntityResolution(
                    status=ResolutionStatus.AMBIGUOUS,
                    candidates=candidates,
                    reason=(
                        "Reference matches multiple active entities."
                    ),
                )

            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                entity_type=(
                    detected_types[0]
                    if len(detected_types) == 1
                    else None
                ),
                reason="No matching active entity for reference.",
            )

        if detected_types:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                entity_type=(
                    detected_types[0]
                    if len(detected_types) == 1
                    else None
                ),
                reason=(
                    "Entity-related query requires name or "
                    "canonical ID lookup."
                ),
            )

        return EntityResolution(
            status=ResolutionStatus.NOT_APPLICABLE,
            reason="No entity reference detected.",
        )

    def track(
        self,
        state: AgentState,
        entity: ResolvedEntity,
    ) -> AgentState:
        """Return a new state with the entity tracked as active.

        The newest entity is placed last. Existing entities
        with the same type and canonical ID are replaced.
        """

        updated = state.model_copy(deep=True)

        key = (
            entity.entity_type.value,
            entity.canonical_id or entity.name.casefold(),
        )

        remaining = []

        for existing in updated.active_entities:
            existing_key = (
                existing.entity_type.value,
                existing.canonical_id
                or existing.name.casefold(),
            )

            if existing_key != key:
                remaining.append(existing)

        remaining.append(entity.model_copy(deep=True))
        updated.active_entities = remaining

        return updated
