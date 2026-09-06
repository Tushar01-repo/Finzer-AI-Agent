from typing import Any

import feedparser


class RSSParser:
    """
    Parses raw RSS content into structured article metadata.

    Responsibility:
    - Parse RSS bytes/content
    - Extract RSS-level article metadata
    - Normalize missing fields

    This class does not:
    - Resolve Google News URLs
    - Fetch article pages
    - Extract article content
    - Store anything in the database
    """

    def parse(
        self,
        content: bytes,
        feed: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Parse raw RSS content.

        Args:
            content: Raw RSS response content.
            feed: Feed configuration.

        Returns:
            A list of structured RSS article records.
        """

        parsed_feed = feedparser.parse(content)

        articles = []

        for entry in parsed_feed.entries:
            article = {
                "feed_id": feed["feed_id"],
                "rss_title": self._get_value(
                    entry,
                    "title",
                ),
                "rss_published": self._get_value(
                    entry,
                    "published",
                ),
                "rss_source": self._extract_source(entry),
                "google_news_link": self._get_value(
                    entry,
                    "link",
                ),
            }

            articles.append(article)

        return articles

    @staticmethod
    def _get_value(
        entry: Any,
        field: str,
    ) -> str | None:
        """
        Safely retrieve a value from an RSS entry.
        """

        value = entry.get(field)

        if value is None:
            return None

        value = str(value).strip()

        return value or None

    @staticmethod
    def _extract_source(
        entry: Any,
    ) -> str | None:
        """
        Extract the publisher/source name from an RSS entry.
        """

        source = entry.get("source")

        if source is None:
            return None

        if isinstance(source, dict):
            value = source.get("title")
        else:
            value = getattr(
                source,
                "title",
                None,
            )

        if value is None:
            return None

        value = str(value).strip()

        return value or None