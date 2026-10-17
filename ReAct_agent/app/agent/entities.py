
"""Deterministic entity resolution for Finzer ReAct Agent.

Phase 3.3 — Entity tracking and conversational references.

No LLM calls, database access, or MCP tool execution.
Python 3.10+ and Pydantic v2.
"""

from __future__ import annotations

import re
import json
from enum import Enum
from typing import Any

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


class IPOLookupStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    INVALID_RESPONSE = "invalid_response"


class IPOLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IPOLookupStatus
    entity: ResolvedEntity | None = None
    candidates: list[ResolvedEntity] = Field(default_factory=list)
    reason: str = ""


class IPOEntityLookupService:
    """Resolve IPO documents from ingestion metadata."""

    DOCUMENT_TYPES = ("DRHP", "RHP")

    @staticmethod
    def _normalize(value: str) -> str:
        value = value.casefold()
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    @classmethod
    def _detect_document_type(cls, query: str) -> str | None:
        matches = [
            doc_type
            for doc_type in cls.DOCUMENT_TYPES
            if re.search(
                rf"\b{doc_type}\b",
                query,
                re.IGNORECASE,
            )
        ]

        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _extract_documents(
        response: Any,
    ) -> list[dict[str, Any]] | None:
        if isinstance(response, list):
            documents = response

        elif isinstance(response, dict):
            if response.get("isError") is True:
                return None

            if response.get("status") == "error":
                return None

            documents = response.get("documents")

            if not isinstance(documents, list):
                documents = response.get("data")

        else:
            return None

        if not isinstance(documents, list):
            return None

        if not all(isinstance(doc, dict) for doc in documents):
            return None

        return documents

    @staticmethod
    def _to_entity(
        document: dict[str, Any],
    ) -> ResolvedEntity | None:
        document_key = document.get("document_key")
        company_name = document.get("company_name")
        document_type = document.get("document_type")

        if not isinstance(document_key, str):
            return None

        if not document_key.strip():
            return None

        if not isinstance(company_name, str):
            return None

        if not company_name.strip():
            return None

        if not isinstance(document_type, str):
            return None

        if not document_type.strip():
            return None

        document_type = document_type.strip().upper()

        metadata = {
            "document_id": document.get("document_id"),
            "company_name": company_name.strip(),
            "document_type": document_type,
            "source_title": document.get("source_title"),
            "published_at": document.get("published_at"),
            "status": document.get("status"),
            "source": document.get("source"),
        }

        return ResolvedEntity(
            entity_type=EntityType.IPO_DOCUMENT,
            name=f"{company_name.strip()} {document_type}",
            canonical_id=document_key.strip(),
            metadata=metadata,
        )

    @classmethod
    def _matches_query(
        cls,
        query: str,
        entity: ResolvedEntity,
    ) -> bool:
        normalized_query = cls._normalize(query)

        company_name = cls._normalize(
            entity.metadata["company_name"]
        )

        if not company_name:
            return False

        # Match the full company name as a token sequence.
        # Do not match arbitrary substrings.
        query_tokens = normalized_query.split()
        company_tokens = company_name.split()

        company_length = len(company_tokens)

        for index in range(
            len(query_tokens) - company_length + 1
        ):
            if (
                query_tokens[index:index + company_length]
                == company_tokens
            ):
                return True

        return False

    def resolve(
        self,
        query: str,
        response: Any,
    ) -> IPOLookupResult:
        if not isinstance(query, str) or not query.strip():
            return IPOLookupResult(
                status=IPOLookupStatus.NOT_FOUND,
                reason="Empty IPO document query.",
            )

        documents = self._extract_documents(response)

        if documents is None:
            return IPOLookupResult(
                status=IPOLookupStatus.INVALID_RESPONSE,
                reason="Invalid document metadata response.",
            )

        expected_type = self._detect_document_type(query)

        candidates: list[ResolvedEntity] = []
        seen_keys: set[str] = set()

        for document in documents:
            entity = self._to_entity(document)

            if entity is None:
                continue

            if entity.canonical_id in seen_keys:
                continue

            if not self._matches_query(query, entity):
                continue

            if expected_type is not None:
                if (
                    entity.metadata["document_type"]
                    != expected_type
                ):
                    continue

            seen_keys.add(entity.canonical_id)
            candidates.append(entity)

        if not candidates:
            return IPOLookupResult(
                status=IPOLookupStatus.NOT_FOUND,
                reason="No matching indexed IPO document found.",
            )

        if len(candidates) == 1:
            return IPOLookupResult(
                status=IPOLookupStatus.RESOLVED,
                entity=candidates[0],
                reason="Unique matching IPO document found.",
            )

        return IPOLookupResult(
            status=IPOLookupStatus.AMBIGUOUS,
            candidates=candidates,
            reason=(
                "Multiple IPO documents match the query. "
                "User clarification is required."
            ),
        )


class MCPLookupAdapter:
    """Normalize mutual fund MCP responses."""

    @staticmethod
    def normalize_search_response(
        response: Any,
    ) -> dict[str, Any]:
        """Normalize an MCP result into a lookup response.

        Supports:
        - ToolResponse dictionaries
        - MCP CallToolResult objects
        - JSON-encoded MCP text content

        Rejects unsuccessful or malformed responses.
        """

        if hasattr(response, "model_dump"):
            response = response.model_dump(
                mode="json",
                exclude_none=True,
            )

        if not isinstance(response, dict):
            return {
                "isError": True,
                "message": "Unsupported MCP response type.",
            }

        if response.get("isError") is True:
            return {
                "isError": True,
                "message": "MCP tool execution failed.",
            }

        # Handle an MCP CallToolResult content wrapper.
        if "content" in response:

            structured = response.get("structuredContent")

            if isinstance(structured, dict):
                return (
                    MCPLookupAdapter.normalize_search_response(
                        structured
                    )
                )

            content = response["content"]

            if not isinstance(content, list):
                return {
                    "isError": True,
                    "message": "Invalid MCP content.",
                }

            for item in content:

                if not isinstance(item, dict):
                    continue

                text = item.get("text")

                if not isinstance(text, str):
                    continue

                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue

                return (
                    MCPLookupAdapter.normalize_search_response(
                        parsed
                    )
                )

            return {
                "isError": True,
                "message": "No valid JSON MCP content.",
            }

        # Handle our MutualFundTools ToolResponse.
        if response.get("status") == "error":
            return {
                "isError": True,
                "message": "Mutual fund lookup failed.",
                "error": response.get("error"),
            }

        if response.get("status") == "success":

            data = response.get("data")

            if not isinstance(data, list):
                return {
                    "isError": True,
                    "message": "Invalid mutual fund search data.",
                }

            return {"data": data}

        return {
            "isError": True,
            "message": "Unrecognized mutual fund MCP response.",
        }
