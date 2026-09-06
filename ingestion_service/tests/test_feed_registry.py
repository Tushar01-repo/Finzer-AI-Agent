from pathlib import Path
import pytest

from app.config.feed_registry import FeedRegistry


FEEDS_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "config"
    / "feeds.yaml"
)


@pytest.fixture
def registry():
    return FeedRegistry(FEEDS_PATH)


def test_total_feed_count(registry):
    assert registry.count() == 25


def test_all_feeds_are_enabled(registry):
    assert len(registry.enabled()) == 25


def test_feed_ids_are_deterministic(registry):
    for feed in registry.all():
        expected_feed_id = (
            f"{feed['feed_type']}_{feed['feed_value']}"
        )

        assert feed["feed_id"] == expected_feed_id


def test_feed_ids_are_unique(registry):
    feed_ids = [
        feed["feed_id"]
        for feed in registry.all()
    ]

    assert len(feed_ids) == len(set(feed_ids))


def test_get_existing_feed(registry):
    feed = registry.get("company_tcs")

    assert feed["feed_id"] == "company_tcs"
    assert feed["feed_type"] == "company"
    assert feed["feed_value"] == "tcs"
    assert feed["enabled"] is True


def test_get_unknown_feed(registry):
    with pytest.raises(KeyError):
        registry.get("does_not_exist")