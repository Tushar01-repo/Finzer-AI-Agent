from unittest.mock import Mock

from app.services.ingestion_service import IngestionService


def create_service():
    feed_registry = Mock()
    feed_fetcher = Mock()
    rss_parser = Mock()
    url_resolver = Mock()
    content_extractor = Mock()
    normalizer = Mock()
    article_repository = Mock()
    article_feed_repository = Mock()
    queue_publisher = Mock()

    service = IngestionService(
        feed_registry=feed_registry,
        feed_fetcher=feed_fetcher,
        rss_parser=rss_parser,
        url_resolver=url_resolver,
        content_extractor=content_extractor,
        normalizer=normalizer,
        article_repository=article_repository,
        article_feed_repository=article_feed_repository,
        queue_publisher=queue_publisher,
    )

    return service


def test_new_article_is_saved_and_published():
    service = create_service()

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS",
        "enabled": True,
    }

    service.feed_registry.enabled.return_value = [feed]

    service.feed_fetcher.fetch.return_value = b"rss"

    service.rss_parser.parse.return_value = [
        {
            "feed_id": "company_tcs",
            "rss_title": "TCS announces results",
            "rss_published": "Mon, 01 Sep 2026 10:00:00 GMT",
            "rss_source": "Economic Times",
            "google_news_link": "https://news.google.com/rss/articles/test",
        }
    ]

    service.url_resolver.resolve.return_value = (
        "https://example.com/tcs-results"
    )

    service.content_extractor.extract.return_value = {
        "status": "success",
        "title": "TCS announces results",
        "source": "Economic Times",
        "authors": ["Author"],
        "published_at": "2026-09-01T10:00:00+00:00",
        "content": "TCS reported strong quarterly results.",
    }

    service.normalizer.normalize.return_value = {
        "article_key": "a" * 64,
        "title": "TCS announces results",
        "url": "https://example.com/tcs-results",
        "source": "Economic Times",
        "authors": ["Author"],
        "published_at": "2026-09-01T10:00:00+00:00",
        "content": "TCS reported strong quarterly results.",
        "content_hash": "b" * 64,
    }

    service.article_repository.get_by_key.return_value = None

    stats = service.ingest()

    assert stats["feeds_processed"] == 1
    assert stats["rss_entries"] == 1
    assert stats["articles_discovered"] == 1
    assert stats["articles_inserted"] == 1
    assert stats["articles_updated"] == 0
    assert stats["articles_failed"] == 0
    assert stats["messages_published"] == 1

    service.article_repository.upsert.assert_called_once()
    service.article_feed_repository.add.assert_called_once()
    service.queue_publisher.publish.assert_called_once_with(
        {"article_key": "a" * 64}
    )


def test_existing_article_is_not_published_again():
    service = create_service()

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS",
        "enabled": True,
    }

    service.feed_registry.enabled.return_value = [feed]

    service.feed_fetcher.fetch.return_value = b"rss"

    service.rss_parser.parse.return_value = [
        {
            "feed_id": "company_tcs",
            "rss_title": "TCS results",
            "rss_published": None,
            "rss_source": "Economic Times",
            "google_news_link": "https://news.google.com/rss/articles/test",
        }
    ]

    service.url_resolver.resolve.return_value = (
        "https://example.com/tcs-results"
    )

    service.content_extractor.extract.return_value = {
        "status": "success",
        "title": "TCS results",
        "source": "Economic Times",
        "authors": [],
        "published_at": None,
        "content": "Updated TCS results content.",
    }

    service.normalizer.normalize.return_value = {
        "article_key": "a" * 64,
        "title": "TCS results",
        "url": "https://example.com/tcs-results",
        "source": "Economic Times",
        "authors": [],
        "published_at": None,
        "content": "Updated TCS results content.",
        "content_hash": "c" * 64,
    }

    existing_article = Mock()
    existing_article.summary = "Existing summary"
    existing_article.processing_status = "summarized"
    existing_article.created_at = None
    existing_article.updated_at = None

    service.article_repository.get_by_key.return_value = existing_article

    stats = service.ingest()

    assert stats["articles_inserted"] == 0
    assert stats["articles_updated"] == 1
    assert stats["messages_published"] == 0

    service.article_repository.upsert.assert_called_once()
    service.article_feed_repository.add.assert_called_once()
    service.queue_publisher.publish.assert_not_called()


