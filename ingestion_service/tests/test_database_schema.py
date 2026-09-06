from dataclasses import fields

from app.models.database_schema import (
    ArticleFeedRecord,
    ArticleRecord,
    FeedRecord,
)


def test_feed_record_fields():
    field_names = {
        field.name
        for field in fields(FeedRecord)
    }

    assert field_names == {
        "feed_id",
        "feed_type",
        "feed_value",
        "query",
        "enabled",
        "created_at",
    }


def test_article_record_defaults():
    article = ArticleRecord(
        article_key="a" * 64,
        title="TCS Results",
        url="https://example.com/article",
        source="Example News",
        authors=["John Doe"],
        published_at=None,
        content="Article content",
        content_hash="b" * 64,
    )

    assert article.summary is None
    assert article.processing_status == "pending"
    assert article.created_at is None
    assert article.updated_at is None


def test_article_feed_record():
    relationship = ArticleFeedRecord(
        article_key="a" * 64,
        feed_id="company_tcs",
    )

    assert relationship.article_key == "a" * 64
    assert relationship.feed_id == "company_tcs"
    assert relationship.first_seen_at is None


def test_article_key_length():
    article = ArticleRecord(
        article_key="a" * 64,
        title="Test",
        url="https://example.com",
        source=None,
        authors=[],
        published_at=None,
        content=None,
        content_hash=None,
    )

    assert len(article.article_key) == 64


def test_article_authors_support_multiple_authors():
    article = ArticleRecord(
        article_key="a" * 64,
        title="Market Update",
        url="https://example.com/article",
        source="Example News",
        authors=[
            "Author One",
            "Author Two",
        ],
        published_at=None,
        content="Content",
        content_hash="b" * 64,
    )

    assert len(article.authors) == 2
    assert article.authors[0] == "Author One"
    assert article.authors[1] == "Author Two"