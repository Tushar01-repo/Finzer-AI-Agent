
"""Functional tests for Finzer Entity Resolver â€” Phase 3.3.

Run:
    python -m pytest .\\test_entity_resolver.py -v
"""

import pytest

from app.agent.entities import (
    EntityResolver,
    ResolutionStatus,
)
from app.agent.state import (
    AgentState,
    EntityType,
    ResolvedEntity,
)


@pytest.fixture
def resolver():
    return EntityResolver()


@pytest.fixture
def fund():
    return ResolvedEntity(
        entity_type=EntityType.MUTUAL_FUND,
        name="SBI Small Cap Fund",
        canonical_id="125497",
    )


@pytest.fixture
def second_fund():
    return ResolvedEntity(
        entity_type=EntityType.MUTUAL_FUND,
        name="HDFC Small Cap Fund",
        canonical_id="130503",
    )


@pytest.fixture
def gold():
    return ResolvedEntity(
        entity_type=EntityType.GOLD,
        name="Gold",
        canonical_id=None,
    )


def make_state(entities=None):
    return AgentState(
        user_query="Test query",
        active_entities=entities or [],
    )


def test_resolve_explicit_name(resolver, fund):
    result = resolver.resolve(
        "Tell me about SBI Small Cap Fund",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.canonical_id == "125497"


def test_resolve_canonical_id(resolver, fund):
    result = resolver.resolve(
        "Get NAV for scheme 125497",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.name == fund.name


def test_resolve_its_nav(resolver, fund):
    result = resolver.resolve(
        "What is its latest NAV?",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.canonical_id == "125497"


def test_resolve_that_fund(resolver, fund):
    result = resolver.resolve(
        "What about that fund?",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.entity_type == EntityType.MUTUAL_FUND


def test_resolve_same_ipo(resolver):
    ipo = ResolvedEntity(
        entity_type=EntityType.IPO_DOCUMENT,
        name="Example IPO DRHP",
        canonical_id="example-drhp",
    )

    result = resolver.resolve(
        "Summarize the same IPO document",
        make_state([ipo]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.canonical_id == "example-drhp"


def test_ambiguous_fund_reference(
    resolver,
    fund,
    second_fund,
):
    result = resolver.resolve(
        "What is its NAV?",
        make_state([fund, second_fund]),
    )

    assert result.status == ResolutionStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_explicit_name_disambiguates(
    resolver,
    fund,
    second_fund,
):
    result = resolver.resolve(
        "What is the NAV of HDFC Small Cap Fund?",
        make_state([fund, second_fund]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.canonical_id == "130503"


def test_unknown_fund_requires_lookup(resolver, fund):
    result = resolver.resolve(
        "Tell me about a new mutual fund",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.UNRESOLVED
    assert result.entity is None


def test_no_active_entity_for_reference(resolver):
    result = resolver.resolve(
        "What is its NAV?",
        make_state(),
    )

    assert result.status == ResolutionStatus.UNRESOLVED


def test_empty_query(resolver, fund):
    result = resolver.resolve(
        "   ",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.NOT_APPLICABLE


def test_unrelated_query(resolver, fund):
    result = resolver.resolve(
        "Hello, how are you?",
        make_state([fund]),
    )

    assert result.status == ResolutionStatus.NOT_APPLICABLE


def test_cross_entity_type_resolution(
    resolver,
    fund,
    gold,
):
    result = resolver.resolve(
        "What is its gold price?",
        make_state([fund, gold]),
    )

    assert result.status == ResolutionStatus.RESOLVED
    assert result.entity.entity_type == EntityType.GOLD


def test_track_adds_entity(resolver, fund):
    original = make_state()

    updated = resolver.track(original, fund)

    assert len(updated.active_entities) == 1
    assert updated.active_entities[0].canonical_id == "125497"
    assert original.active_entities == []


def test_track_replaces_duplicate(resolver, fund):
    original = make_state([fund])

    updated_fund = fund.model_copy(
        update={"name": "SBI Small Cap Direct Growth"}
    )

    updated = resolver.track(original, updated_fund)

    assert len(updated.active_entities) == 1
    assert (
        updated.active_entities[0].name
        == "SBI Small Cap Direct Growth"
    )


def test_track_preserves_different_entities(
    resolver,
    fund,
    second_fund,
):
    original = make_state([fund])

    updated = resolver.track(original, second_fund)

    assert len(updated.active_entities) == 2


def test_track_does_not_mutate_original(
    resolver,
    fund,
):
    original = make_state()

    before = original.model_dump_json()

    resolver.track(original, fund)

    assert original.model_dump_json() == before


def test_resolve_does_not_mutate_state(
    resolver,
    fund,
):
    state = make_state([fund])
    before = state.model_dump_json()

    resolver.resolve(
        "What is its NAV?",
        state,
    )

    assert state.model_dump_json() == before


def test_unknown_explicit_fund_not_reused(
    resolver,
    fund,
):
    """Regression: a new fund name must not resolve to SBI."""

    result = resolver.resolve(
        "Tell me about HDFC Small Cap Fund",
        make_state([fund]),
    )

    assert result.status != ResolutionStatus.RESOLVED
    assert result.entity is None