def test_article_is_linked_to_multiple_feeds():
    service = create_service()

    feeds = [
        {
            "feed_id": "company_tcs",
            "feed_type": "company",
            "feed_value": "tcs",
            "query": "TCS",
            "enabled": True,
        },
        {
            "feed_id": "sector_it",
            "feed_type": "sector",
            "feed_value": "it",
            "query": "IT sector",
            "enabled": True,
        },
    ]

    service.feed_registry.enabled.return_value = feeds

    service.feed_fetcher.fetch.return_value = b"rss"

    service.rss_parser.parse.return_value = [
        {
            "feed_id": "test",
            "rss_title": "TCS results",
            "rss_published": None,
            "rss_source": "Economic Times",
            "google_news_link": "https://news.google.com/rss/articles/test",
        }
    ]

    service.url_resolver.resolve.return_value = (
        "https://example.com/tcs-results"
    )

    service.content_extractor.extract.return_value = {
        "status": "success",
        "title": "TCS results",
        "source": "Economic Times",
        "authors": [],
        "published_at": None,
        "content": "TCS results content.",
    }

    service.normalizer.normalize.return_value = {
        "article_key": "a" * 64,
        "title": "TCS results",
        "url": "https://example.com/tcs-results",
        "source": "Economic Times",
        "authors": [],
        "published_at": None,
        "content": "TCS results content.",
        "content_hash": "b" * 64,
    }

    # First feed discovers the article.
    # Second feed sees the same article.
    service.article_repository.get_by_key.side_effect = [
        None,
        Mock(
            summary="Existing summary",
            processing_status="summarized",
            created_at=None,
            updated_at=None,
        ),
    ]

    stats = service.ingest()

    assert stats["feeds_processed"] == 2
    assert stats["articles_discovered"] == 2
    assert stats["articles_inserted"] == 1
    assert stats["articles_updated"] == 1
    assert stats["messages_published"] == 1

    assert service.article_feed_repository.add.call_count == 2
    assert service.queue_publisher.publish.call_count == 1


def test_failed_article_does_not_stop_other_articles():
    service = create_service()

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS",
        "enabled": True,
    }

    service.feed_registry.enabled.return_value = [feed]

    service.feed_fetcher.fetch.return_value = b"rss"

    service.rss_parser.parse.return_value = [
        {
            "feed_id": "company_tcs",
            "rss_title": "Bad article",
            "rss_published": None,
            "rss_source": "Source",
            "google_news_link": "https://news.google.com/rss/articles/bad",
        },
        {
            "feed_id": "company_tcs",
            "rss_title": "Good article",
            "rss_published": None,
            "rss_source": "Source",
            "google_news_link": "https://news.google.com/rss/articles/good",
        },
    ]

    service.url_resolver.resolve.side_effect = [
        "https://example.com/bad",
        "https://example.com/good",
    ]

    service.content_extractor.extract.side_effect = [
        {
            "status": "failed",
            "error": "403 Forbidden",
        },
        {
            "status": "success",
            "title": "Good article",
            "source": "Source",
            "authors": [],
            "published_at": None,
            "content": "Good article content.",
        },
    ]

    service.normalizer.normalize.return_value = {
        "article_key": "a" * 64,
        "title": "Good article",
        "url": "https://example.com/good",
        "source": "Source",
        "authors": [],
        "published_at": None,
        "content": "Good article content.",
        "content_hash": "b" * 64,
    }

    service.article_repository.get_by_key.return_value = None

    stats = service.ingest()

    assert stats["rss_entries"] == 2
    assert stats["articles_discovered"] == 1
    assert stats["articles_failed"] == 1
    assert stats["articles_inserted"] == 1
    assert stats["messages_published"] == 1