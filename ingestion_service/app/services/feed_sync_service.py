from app.config.feed_registry import FeedRegistry
from app.models.database_schema import FeedRecord
from app.repositories.feed_repository import FeedRepository


class FeedSyncService:
    """
    Synchronizes feed configuration from feeds.yaml
    into the PostgreSQL feeds table.
    """

    def __init__(
        self,
        feed_registry: FeedRegistry,
        feed_repository: FeedRepository,
    ):
        self.feed_registry = feed_registry
        self.feed_repository = feed_repository

    def sync(self) -> int:
        """
        Synchronize all configured feeds into PostgreSQL.

        Returns:
            Number of feeds synchronized.
        """

        feeds = self.feed_registry.all()

        for feed in feeds:
            record = FeedRecord(
                feed_id=feed["feed_id"],
                feed_type=feed["feed_type"],
                feed_value=feed["feed_value"],
                query=feed["query"],
                enabled=feed["enabled"],
            )

            self.feed_repository.upsert(record)

        return len(feeds)