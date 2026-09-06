from typing import Any

from app.models.database_schema import (
    ArticleFeedRecord,
    ArticleRecord,
)
from app.repositories.article_feed_repository import (
    ArticleFeedRepository,
)
from app.repositories.article_repository import (
    ArticleRepository,
)
from app.services.article_content_extractor import (
    ArticleContentExtractor,
)
from app.services.article_normalizer import ArticleNormalizer
from app.services.feed_fetcher import FeedFetcher
from app.services.google_news_url_resolver import (
    GoogleNewsURLResolver,
)
from app.services.rss_parser import RSSParser
from app.config.feed_registry import FeedRegistry
from app.queue.queue_publisher import QueuePublisher


class IngestionService:
    """
    Orchestrates the synchronous article ingestion pipeline.

    Responsibilities:
    - Process enabled feeds
    - Fetch and parse RSS feeds
    - Resolve Google News URLs
    - Extract article content
    - Normalize article data
    - Deduplicate articles
    - Persist articles and feed relationships
    - Publish newly discovered articles for asynchronous processing

    This service does not perform:
    - LLM processing
    - Embedding generation
    - Vector storage
    """

    def __init__(
        self,
        feed_registry: FeedRegistry,
        feed_fetcher: FeedFetcher,
        rss_parser: RSSParser,
        url_resolver: GoogleNewsURLResolver,
        content_extractor: ArticleContentExtractor,
        normalizer: ArticleNormalizer,
        article_repository: ArticleRepository,
        article_feed_repository: ArticleFeedRepository,
        queue_publisher: QueuePublisher,
    ):
        self.feed_registry = feed_registry
        self.feed_fetcher = feed_fetcher
        self.rss_parser = rss_parser
        self.url_resolver = url_resolver
        self.content_extractor = content_extractor
        self.normalizer = normalizer
        self.article_repository = article_repository
        self.article_feed_repository = article_feed_repository
        self.queue_publisher = queue_publisher

    def ingest(
        self,
        feed_id: str | None = None,
    ) -> dict[str, int]:
        """
        Process enabled feeds or a specific feed.

        Args:
            feed_id:
                Optional feed ID. If provided, only that feed
                is processed.

        Returns:
            Statistics describing the ingestion run.
        """

        stats = {
            "feeds_processed": 0,
            "rss_entries": 0,
            "articles_discovered": 0,
            "articles_inserted": 0,
            "articles_updated": 0,
            "articles_failed": 0,
            "messages_published": 0,
        }

        feeds = (
            [self.feed_registry.get(feed_id)]
            if feed_id
            else self.feed_registry.enabled()
        )

        for feed in feeds:
            stats["feeds_processed"] += 1

            try:
                feed_stats = self._process_feed(feed)

                for key, value in feed_stats.items():
                    stats[key] += value

            except Exception:
                # One feed failure must not stop the remaining feeds.
                continue

        return stats

    def _process_feed(
        self,
        feed: dict[str, Any],
    ) -> dict[str, int]:
        """
        Process a single configured feed.
        """

        stats = {
            "rss_entries": 0,
            "articles_discovered": 0,
            "articles_inserted": 0,
            "articles_updated": 0,
            "articles_failed": 0,
            "messages_published": 0,
        }

        rss_content = self.feed_fetcher.fetch(feed)

        entries = self.rss_parser.parse(
            rss_content,
            feed,
        )

        stats["rss_entries"] = len(entries)

        for entry in entries:
            try:
                result = self._process_entry(
                    entry,
                    feed,
                )

                stats["articles_discovered"] += 1

                if result["is_new"]:
                    stats["articles_inserted"] += 1
                    stats["messages_published"] += 1
                else:
                    stats["articles_updated"] += 1

            except Exception:
                stats["articles_failed"] += 1

        return stats

    def _process_entry(
        self,
        entry: dict[str, Any],
        feed: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Process one RSS entry from discovery to persistence.
        """

        google_news_url = entry["google_news_link"]

        if not google_news_url:
            raise ValueError(
                "RSS entry does not contain a Google News URL."
            )

        article_url = self.url_resolver.resolve(
            google_news_url
        )

        extraction = self.content_extractor.extract(
            article_url
        )

        if extraction.get("status") != "success":
            raise ValueError(
                extraction.get(
                    "error",
                    "Article extraction failed.",
                )
            )

        normalized = self.normalizer.normalize(
            {
                "title": extraction.get("title")
                or entry.get("rss_title"),
                "url": article_url,
                "source": extraction.get("source")
                or entry.get("rss_source"),
                "authors": extraction.get("authors", []),
                "published_at": extraction.get("published_at")
                or entry.get("rss_published"),
                "content": extraction.get("content"),
            }
        )

        article_key = normalized["article_key"]

        existing_article = self.article_repository.get_by_key(
            article_key
        )

        article = ArticleRecord(
            article_key=article_key,
            title=normalized["title"],
            url=normalized["url"],
            source=normalized["source"],
            authors=normalized["authors"],
            published_at=normalized["published_at"],
            content=normalized["content"],
            content_hash=normalized["content_hash"],
            summary=(
                existing_article.summary
                if existing_article
                else None
            ),
            processing_status=(
                existing_article.processing_status
                if existing_article
                else "pending"
            ),
            created_at=(
                existing_article.created_at
                if existing_article
                else None
            ),
            updated_at=(
                existing_article.updated_at
                if existing_article
                else None
            ),
        )

        self.article_repository.upsert(article)

        self.article_feed_repository.add(
            ArticleFeedRecord(
                article_key=article_key,
                feed_id=feed["feed_id"],
            )
        )

        is_new = existing_article is None

        if is_new:
            self.queue_publisher.publish(
                {
                    "article_key": article_key,
                }
            )

        return {
            "is_new": is_new,
        }