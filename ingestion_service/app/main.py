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


def print_ingestion_stats(
    stats: dict[str, int],
) -> None:
    """
    Print ingestion statistics in a readable format.
    """

    print("\nIngestion completed.")

    print(
        f"Feeds processed:              "
        f"{stats.get('feeds_processed', 0)}"
    )

    print(
        f"Articles discovered:          "
        f"{stats.get('articles_discovered', 0)}"
    )

    print(
        f"Articles inserted:            "
        f"{stats.get('articles_inserted', 0)}"
    )

    print(
        f"Articles updated:             "
        f"{stats.get('articles_updated', 0)}"
    )

    print(
        f"Articles failed:              "
        f"{stats.get('articles_failed', 0)}"
    )

    print("\nFailure breakdown:")

    # print(
    #     f"  Blocked:                    "
    #     f"{stats['articles_blocked']}"
    # )

    print(
        f"Articles blocked:             "
        f"{stats.get('articles_blocked', 0)}"
    )

    print(
        f"  Timed out:                  "
        f"{stats.get('articles_timed_out', 0)}"
    )

    print(
        f"  Not found:                  "
        f"{stats.get('articles_not_found', 0)}"
    )

    print(
        f"  Server errors:              "
        f"{stats.get('articles_server_error', 0)}"
    )

    print(
        f"  Security challenges:        "
        f"{stats.get('articles_security_challenge', 0)}"
    )

    print(
        f"  Insufficient content:       "
        f"{stats.get('articles_insufficient_content', 0)}"
    )

    print(
        f"  Connection errors:          "
        f"{stats.get('articles_connection_error', 0)}"
    )

    print(
        f"  Request errors:             "
        f"{stats.get('articles_request_error', 0)}"
    )

    print(
        f"  HTTP errors:                "
        f"{stats.get('articles_http_error', 0)}"
    )

    print(
        f"  Extraction errors:          "
        f"{stats.get('articles_extraction_error', 0)}"
    )

    print(
        f"  Other failures:             "
        f"{stats.get('articles_other_failure', 0)}"
    )

    print(
        f"\nMessages published:           "
        f"{stats.get('messages_published', 0)}"
    )


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

    print_ingestion_stats(
        stats
    )


if __name__ == "__main__":
    args = parse_args()

    main(
        feed_id=args.feed_id
    )