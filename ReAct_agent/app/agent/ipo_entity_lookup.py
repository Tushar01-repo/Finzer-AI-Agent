
"""IPO document entity lookup for the Finzer ReAct Agent.

Phase 3.5 — Resolve indexed IPO documents from metadata.

This module:
- Does not access PostgreSQL.
- Does not call MCP or an LLM.
- Does not generate document keys.
- Does not mutate AgentState.

The ingestion layer supplies document metadata.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import EntityType, ResolvedEntity


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
