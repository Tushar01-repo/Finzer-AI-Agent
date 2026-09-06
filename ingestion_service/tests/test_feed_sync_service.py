from unittest.mock import MagicMock

from app.models.database_schema import FeedRecord
from app.services.feed_sync_service import FeedSyncService


def test_syncs_all_configured_feeds():
    feed_registry = MagicMock()
    feed_repository = MagicMock()

    feed_registry.all.return_value = [
        {
            "feed_id": "company_tcs",
            "feed_type": "company",
            "feed_value": "tcs",
            "query": "TCS stock",
            "enabled": True,
        },
        {
            "feed_id": "sector_it",
            "feed_type": "sector",
            "feed_value": "it",
            "query": "India IT sector",
            "enabled": True,
        },
    ]

    service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    result = service.sync()

    assert result == 2

    assert feed_repository.upsert.call_count == 2

    first_record = feed_repository.upsert.call_args_list[0].args[0]
    second_record = feed_repository.upsert.call_args_list[1].args[0]

    assert isinstance(first_record, FeedRecord)
    assert first_record.feed_id == "company_tcs"
    assert first_record.feed_type == "company"
    assert first_record.feed_value == "tcs"
    assert first_record.query == "TCS stock"
    assert first_record.enabled is True

    assert isinstance(second_record, FeedRecord)
    assert second_record.feed_id == "sector_it"
    assert second_record.feed_type == "sector"
    assert second_record.feed_value == "it"
    assert second_record.query == "India IT sector"
    assert second_record.enabled is True


def test_sync_returns_zero_when_no_feeds_configured():
    feed_registry = MagicMock()
    feed_repository = MagicMock()

    feed_registry.all.return_value = []

    service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    result = service.sync()

    assert result == 0

    feed_repository.upsert.assert_not_called()


def test_sync_preserves_disabled_feed():
    feed_registry = MagicMock()
    feed_repository = MagicMock()

    feed_registry.all.return_value = [
        {
            "feed_id": "company_tcs",
            "feed_type": "company",
            "feed_value": "tcs",
            "query": "TCS stock",
            "enabled": False,
        },
    ]

    service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    result = service.sync()

    assert result == 1

    record = feed_repository.upsert.call_args.args[0]

    assert record.feed_id == "company_tcs"
    assert record.enabled is False


def test_sync_calls_registry_all():
    feed_registry = MagicMock()
    feed_repository = MagicMock()

    feed_registry.all.return_value = []

    service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    service.sync()

    feed_registry.all.assert_called_once()