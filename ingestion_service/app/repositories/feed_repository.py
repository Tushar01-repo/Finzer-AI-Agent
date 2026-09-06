from typing import Any

from app.models.database_schema import FeedRecord
from app.repositories.database import PostgresDatabase


class FeedRepository:
    """
    Repository for the feeds table.

    Responsibilities:
    - Persist feed configuration
    - Retrieve feed configuration
    - Keep SQL operations isolated from business logic
    """

    def __init__(self, database: PostgresDatabase):
        self.database = database

    def upsert(self, feed: FeedRecord) -> None:
        """
        Insert a feed or update it if the feed_id already exists.
        """
        query = """
            INSERT INTO feeds (
                feed_id,
                feed_type,
                feed_value,
                query,
                enabled
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (feed_id)
            DO UPDATE SET
                feed_type = EXCLUDED.feed_type,
                feed_value = EXCLUDED.feed_value,
                query = EXCLUDED.query,
                enabled = EXCLUDED.enabled
        """

        params = (
            feed.feed_id,
            feed.feed_type,
            feed.feed_value,
            feed.query,
            feed.enabled,
        )

        self.database.execute(query, params)

    def get_by_id(self, feed_id: str) -> FeedRecord | None:
        """
        Retrieve a feed by feed_id.
        """
        query = """
            SELECT
                feed_id,
                feed_type,
                feed_value,
                query,
                enabled,
                created_at
            FROM feeds
            WHERE feed_id = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (feed_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._to_record(row)

    def get_all(self) -> list[FeedRecord]:
        """
        Retrieve all feeds.
        """
        query = """
            SELECT
                feed_id,
                feed_type,
                feed_value,
                query,
                enabled,
                created_at
            FROM feeds
            ORDER BY feed_id
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

        return [self._to_record(row) for row in rows]

    def get_enabled(self) -> list[FeedRecord]:
        """
        Retrieve only enabled feeds.
        """
        query = """
            SELECT
                feed_id,
                feed_type,
                feed_value,
                query,
                enabled,
                created_at
            FROM feeds
            WHERE enabled = TRUE
            ORDER BY feed_id
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

        return [self._to_record(row) for row in rows]

    @staticmethod
    def _to_record(row: tuple[Any, ...]) -> FeedRecord:
        """
        Convert a database row into a FeedRecord.
        """
        return FeedRecord(
            feed_id=row[0],
            feed_type=row[1],
            feed_value=row[2],
            query=row[3],
            enabled=row[4],
            created_at=row[5],
        )