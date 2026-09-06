from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.database_schema import FeedRecord
from app.repositories.feed_repository import FeedRepository


def create_database_mock():
    database = MagicMock()

    connection = MagicMock()
    cursor = MagicMock()

    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    database.connect.return_value = connection

    return database, connection, cursor


def test_upsert_feed():
    database, _, _ = create_database_mock()

    repository = FeedRepository(database)

    feed = FeedRecord(
        feed_id="company_tcs",
        feed_type="company",
        feed_value="tcs",
        query="TCS stock",
        enabled=True,
    )

    repository.upsert(feed)

    database.execute.assert_called_once()

    query, params = database.execute.call_args.args

    assert "INSERT INTO feeds" in query
    assert "ON CONFLICT (feed_id)" in query

    assert params == (
        "company_tcs",
        "company",
        "tcs",
        "TCS stock",
        True,
    )


def test_get_by_id_returns_feed():
    database, _, cursor = create_database_mock()

    created_at = datetime.now(timezone.utc)

    cursor.fetchone.return_value = (
        "company_tcs",
        "company",
        "tcs",
        "TCS stock",
        True,
        created_at,
    )

    repository = FeedRepository(database)

    result = repository.get_by_id("company_tcs")

    cursor.execute.assert_called_once()

    assert result is not None
    assert result.feed_id == "company_tcs"
    assert result.feed_type == "company"
    assert result.feed_value == "tcs"
    assert result.query == "TCS stock"
    assert result.enabled is True
    assert result.created_at == created_at


def test_get_by_id_returns_none_when_not_found():
    database, _, cursor = create_database_mock()

    cursor.fetchone.return_value = None

    repository = FeedRepository(database)

    result = repository.get_by_id("unknown_feed")

    assert result is None


def test_get_all_returns_feeds():
    database, _, cursor = create_database_mock()

    created_at = datetime.now(timezone.utc)

    cursor.fetchall.return_value = [
        (
            "company_tcs",
            "company",
            "tcs",
            "TCS stock",
            True,
            created_at,
        ),
        (
            "company_reliance",
            "company",
            "reliance",
            "Reliance stock",
            True,
            created_at,
        ),
    ]

    repository = FeedRepository(database)

    result = repository.get_all()

    assert len(result) == 2

    assert result[0].feed_id == "company_tcs"
    assert result[1].feed_id == "company_reliance"


def test_get_all_returns_empty_list():
    database, _, cursor = create_database_mock()

    cursor.fetchall.return_value = []

    repository = FeedRepository(database)

    result = repository.get_all()

    assert result == []


def test_get_enabled_returns_only_enabled_feeds():
    database, _, cursor = create_database_mock()

    created_at = datetime.now(timezone.utc)

    cursor.fetchall.return_value = [
        (
            "company_tcs",
            "company",
            "tcs",
            "TCS stock",
            True,
            created_at,
        ),
    ]

    repository = FeedRepository(database)

    result = repository.get_enabled()

    query = cursor.execute.call_args.args[0]

    assert "WHERE enabled = TRUE" in query

    assert len(result) == 1
    assert result[0].feed_id == "company_tcs"
    assert result[0].enabled is True


def test_get_enabled_returns_empty_list():
    database, _, cursor = create_database_mock()

    cursor.fetchall.return_value = []

    repository = FeedRepository(database)

    result = repository.get_enabled()

    assert result == []