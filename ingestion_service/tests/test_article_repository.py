from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.database_schema import ArticleRecord
from app.repositories.article_repository import ArticleRepository


def create_database_mock():
    database = MagicMock()

    connection = MagicMock()
    cursor = MagicMock()

    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    database.connect.return_value = connection

    return database, connection, cursor


def create_article():
    return ArticleRecord(
        article_key="a" * 64,
        title="TCS reports strong quarterly results",
        url="https://example.com/tcs-results",
        source="Example News",
        authors=["John Doe"],
        published_at=datetime.now(timezone.utc),
        content="TCS reported strong quarterly results.",
        content_hash="b" * 64,
        summary=None,
        processing_status="pending",
    )


def test_upsert_article():
    database, _, _ = create_database_mock()

    repository = ArticleRepository(database)
    article = create_article()

    repository.upsert(article)

    database.execute.assert_called_once()

    query, params = database.execute.call_args.args

    assert "INSERT INTO articles" in query
    assert "ON CONFLICT (article_key)" in query

    assert params[0] == article.article_key
    assert params[1] == article.title
    assert params[2] == article.url
    assert params[3] == article.source
    assert params[4] == article.authors
    assert params[6] == article.content
    assert params[7] == article.content_hash


def test_get_by_key_returns_article():
    database, _, cursor = create_database_mock()

    created_at = datetime.now(timezone.utc)
    updated_at = datetime.now(timezone.utc)

    cursor.fetchone.return_value = (
        "a" * 64,
        "TCS results",
        "https://example.com/tcs",
        "Example News",
        ["John Doe"],
        created_at,
        "TCS reported strong results.",
        "b" * 64,
        "Strong quarterly performance.",
        "summarized",
        created_at,
        updated_at,
    )

    repository = ArticleRepository(database)

    result = repository.get_by_key("a" * 64)

    assert result is not None
    assert result.article_key == "a" * 64
    assert result.title == "TCS results"
    assert result.url == "https://example.com/tcs"
    assert result.source == "Example News"
    assert result.authors == ["John Doe"]
    assert result.content_hash == "b" * 64
    assert result.summary == "Strong quarterly performance."
    assert result.processing_status == "summarized"
    assert result.created_at == created_at
    assert result.updated_at == updated_at


def test_get_by_key_returns_none_when_not_found():
    database, _, cursor = create_database_mock()

    cursor.fetchone.return_value = None

    repository = ArticleRepository(database)

    result = repository.get_by_key("a" * 64)

    assert result is None


def test_update_summary():
    database, _, _ = create_database_mock()

    repository = ArticleRepository(database)

    article_key = "a" * 64
    summary = "TCS reported strong quarterly performance."

    repository.update_summary(
        article_key,
        summary,
    )

    database.execute.assert_called_once()

    query, params = database.execute.call_args.args

    assert "UPDATE articles" in query
    assert "summary = %s" in query
    assert "processing_status = 'summarized'" in query

    assert params == (
        summary,
        article_key,
    )


def test_update_processing_status():
    database, _, _ = create_database_mock()

    repository = ArticleRepository(database)

    article_key = "a" * 64

    repository.update_processing_status(
        article_key,
        "failed",
    )

    database.execute.assert_called_once()

    query, params = database.execute.call_args.args

    assert "UPDATE articles" in query
    assert "processing_status = %s" in query

    assert params == (
        "failed",
        article_key,
    )


def test_get_pending_articles():
    database, _, cursor = create_database_mock()

    created_at = datetime.now(timezone.utc)

    cursor.fetchall.return_value = [
        (
            "a" * 64,
            "TCS results",
            "https://example.com/tcs",
            "Example News",
            ["John Doe"],
            created_at,
            "TCS reported strong results.",
            "b" * 64,
            None,
            "pending",
            created_at,
            created_at,
        ),
        (
            "c" * 64,
            "Reliance results",
            "https://example.com/reliance",
            "Example News",
            ["Jane Doe"],
            created_at,
            "Reliance reported strong results.",
            "d" * 64,
            None,
            "pending",
            created_at,
            created_at,
        ),
    ]

    repository = ArticleRepository(database)

    result = repository.get_pending_articles(limit=10)

    assert len(result) == 2
    assert result[0].article_key == "a" * 64
    assert result[1].article_key == "c" * 64

    query, params = cursor.execute.call_args.args

    assert "processing_status = 'pending'" in query
    assert "LIMIT %s" in query
    assert params == (10,)


def test_get_pending_articles_returns_empty_list():
    database, _, cursor = create_database_mock()

    cursor.fetchall.return_value = []

    repository = ArticleRepository(database)

    result = repository.get_pending_articles()

    assert result == []


def test_get_pending_articles_rejects_invalid_limit():
    database, _, _ = create_database_mock()

    repository = ArticleRepository(database)

    with pytest.raises(
        ValueError,
        match="limit must be greater than zero",
    ):
        repository.get_pending_articles(limit=0)


def test_get_pending_articles_rejects_negative_limit():
    database, _, _ = create_database_mock()

    repository = ArticleRepository(database)

    with pytest.raises(
        ValueError,
        match="limit must be greater than zero",
    ):
        repository.get_pending_articles(limit=-1)