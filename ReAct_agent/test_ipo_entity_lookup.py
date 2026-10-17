
"""Unit tests for IPO Document Entity Lookup.

Run:
    python -m pytest test_ipo_entity_lookup.py -v
"""

from __future__ import annotations

import pytest

from app.agent.entities import (
    IPOEntityLookupService,
    IPOLookupStatus,
)
from app.agent.state import EntityType


@pytest.fixture
def service():
    return IPOEntityLookupService()


@pytest.fixture
def documents():
    return [
        {
            "document_id": 1,
            "document_key": "hitech-drhp-v1",
            "company_name": "Hi-Tech Flow Solutions",
            "document_type": "DRHP",
            "source_title": "Draft Red Herring Prospectus",
            "status": "embedded",
        },
        {
            "document_id": 2,
            "document_key": "hitech-rhp-v1",
            "company_name": "Hi-Tech Flow Solutions",
            "document_type": "RHP",
            "status": "embedded",
        },
        {
            "document_id": 3,
            "document_key": "other-drhp-v1",
            "company_name": "Example Industries",
            "document_type": "DRHP",
            "status": "embedded",
        },
    ]


def test_resolve_unique_drhp(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        documents,
    )

    assert result.status == IPOLookupStatus.RESOLVED
    assert result.entity is not None
    assert result.entity.canonical_id == "hitech-drhp-v1"
    assert result.entity.entity_type == EntityType.IPO_DOCUMENT


def test_resolve_unique_rhp(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions RHP",
        documents,
    )

    assert result.status == IPOLookupStatus.RESOLVED
    assert result.entity.canonical_id == "hitech-rhp-v1"


def test_ambiguous_without_document_type(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions",
        documents,
    )

    assert result.status == IPOLookupStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_unknown_company(service, documents):
    result = service.resolve(
        "Summarize Unknown Company DRHP",
        documents,
    )

    assert result.status == IPOLookupStatus.NOT_FOUND


def test_wrong_document_type(service, documents):
    result = service.resolve(
        "Summarize Example Industries RHP",
        documents,
    )

    assert result.status == IPOLookupStatus.NOT_FOUND


def test_empty_query(service, documents):
    result = service.resolve("", documents)

    assert result.status == IPOLookupStatus.NOT_FOUND


def test_empty_document_list(service):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        [],
    )

    assert result.status == IPOLookupStatus.NOT_FOUND


def test_response_wrapped_in_documents(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        {"documents": documents},
    )

    assert result.status == IPOLookupStatus.RESOLVED


def test_response_wrapped_in_data(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        {"data": documents},
    )

    assert result.status == IPOLookupStatus.RESOLVED


def test_upstream_error(service):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        {"status": "error", "message": "Database unavailable"},
    )

    assert result.status == IPOLookupStatus.INVALID_RESPONSE


def test_malformed_response(service):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        {"documents": "not-a-list"},
    )

    assert result.status == IPOLookupStatus.INVALID_RESPONSE


def test_invalid_document_skipped(service):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        [
            {"company_name": "Hi-Tech Flow Solutions"},
            {
                "document_key": "valid-key",
                "company_name": "Hi-Tech Flow Solutions",
                "document_type": "DRHP",
            },
        ],
    )

    assert result.status == IPOLookupStatus.RESOLVED
    assert result.entity.canonical_id == "valid-key"


def test_duplicate_document_key(service):
    document = {
        "document_key": "same-key",
        "company_name": "Hi-Tech Flow Solutions",
        "document_type": "DRHP",
    }

    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        [document, document],
    )

    assert result.status == IPOLookupStatus.RESOLVED


def test_multiple_drhp_versions(service):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        [
            {
                "document_key": "version-1",
                "company_name": "Hi-Tech Flow Solutions",
                "document_type": "DRHP",
            },
            {
                "document_key": "version-2",
                "company_name": "Hi-Tech Flow Solutions",
                "document_type": "DRHP",
            },
        ],
    )

    assert result.status == IPOLookupStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_company_name_case_insensitive(service, documents):
    result = service.resolve(
        "summarize HI-TECH FLOW SOLUTIONS drhp",
        documents,
    )

    assert result.status == IPOLookupStatus.RESOLVED


def test_partial_company_name_not_matched(service, documents):
    result = service.resolve(
        "Summarize Flow Solutions DRHP",
        documents,
    )

    assert result.status == IPOLookupStatus.NOT_FOUND


def test_preserves_metadata(service, documents):
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        documents,
    )

    assert result.entity.metadata["document_id"] == 1
    assert result.entity.metadata["status"] == "embedded"
    assert result.entity.metadata["document_type"] == "DRHP"


def test_no_database_dependency(service, documents):
    """The resolver works entirely from supplied metadata."""
    result = service.resolve(
        "Summarize Hi-Tech Flow Solutions DRHP",
        documents,
    )

    assert result.status == IPOLookupStatus.RESOLVED

