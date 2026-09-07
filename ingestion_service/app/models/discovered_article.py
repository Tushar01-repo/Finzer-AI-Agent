from dataclasses import dataclass
from datetime import datetime


@dataclass
class DiscoveredArticle:
    """
    Provider-independent representation of a discovered news article.

    Provider-specific response formats must be converted into this
    model before being passed to the rest of the ingestion pipeline.
    """

    title: str
    url: str
    source: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    authors: list[str] | None = None
    image_url: str | None = None