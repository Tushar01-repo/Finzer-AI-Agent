from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.database_schema import ArticleFeedRecord
from app.repositories.article_feed_repository import ArticleFeedRepository


def create_database_mock():
    database = MagicMock()

    connection = MagicMock()
    cursor = MagicMock()

    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    database.connect.return_value = connection

    return database, connection, cursor


def test_add_article_feed_relationship():
    database, _, _ = create_database_mock()

    repository = ArticleFeedRepository(database)

    first_seen_at = datetime.now(timezone.utc)

    record = ArticleFeedRecord(
        article_key="a" * 64,
        feed_id="company_tcs",
        first_seen_at=first_seen_at,
    )

    repository.add(record)

    database.execute.assert_called_once()

    query, params = database.execute.call_args.args

    assert "INSERT INTO article_feeds" in query
    assert "ON CONFLICT (article_key, feed_id)" in query
    assert "DO NOTHING" in query

    assert params == (
        "a" * 64,
        "company_tcs",
        first_seen_at,
    )


def test_add_generates_first_seen_at_when_missing():
    database, _, _ = create_database_mock()

    repository = ArticleFeedRepository(database)

    record = ArticleFeedRecord(
        article_key="a" * 64,
        feed_id="company_tcs",
    )

    repository.add(record)

    _, params = database.execute.call_args.args

    assert params[0] == "a" * 64
    assert params[1] == "company_tcs"
    assert isinstance(params[2], datetime)
    assert params[2].tzinfo == timezone.utc


def test_get_feeds_for_article():
    database, _, cursor = create_database_mock()

    cursor.fetchall.return_value = [
        ("company_tcs",),
        ("market_india",),
        ("sector_it",),
    ]

    repository = ArticleFeedRepository(database)

    result = repository.get_feeds_for_article(
        "a" * 64
    )

    cursor.execute.assert_called_once()

    query, params = cursor.execute.call_args.args

    assert "SELECT feed_id" in query
    assert "WHERE article_key = %s" in query
    assert "ORDER BY feed_id" in query

    assert params == ("a" * 64,)

    assert result == [
        "company_tcs",
        "market_india",
        "sector_it",
    ]


def test_get_feeds_for_article_returns_empty_list():
    database, _, cursor = create_database_mock()

    cursor.fetchall.return_value = []

    repository = ArticleFeedRepository(database)

    result = repository.get_feeds_for_article(
        "a" * 64
    )

    assert result == []


def test_exists_returns_true():
    database, _, cursor = create_database_mock()

    cursor.fetchone.return_value = (1,)

    repository = ArticleFeedRepository(database)

    result = repository.exists(
        "a" * 64,
        "company_tcs",
    )

    cursor.execute.assert_called_once()

    query, params = cursor.execute.call_args.args

    assert "SELECT 1" in query
    assert "WHERE article_key = %s" in query
    assert "AND feed_id = %s" in query
    assert "LIMIT 1" in query

    assert params == (
        "a" * 64,
        "company_tcs",
    )

    assert result is True


def test_exists_returns_false():
    database, _, cursor = create_database_mock()

    cursor.fetchone.return_value = None

    repository = ArticleFeedRepository(database)

    result = repository.exists(
        "a" * 64,
        "company_tcs",
    )

    assert result is False