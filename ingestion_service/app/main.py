import argparse
import logging
from pathlib import Path

from app.config.feed_registry import FeedRegistry
from app.config.settings import settings

from app.providers.news.newsdata import NewsDataProvider

from app.queue.queue_publisher import QueuePublisher

from app.repositories.article_feed_repository import ArticleFeedRepository
from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase
from app.repositories.feed_repository import FeedRepository

from app.services.article_content_extractor import ArticleContentExtractor
from app.services.article_normalizer import ArticleNormalizer
from app.services.feed_sync_service import FeedSyncService
from app.services.ingestion_service import IngestionService
from app.services.news_discovery_service import NewsDiscoveryService


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
        Path(__file__).resolve().parent
        / "config"
        / "feeds.yaml"
    )

    # ------------------------------------------------------------------
    # News discovery
    # ------------------------------------------------------------------

    news_provider = NewsDataProvider()

    news_discovery_service = NewsDiscoveryService(
        provider=news_provider,
    )

    # ------------------------------------------------------------------
    # Article processing
    # ------------------------------------------------------------------

    content_extractor = ArticleContentExtractor()
    normalizer = ArticleNormalizer()

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------

    article_repository = ArticleRepository(
        database
    )

    article_feed_repository = ArticleFeedRepository(
        database
    )

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    queue_publisher = QueuePublisher()

    return IngestionService(
        feed_registry=feed_registry,
        news_discovery_service=news_discovery_service,
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
        Path(__file__).resolve().parent
        / "config"
        / "feeds.yaml"
    )

    feed_repository = FeedRepository(
        database
    )

    feed_sync_service = FeedSyncService(
        feed_registry=feed_registry,
        feed_repository=feed_repository,
    )

    return feed_sync_service.sync()


def main(
    feed_id: str | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print(
        f"Starting {settings.APP_NAME}..."
    )

    if feed_id:
        logger.info(
            "Requested feed: %s",
            feed_id,
        )

    print("\nInitializing database...")
    initialize_database()
    print(
        "Database initialized successfully."
    )

    print(
        "\nSynchronizing feed configuration..."
    )

    synchronized_feeds = sync_feeds()

    print(
        f"{synchronized_feeds} feeds synchronized."
    )

    print(
        "\nStarting article ingestion..."
    )

    ingestion_service = (
        create_ingestion_service()
    )

    if feed_id:
        stats = ingestion_service.ingest(
            feed_id=feed_id
        )
    else:
        stats = ingestion_service.ingest()

    print(
        "\nIngestion completed."
    )

    print(
        f"Feeds processed:       "
        f"{stats['feeds_processed']}"
    )

    print(
        f"Articles discovered:   "
        f"{stats['articles_discovered']}"
    )

    print(
        f"Articles inserted:     "
        f"{stats['articles_inserted']}"
    )

    print(
        f"Articles updated:      "
        f"{stats['articles_updated']}"
    )

    print(
        f"Articles failed:       "
        f"{stats['articles_failed']}"
    )

    print(
        f"Messages published:    "
        f"{stats['messages_published']}"
    )


if __name__ == "__main__":
    args = parse_args()

    main(
        feed_id=args.feed_id
    )