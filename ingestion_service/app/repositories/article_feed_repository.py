from datetime import datetime, timezone

from app.models.database_schema import ArticleFeedRecord
from app.repositories.database import PostgresDatabase


class ArticleFeedRepository:
    """
    Repository for the article_feeds relationship table.

    Responsibilities:
    - Link articles to feeds
    - Prevent duplicate article/feed relationships
    - Retrieve feeds associated with an article
    """

    def __init__(self, database: PostgresDatabase):
        self.database = database

    def add(self, record: ArticleFeedRecord) -> None:
        """
        Create an article/feed relationship.

        If the relationship already exists, do nothing.
        """

        query = """
            INSERT INTO article_feeds (
                article_key,
                feed_id,
                first_seen_at
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (article_key, feed_id)
            DO NOTHING
        """

        first_seen_at = record.first_seen_at

        if first_seen_at is None:
            first_seen_at = datetime.now(timezone.utc)

        params = (
            record.article_key,
            record.feed_id,
            first_seen_at,
        )

        self.database.execute(query, params)

    def get_feeds_for_article(
        self,
        article_key: str,
    ) -> list[str]:
        """
        Return all feed IDs associated with an article.
        """

        query = """
            SELECT feed_id
            FROM article_feeds
            WHERE article_key = %s
            ORDER BY feed_id
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (article_key,))
                rows = cursor.fetchall()

        return [row[0] for row in rows]

    def exists(
        self,
        article_key: str,
        feed_id: str,
    ) -> bool:
        """
        Check whether an article/feed relationship exists.
        """

        query = """
            SELECT 1
            FROM article_feeds
            WHERE article_key = %s
              AND feed_id = %s
            LIMIT 1
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (article_key, feed_id),
                )
                row = cursor.fetchone()

        return row is not None