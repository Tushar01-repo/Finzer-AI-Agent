
"""Functional tests for Finzer Entity Lookup Service.

Phase 3.4 â€” Mutual Fund Canonical Lookup

Run:
    python -m pytest .\\test_entity_lookup.py -v

Expected:
    18 passed
"""

import copy

import pytest

from app.agent.entities import (
    EntityLookupService,
    LookupStatus,
)
from app.agent.state import EntityType


@pytest.fixture
def service():
    return EntityLookupService()


@pytest.fixture
def sbi_fund():
    return {
        "schemeCode": 125497,
        "schemeName": "SBI Small Cap Fund",
    }


def test_exact_name_match(service, sbi_fund):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        [sbi_fund],
    )

    assert result.status == LookupStatus.RESOLVED
    assert result.entity.name == "SBI Small Cap Fund"
    assert result.entity.canonical_id == "125497"
    assert result.entity.entity_type == EntityType.MUTUAL_FUND


def test_case_insensitive_match(service, sbi_fund):
    result = service.resolve_mutual_fund(
        "sbi SMALL cap FUND",
        [sbi_fund],
    )

    assert result.status == LookupStatus.RESOLVED


def test_whitespace_normalization(service, sbi_fund):
    result = service.resolve_mutual_fund(
        "  SBI   Small Cap   Fund  ",
        [sbi_fund],
    )

    assert result.status == LookupStatus.RESOLVED


def test_exact_match_preferred_over_partial(service):
    response = [
        {
            "schemeCode": 125497,
            "schemeName": "SBI Small Cap Fund",
        },
        {
            "schemeCode": 125498,
            "schemeName": "SBI Small Cap Fund Direct Growth",
        },
    ]

    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        response,
    )

    assert result.status == LookupStatus.RESOLVED
    assert result.entity.canonical_id == "125497"


def test_multiple_exact_matches_are_ambiguous(service):
    response = [
        {
            "schemeCode": 111111,
            "schemeName": "Example Small Cap Fund",
        },
        {
            "schemeCode": 222222,
            "schemeName": "Example Small Cap Fund",
        },
    ]

    result = service.resolve_mutual_fund(
        "Example Small Cap Fund",
        response,
    )

    assert result.status == LookupStatus.AMBIGUOUS
    assert len(result.candidates) == 2
    assert result.entity is None


def test_partial_name_requires_clarification(service):
    response = [
        {
            "schemeCode": 111111,
            "schemeName": "HDFC Small Cap Fund Direct Growth",
        },
        {
            "schemeCode": 222222,
            "schemeName": "HDFC Small Cap Fund Regular Growth",
        },
    ]

    result = service.resolve_mutual_fund(
        "HDFC Small Cap Fund",
        response,
    )

    assert result.status == LookupStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_direct_regular_variants_not_auto_selected(service):
    response = [
        {
            "schemeCode": 111111,
            "schemeName": "Example Fund Direct Growth",
        },
        {
            "schemeCode": 222222,
            "schemeName": "Example Fund Regular Growth",
        },
    ]

    result = service.resolve_mutual_fund(
        "Example Fund",
        response,
    )

    assert result.status == LookupStatus.AMBIGUOUS
    assert result.entity is None


def test_empty_results(service):
    result = service.resolve_mutual_fund(
        "Unknown Fund",
        [],
    )

    assert result.status == LookupStatus.NOT_FOUND
    assert result.entity is None
    assert result.candidates == []


def test_empty_query(service, sbi_fund):
    result = service.resolve_mutual_fund(
        "   ",
        [sbi_fund],
    )

    assert result.status == LookupStatus.NOT_FOUND


def test_invalid_response_type(service):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        "unexpected response",
    )

    assert result.status == LookupStatus.INVALID_RESPONSE


def test_failed_mcp_response(service):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        {
            "isError": True,
            "message": "Search failed",
        },
    )

    assert result.status == LookupStatus.INVALID_RESPONSE


@pytest.mark.parametrize(
    "wrapper",
    ["funds", "results", "data"],
)
def test_supported_response_wrappers(
    service,
    sbi_fund,
    wrapper,
):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        {wrapper: [sbi_fund]},
    )

    assert result.status == LookupStatus.RESOLVED


def test_missing_scheme_code_is_rejected(service):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        [
            {
                "schemeName": "SBI Small Cap Fund",
            }
        ],
    )

    assert result.status == LookupStatus.NOT_FOUND


def test_missing_scheme_name_is_rejected(service):
    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        [
            {
                "schemeCode": 125497,
            }
        ],
    )

    assert result.status == LookupStatus.NOT_FOUND


def test_invalid_scheme_code_is_rejected(service):
    response = [
        {
            "schemeCode": "not-a-number",
            "schemeName": "SBI Small Cap Fund",
        },
        {
            "schemeCode": True,
            "schemeName": "SBI Small Cap Fund",
        },
    ]

    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        response,
    )

    assert result.status == LookupStatus.NOT_FOUND


def test_duplicate_candidates_are_deduplicated(
    service,
    sbi_fund,
):
    response = [
        sbi_fund,
        copy.deepcopy(sbi_fund),
    ]

    result = service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        response,
    )

    assert result.status == LookupStatus.RESOLVED
    assert result.entity.canonical_id == "125497"


def test_lookup_does_not_mutate_response(
    service,
    sbi_fund,
):
    response = [sbi_fund]
    before = copy.deepcopy(response)

    service.resolve_mutual_fund(
        "SBI Small Cap Fund",
        response,
    )

    assert response == before

