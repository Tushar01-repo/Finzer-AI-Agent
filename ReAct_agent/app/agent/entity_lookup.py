
"""Canonical entity lookup for Finzer ReAct Agent.

Phase 3.4 — Mutual fund candidate resolution.

Consumes search results from the existing mutual fund MCP tool.
Does not execute MCP calls or access external services.

Python 3.10+ and Pydantic v2.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import EntityType, ResolvedEntity


class LookupStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    INVALID_RESPONSE = "invalid_response"


class EntityLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LookupStatus
    entity: ResolvedEntity | None = None
    candidates: list[ResolvedEntity] = Field(default_factory=list)
    reason: str = ""


class EntityLookupService:
    """Convert external lookup candidates into canonical entities."""

    @staticmethod
    def _normalize(value: str) -> str:
        value = value.casefold()
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    @staticmethod
    def _extract_candidates(
        response: Any,
    ) -> list[dict[str, Any]] | None:
        """Accept common structured MCP result shapes."""

        if isinstance(response, list):
            items = response

        elif isinstance(response, dict):
            if response.get("isError") is True:
                return None

            if isinstance(response.get("funds"), list):
                items = response["funds"]

            elif isinstance(response.get("results"), list):
                items = response["results"]

            elif isinstance(response.get("data"), list):
                items = response["data"]

            else:
                return None

        else:
            return None

        if not all(isinstance(item, dict) for item in items):
            return None

        return items

    @staticmethod
    def _candidate_to_entity(
        candidate: dict[str, Any],
    ) -> ResolvedEntity | None:
        """Require both a fund name and a scheme code."""

        name = (
            candidate.get("schemeName")
            or candidate.get("scheme_name")
            or candidate.get("name")
        )

        code = (
            candidate.get("schemeCode")
            or candidate.get("scheme_code")
            or candidate.get("code")
        )

        if not isinstance(name, str) or not name.strip():
            return None

        if isinstance(code, bool):
            return None

        if not isinstance(code, (str, int)):
            return None

        canonical_id = str(code).strip()

        if not canonical_id.isdigit():
            return None

        return ResolvedEntity(
            entity_type=EntityType.MUTUAL_FUND,
            name=name.strip(),
            canonical_id=canonical_id,
            metadata={
                "lookup_source": "search_mutual_funds",
            },
        )

    def resolve_mutual_fund(
        self,
        query: str,
        response: Any,
    ) -> EntityLookupResult:
        """Resolve a mutual fund from externally supplied candidates.

        An exact normalized name match is required for
        automatic resolution.

        Multiple exact matches remain ambiguous.

        Non-exact candidates are returned for clarification,
        never silently selected.
        """

        if not query.strip():
            return EntityLookupResult(
                status=LookupStatus.NOT_FOUND,
                reason="Empty mutual fund query.",
            )

        raw_candidates = self._extract_candidates(response)

        if raw_candidates is None:
            return EntityLookupResult(
                status=LookupStatus.INVALID_RESPONSE,
                reason="Unsupported or failed lookup response.",
            )

        entities = []
        seen = set()

        for candidate in raw_candidates:
            entity = self._candidate_to_entity(candidate)

            if entity is None:
                continue

            key = entity.canonical_id

            if key in seen:
                continue

            seen.add(key)
            entities.append(entity)

        if not entities:
            return EntityLookupResult(
                status=LookupStatus.NOT_FOUND,
                reason="No valid mutual fund candidates found.",
            )

        normalized_query = self._normalize(query)

        exact = [
            entity
            for entity in entities
            if self._normalize(entity.name) == normalized_query
        ]

        if len(exact) == 1:
            return EntityLookupResult(
                status=LookupStatus.RESOLVED,
                entity=exact[0],
                reason="Exact canonical fund name match.",
            )

        if len(exact) > 1:
            return EntityLookupResult(
                status=LookupStatus.AMBIGUOUS,
                candidates=exact,
                reason="Multiple exact fund matches.",
            )

        return EntityLookupResult(
            status=LookupStatus.AMBIGUOUS,
            candidates=entities,
            reason=(
                "No exact fund name match. "
                "User clarification is required."
            ),
        )
