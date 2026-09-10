import logging

from typing import Any

from app.config.feed_registry import FeedRegistry
from app.models.database_schema import (
    ArticleFeedRecord,
    ArticleRecord,
)
from app.queue.queue_publisher import QueuePublisher
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
from app.services.news_discovery_service import (
    NewsDiscoveryService,
)


logger = logging.getLogger(__name__)


class ArticleExtractionError(Exception):
    """
    Raised when article content extraction fails.

    Keeps the structured extraction result so the ingestion
    service can classify and report failures accurately.
    """

    def __init__(
        self,
        extraction: dict[str, Any],
    ):
        self.extraction = extraction

        error_message = extraction.get(
            "error",
            "Article extraction failed.",
        )

        super().__init__(error_message)


class IngestionService:
    """
    Orchestrates the synchronous article ingestion pipeline.

    Responsibilities:
    - Process enabled feeds
    - Discover articles through a news provider
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

    FAILURE_STAT_KEYS = {
        "blocked": "articles_blocked",
        "timeout": "articles_timed_out",
        "not_found": "articles_not_found",
        "server_error": "articles_server_error",
        "security_challenge": "articles_security_challenge",
        "insufficient_content": "articles_insufficient_content",
        "connection_error": "articles_connection_error",
        "request_error": "articles_request_error",
        "http_error": "articles_http_error",
        "extraction_error": "articles_extraction_error",
    }

    def __init__(
        self,
        feed_registry: FeedRegistry,
        news_discovery_service: NewsDiscoveryService,
        content_extractor: ArticleContentExtractor,
        normalizer: ArticleNormalizer,
        article_repository: ArticleRepository,
        article_feed_repository: ArticleFeedRepository,
        queue_publisher: QueuePublisher,
    ):
        self.feed_registry = feed_registry
        self.news_discovery_service = news_discovery_service
        self.content_extractor = content_extractor
        self.normalizer = normalizer
        self.article_repository = article_repository
        self.article_feed_repository = article_feed_repository
        self.queue_publisher = queue_publisher

    @staticmethod
    def _empty_stats(
        include_feeds: bool = False,
    ) -> dict[str, int]:
        """
        Create a fresh statistics dictionary.
        """

        stats = {
            "articles_discovered": 0,
            "articles_inserted": 0,
            "articles_updated": 0,
            "articles_failed": 0,
            "messages_published": 0,

            # Extraction failure categories
            "articles_blocked": 0,
            "articles_timed_out": 0,
            "articles_not_found": 0,
            "articles_server_error": 0,
            "articles_security_challenge": 0,
            "articles_insufficient_content": 0,
            "articles_connection_error": 0,
            "articles_request_error": 0,
            "articles_http_error": 0,
            "articles_extraction_error": 0,

            # Failures not caused by extraction.
            "articles_other_failure": 0,
        }

        if include_feeds:
            stats = {
                "feeds_processed": 0,
                **stats,
            }

        return stats

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

        stats = self._empty_stats(
            include_feeds=True,
        )

        feeds = (
            [self.feed_registry.get(feed_id)]
            if feed_id
            else self.feed_registry.enabled()
        )

        logger.info(
            "Starting the ingestion, feed_id=%s, feeds=%d",
            feed_id,
            len(feeds),
        )

        for feed in feeds:
            current_feed_id = feed.get(
                "feed_id",
                feed_id,
            )

            stats["feeds_processed"] += 1

            logger.info(
                "Processing feed: feed_id=%s",
                current_feed_id,
            )

            try:
                feed_stats = self._process_feed(
                    feed
                )

                for key, value in feed_stats.items():
                    stats[key] += value

                logger.info(
                    "Finished feed: feed_id=%s, stats=%s",
                    current_feed_id,
                    feed_stats,
                )

            except Exception:
                # One feed failure must not stop the remaining feeds.
                logger.exception(
                    "Failed to process feed: feed_id=%s",
                    current_feed_id,
                )

        return stats

    def _process_feed(
        self,
        feed: dict[str, Any],
    ) -> dict[str, int]:
        """
        Process a single configured feed.

        Discovery is provider-agnostic. The ingestion service
        only works with the canonical DiscoveredArticle model
        returned by NewsDiscoveryService.
        """

        stats = self._empty_stats()

        query = feed.get("query")

        if isinstance(query, list):
            query = " OR ".join(
                str(item).strip()
                for item in query
                if str(item).strip()
            )

        if not query:
            logger.warning(
                "Skipping feed without query: feed_id=%s",
                feed.get("feed_id"),
            )

            return stats

        max_articles = feed.get(
            "max_articles",
        )

        if max_articles is None:
            from app.config.settings import settings

            max_articles = settings.MAX_ARTICLES_PER_FEED

        logger.info(
            "Discovering articles: feed_id=%s, query=%r, max_articles=%d",
            feed.get("feed_id"),
            query,
            max_articles,
        )

        articles = self.news_discovery_service.discover(
            query=query,
            max_articles=max_articles,
        )

        # Every article returned by the discovery provider is
        # considered discovered, regardless of what happens later.
        stats["articles_discovered"] = len(
            articles
        )

        logger.info(
            "Articles discovered: feed_id=%s, count=%d",
            feed.get("feed_id"),
            len(articles),
        )

        for index, article in enumerate(
            articles,
            start=1,
        ):
            logger.info(
                "Processing article %d/%d: feed_id=%s, title=%r, url=%s",
                index,
                len(articles),
                feed.get("feed_id"),
                article.title,
                article.url,
            )

            try:
                result = self._process_article(
                    article,
                    feed,
                )

                if result["is_new"]:
                    stats["articles_inserted"] += 1
                    stats["messages_published"] += 1

                    logger.info(
                        "Inserted new article: feed_id=%s, title=%r",
                        feed.get("feed_id"),
                        article.title,
                    )

                else:
                    stats["articles_updated"] += 1

                    logger.info(
                        "Updated existing article: feed_id=%s, title=%r",
                        feed.get("feed_id"),
                        article.title,
                    )

            except ArticleExtractionError as exc:
                stats["articles_failed"] += 1

                extraction = exc.extraction

                error_type = extraction.get(
                    "error_type"
                ) or "extraction_error"

                stat_key = self.FAILURE_STAT_KEYS.get(
                    error_type,
                    "articles_extraction_error",
                )

                stats[stat_key] += 1

                logger.error(
                    (
                        "Article extraction failed: "
                        "feed_id=%s, "
                        "title=%r, "
                        "url=%s, "
                        "error_type=%s, "
                        "status_code=%s, "
                        "method=%s, "
                        "error=%s"
                    ),
                    feed.get("feed_id"),
                    article.title,
                    article.url,
                    error_type,
                    extraction.get(
                        "status_code"
                    ),
                    extraction.get(
                        "method"
                    ),
                    extraction.get(
                        "error"
                    ),
                )

            except Exception:
                stats["articles_failed"] += 1
                stats["articles_other_failure"] += 1

                logger.exception(
                    "Failed to process article: feed_id=%s, title=%r, url=%s",
                    feed.get("feed_id"),
                    article.title,
                    article.url,
                )

        return stats

    def _process_article(
        self,
        article: Any,
        feed: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Process one discovered article from extraction
        to persistence.
        """

        extraction = self.content_extractor.extract(
            article.url
        )

        if extraction.get("status") != "success":
            raise ArticleExtractionError(
                extraction
            )

        normalized = self.normalizer.normalize(
            {
                "title": (
                    extraction.get("title")
                    or article.title
                ),
                "url": article.url,
                "source": (
                    extraction.get("source")
                    or article.source
                ),
                "authors": (
                    extraction.get("authors")
                    or article.authors
                    or []
                ),
                "published_at": (
                    extraction.get("published_at")
                    or article.published_at
                ),
                "content": extraction.get(
                    "content"
                ),
            }
        )

        article_key = normalized[
            "article_key"
        ]

        existing_article = (
            self.article_repository.get_by_key(
                article_key
            )
        )

        article_record = ArticleRecord(
            article_key=article_key,
            title=normalized["title"],
            url=normalized["url"],
            source=normalized["source"],
            authors=normalized["authors"],
            published_at=normalized[
                "published_at"
            ],
            content=normalized["content"],
            content_hash=normalized[
                "content_hash"
            ],
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

        self.article_repository.upsert(
            article_record
        )

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