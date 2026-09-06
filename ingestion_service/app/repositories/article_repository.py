from typing import Any

from app.models.database_schema import ArticleRecord
from app.repositories.database import PostgresDatabase


class ArticleRepository:
    """
    Repository for the articles table.

    Responsibilities:
    - Insert new articles
    - Update existing articles
    - Retrieve articles
    - Maintain processing status
    """

    def __init__(self, database: PostgresDatabase):
        self.database = database

    def upsert(self, article: ArticleRecord) -> None:
        """
        Insert an article or update the existing article
        identified by article_key.
        """

        query = """
            INSERT INTO articles (
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (article_key)
            DO UPDATE SET
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                source = EXCLUDED.source,
                authors = EXCLUDED.authors,
                published_at = EXCLUDED.published_at,
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                updated_at = NOW()
        """

        params = (
            article.article_key,
            article.title,
            article.url,
            article.source,
            article.authors,
            article.published_at,
            article.content,
            article.content_hash,
            article.summary,
            article.processing_status,
        )

        self.database.execute(query, params)

    def get_by_key(
        self,
        article_key: str,
    ) -> ArticleRecord | None:
        """
        Retrieve an article using its deterministic article_key.
        """

        query = """
            SELECT
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status,
                created_at,
                updated_at
            FROM articles
            WHERE article_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (article_key,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._to_record(row)

    def update_summary(
        self,
        article_key: str,
        summary: str,
    ) -> None:
        """
        Update the generated article summary.
        """

        query = """
            UPDATE articles
            SET
                summary = %s,
                processing_status = 'summarized',
                updated_at = NOW()
            WHERE article_key = %s
        """

        self.database.execute(
            query,
            (summary, article_key),
        )

    def update_processing_status(
        self,
        article_key: str,
        status: str,
    ) -> None:
        """
        Update article processing status.
        """

        query = """
            UPDATE articles
            SET
                processing_status = %s,
                updated_at = NOW()
            WHERE article_key = %s
        """

        self.database.execute(
            query,
            (status, article_key),
        )

    def get_pending_articles(
        self,
        limit: int = 100,
    ) -> list[ArticleRecord]:
        """
        Retrieve articles waiting for asynchronous processing.
        """

        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        query = """
            SELECT
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status,
                created_at,
                updated_at
            FROM articles
            WHERE processing_status = 'pending'
            ORDER BY created_at
            LIMIT %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()

        return [self._to_record(row) for row in rows]

    @staticmethod
    def _to_record(row: tuple[Any, ...]) -> ArticleRecord:
        """
        Convert a database row into an ArticleRecord.
        """

        return ArticleRecord(
            article_key=row[0],
            title=row[1],
            url=row[2],
            source=row[3],
            authors=row[4],
            published_at=row[5],
            content=row[6],
            content_hash=row[7],
            summary=row[8],
            processing_status=row[9],
            created_at=row[10],
            updated_at=row[11],
        )