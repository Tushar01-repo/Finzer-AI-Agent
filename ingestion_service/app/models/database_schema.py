from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FeedRecord:
    """
    Represents a feed configuration stored in PostgreSQL.
    """

    feed_id: str
    feed_type: str
    feed_value: str
    query: str
    enabled: bool
    created_at: datetime | None = None


@dataclass(frozen=True)
class ArticleRecord:
    """
    Represents a normalized article stored in PostgreSQL.
    """

    article_key: str
    title: str | None
    url: str
    source: str | None
    authors: list[str]
    published_at: datetime | None
    content: str | None
    content_hash: str | None
    summary: str | None = None
    processing_status: str = "pending"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ArticleFeedRecord:
    """
    Represents the relationship between an article and a feed.
    """

    article_key: str
    feed_id: str
    first_seen_at: datetime | None = None