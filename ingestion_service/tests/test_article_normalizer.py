from datetime import datetime, timezone

from app.services.article_normalizer import (
    ArticleNormalizer,
)


def test_normalize_url_removes_tracking_parameters():
    normalizer = ArticleNormalizer()

    url = (
        "HTTPS://Example.COM/article/"
        "?utm_source=google"
        "&utm_medium=news"
        "&id=123"
        "#section"
    )

    normalized = normalizer.normalize_url(url)

    assert normalized == (
        "https://example.com/article?id=123"
    )


def test_normalize_url_removes_trailing_slash():
    normalizer = ArticleNormalizer()

    url = "https://example.com/article/"

    normalized = normalizer.normalize_url(url)

    assert normalized == (
        "https://example.com/article"
    )


def test_normalize_url_sorts_query_parameters():
    normalizer = ArticleNormalizer()

    url = (
        "https://example.com/article"
        "?z=3&a=1&b=2"
    )

    normalized = normalizer.normalize_url(url)

    assert normalized == (
        "https://example.com/article?a=1&b=2&z=3"
    )


def test_normalize_url_removes_fragment():
    normalizer = ArticleNormalizer()

    url = (
        "https://example.com/article"
        "?id=123#comments"
    )

    normalized = normalizer.normalize_url(url)

    assert normalized == (
        "https://example.com/article?id=123"
    )


def test_normalize_text():
    normalizer = ArticleNormalizer()

    value = """
        TCS     reported

        strong   quarterly results.
    """

    normalized = normalizer.normalize_text(value)

    assert normalized == (
        "TCS reported strong quarterly results."
    )


def test_generate_hash():
    normalizer = ArticleNormalizer()

    first = normalizer.generate_hash(
        "https://example.com/article"
    )

    second = normalizer.generate_hash(
        "https://example.com/article"
    )

    assert first == second
    assert len(first) == 64


def test_generate_hash_changes_with_content():
    normalizer = ArticleNormalizer()

    first = normalizer.generate_hash(
        "article content one"
    )

    second = normalizer.generate_hash(
        "article content two"
    )

    assert first != second


def test_normalize_datetime_to_utc():
    normalizer = ArticleNormalizer()

    value = datetime(
        2026,
        9,
        5,
        10,
        0,
        tzinfo=timezone.utc,
    )

    normalized = normalizer.normalize_datetime(value)

    assert normalized == value


def test_normalize_article_generates_hashes():
    normalizer = ArticleNormalizer()

    article = {
        "url": (
            "https://Example.com/article/"
            "?utm_source=google"
        ),
        "title": (
            "  TCS    reports strong results  "
        ),
        "content": (
            "TCS   reported strong results "
            "during the quarter."
        ),
        "source": "  Example News  ",
        "published_at": None,
    }

    normalized = normalizer.normalize(article)

    assert normalized["url"] == (
        "https://example.com/article"
    )

    assert normalized["title"] == (
        "TCS reports strong results"
    )

    assert normalized["content"] == (
        "TCS reported strong results during the quarter."
    )

    assert normalized["source"] == "Example News"

    assert normalized["article_key"] is not None
    assert normalized["content_hash"] is not None

    assert len(normalized["article_key"]) == 64
    assert len(normalized["content_hash"]) == 64


def test_same_url_produces_same_article_key():
    normalizer = ArticleNormalizer()

    article_one = {
        "url": (
            "https://example.com/article"
            "?utm_source=google"
        ),
        "title": "Article",
        "content": "Content",
    }

    article_two = {
        "url": "https://example.com/article",
        "title": "Article",
        "content": "Different content",
    }

    normalized_one = normalizer.normalize(
        article_one
    )

    normalized_two = normalizer.normalize(
        article_two
    )

    assert (
        normalized_one["article_key"]
        == normalized_two["article_key"]
    )

    assert (
        normalized_one["content_hash"]
        != normalized_two["content_hash"]
    )