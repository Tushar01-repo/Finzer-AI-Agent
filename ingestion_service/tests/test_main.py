from unittest.mock import Mock, patch

from app.main import create_ingestion_service, main


@patch("app.main.QueuePublisher")
@patch("app.main.ArticleFeedRepository")
@patch("app.main.ArticleRepository")
@patch("app.main.FeedRepository")
@patch("app.main.GoogleNewsURLResolver")
@patch("app.main.ArticleContentExtractor")
@patch("app.main.ArticleNormalizer")
@patch("app.main.RSSParser")
@patch("app.main.FeedFetcher")
@patch("app.main.FeedRegistry")
@patch("app.main.PostgresDatabase")
def test_create_ingestion_service_wires_dependencies(
    mock_database,
    mock_feed_registry,
    mock_feed_fetcher,
    mock_rss_parser,
    mock_url_resolver,
    mock_content_extractor,
    mock_normalizer,
    mock_feed_repository,
    mock_article_repository,
    mock_article_feed_repository,
    mock_queue_publisher,
):
    service = create_ingestion_service()

    assert service is not None

    mock_database.assert_called_once()
    mock_feed_registry.assert_called_once()
    mock_feed_fetcher.assert_called_once()
    mock_rss_parser.assert_called_once()
    mock_url_resolver.assert_called_once()
    mock_content_extractor.assert_called_once()
    mock_normalizer.assert_called_once()
    mock_feed_repository.assert_called_once()
    mock_article_repository.assert_called_once()
    mock_article_feed_repository.assert_called_once()
    mock_queue_publisher.assert_called_once()


@patch("app.main.PostgresDatabase")
def test_initialize_database(mock_database):
    database = mock_database.return_value

    from app.main import initialize_database

    initialize_database()

    database.initialize_schema.assert_called_once()


@patch("app.main.FeedRepository")
@patch("app.main.FeedRegistry")
@patch("app.main.PostgresDatabase")
def test_sync_feeds(
    mock_database,
    mock_feed_registry,
    mock_feed_repository,
):
    feed_sync_service = Mock()

    with patch(
        "app.main.FeedSyncService",
        return_value=feed_sync_service,
    ):
        feed_sync_service.sync.return_value = 25

        from app.main import sync_feeds

        result = sync_feeds()

    assert result == 25

    feed_sync_service.sync.assert_called_once()


@patch("app.main.sync_feeds")
@patch("app.main.initialize_database")
@patch("app.main.create_ingestion_service")
def test_main_runs_pipeline(
    mock_create_service,
    mock_initialize_database,
    mock_sync_feeds,
):
    ingestion_service = Mock()

    mock_create_service.return_value = ingestion_service
    mock_sync_feeds.return_value = 25

    ingestion_service.ingest.return_value = {
        "feeds_processed": 25,
        "rss_entries": 100,
        "articles_discovered": 80,
        "articles_inserted": 70,
        "articles_updated": 10,
        "articles_failed": 0,
        "messages_published": 70,
    }

    main()

    mock_initialize_database.assert_called_once()
    mock_sync_feeds.assert_called_once()
    ingestion_service.ingest.assert_called_once()