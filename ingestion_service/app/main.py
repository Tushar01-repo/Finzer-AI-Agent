import argparse
import logging
from pathlib import Path

from app.config.feed_registry import FeedRegistry
from app.config.settings import settings

from app.queue.queue_publisher import QueuePublisher

from app.repositories.article_feed_repository import ArticleFeedRepository
from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase
from app.repositories.feed_repository import FeedRepository

from app.services.article_content_extractor import ArticleContentExtractor
from app.services.article_normalizer import ArticleNormalizer
from app.services.feed_fetcher import FeedFetcher
from app.services.feed_sync_service import FeedSyncService
from app.services.google_news_url_resolver import GoogleNewsURLResolver
from app.services.ingestion_service import IngestionService
from app.services.rss_parser import RSSParser


logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Finzer article ingestion service"
    )

    parser.add_argument(
        "--feed-id",
        type=str,
        default=None,
        help="Process only the specified feed, e.g. company_tcs",
    )

    return parser.parse_args()


def create_ingestion_service() -> IngestionService:
    database = PostgresDatabase()

    feed_registry = FeedRegistry(
        Path(__file__).resolve().parent / "config" / "feeds.yaml"
    )

    feed_fetcher = FeedFetcher()
    rss_parser = RSSParser()
    url_resolver = GoogleNewsURLResolver()
    content_extractor = ArticleContentExtractor()
    normalizer = ArticleNormalizer()

    feed_repository = FeedRepository(database)
    article_repository = ArticleRepository(database)
    article_feed_repository = ArticleFeedRepository(database)

    queue_publisher = QueuePublisher()

    return IngestionService(
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


def initialize_database() -> None:
    database = PostgresDatabase()
    database.initialize_schema()


def sync_feeds() -> int:
    database = PostgresDatabase()

    feed_registry = FeedRegistry(
        Path(__file__).resolve().parent / "config" / "feeds.yaml"
    )

    feed_repository = FeedRepository(database)

    feed_sync_service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    return feed_sync_service.sync()


def main(feed_id: str | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print(f"Starting {settings.APP_NAME}...")

    if feed_id:
        logger.info("Requested feed: %s", feed_id)

    print("\nInitializing database...")
    initialize_database()
    print("Database initialized successfully.")

    print("\nSynchronizing feed configuration...")
    synchronized_feeds = sync_feeds()
    print(f"{synchronized_feeds} feeds synchronized.")

    print("\nStarting article ingestion...")

    ingestion_service = create_ingestion_service()

    if feed_id:
        stats = ingestion_service.ingest(feed_id=feed_id)
    else:
        stats = ingestion_service.ingest()

    print("\nIngestion completed.")
    print(f"Feeds processed:       {stats['feeds_processed']}")
    print(f"RSS entries:           {stats['rss_entries']}")
    print(f"Articles discovered:   {stats['articles_discovered']}")
    print(f"Articles inserted:     {stats['articles_inserted']}")
    print(f"Articles updated:      {stats['articles_updated']}")
    print(f"Articles failed:       {stats['articles_failed']}")
    print(f"Messages published:    {stats['messages_published']}")


if __name__ == "__main__":
    args = parse_args()
    main(feed_id=args.feed_id)