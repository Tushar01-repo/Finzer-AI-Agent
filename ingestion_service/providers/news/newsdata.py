from datetime import datetime
from typing import Any

import requests

from app.config.settings import settings
from app.models.discovered_article import DiscoveredArticle
from app.providers.news.base import NewsDiscoveryProvider


class NewsDataProvider(NewsDiscoveryProvider):
    """
    News discovery provider implementation using NewsData.io.

    This class is responsible for all NewsData-specific logic,
    including:

    - API authentication
    - API request construction
    - Pagination
    - Response validation
    - NewsData response parsing

    The rest of the application only sees DiscoveredArticle.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_pages: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.NEWSDATA_API_KEY

        self.base_url = (
            base_url
            or settings.NEWSDATA_BASE_URL
        )

        self.timeout = (
            timeout
            if timeout is not None
            else settings.REQUEST_TIMEOUT
        )

        self.max_pages = (
            max_pages
            if max_pages is not None
            else settings.MAX_PAGES_PER_FEED
        )

        if not self.api_key:
            raise ValueError(
                "NEWSDATA_API_KEY is not configured"
            )

        if self.max_pages <= 0:
            raise ValueError(
                "MAX_PAGES_PER_FEED must be greater than 0"
            )

    @property
    def name(self) -> str:
        """
        Return the provider's unique name.
        """

        return "newsdata"

    def discover(
        self,
        query: str,
        max_articles: int,
    ) -> list[DiscoveredArticle]:
        """
        Discover news articles from NewsData.io.

        The provider automatically follows NewsData's nextPage
        pagination token until:

        - max_articles is reached
        - no next page exists
        - max_pages is reached
        """

        if not query or not query.strip():
            return []

        if max_articles <= 0:
            return []

        articles: list[DiscoveredArticle] = []

        next_page: str | None = None

        for _ in range(self.max_pages):
            remaining = max_articles - len(articles)

            if remaining <= 0:
                break

            response = self._fetch_page(
                query=query.strip(),
                page=next_page,
            )

            raw_articles = response.get(
                "results",
                [],
            )

            if not isinstance(raw_articles, list):
                break

            for raw_article in raw_articles:
                if not isinstance(raw_article, dict):
                    continue

                article = self._parse_article(
                    raw_article
                )

                if article is None:
                    continue

                articles.append(article)

                if len(articles) >= max_articles:
                    break

            next_page = response.get("nextPage")

            if not next_page:
                break

        return articles[:max_articles]

    def _fetch_page(
        self,
        query: str,
        page: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch one page from NewsData.io.
        """

        params: dict[str, str] = {
            "apikey": self.api_key,
            "q": query,
        }

        if page:
            params["page"] = page

        response = requests.get(
            self.base_url,
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise RuntimeError(
                "Invalid response received from NewsData API"
            )

        if data.get("status") != "success":
            message = self._extract_error_message(data)

            raise RuntimeError(
                f"NewsData API request failed: {message}"
            )

        return data

    @staticmethod
    def _extract_error_message(
        data: dict[str, Any],
    ) -> str:
        """
        Extract a useful error message from a NewsData
        error response.
        """

        results = data.get("results")

        if isinstance(results, dict):
            message = results.get("message")

            if message:
                return str(message)

        return "Unknown NewsData API error"

    def _parse_article(
        self,
        raw_article: dict[str, Any],
    ) -> DiscoveredArticle | None:
        """
        Convert a NewsData article into our canonical
        DiscoveredArticle model.
        """

        title = self._clean_string(
            raw_article.get("title")
        )

        url = self._clean_string(
            raw_article.get("link")
        )

        # An article without a title or URL is not useful
        # to the ingestion pipeline.
        if not title or not url:
            return None

        source = self._extract_source(
            raw_article
        )

        description = self._clean_string(
            raw_article.get("description")
        )

        published_at = self._parse_datetime(
            raw_article.get("pubDate")
        )

        authors = self._extract_authors(
            raw_article.get("creator")
        )

        image_url = self._clean_string(
            raw_article.get("image_url")
        )

        return DiscoveredArticle(
            title=title,
            url=url,
            source=source,
            description=description,
            published_at=published_at,
            authors=authors,
            image_url=image_url,
        )

    @staticmethod
    def _extract_source(
        raw_article: dict[str, Any],
    ) -> str | None:
        """
        Extract the source name from NewsData.
        """

        source_name = raw_article.get(
            "source_name"
        )

        if isinstance(source_name, str):
            source_name = source_name.strip()

            if source_name:
                return source_name

        return None

    @staticmethod
    def _extract_authors(
        creator: Any,
    ) -> list[str] | None:
        """
        Normalize NewsData's creator field into a list
        of author names.
        """

        if not creator:
            return None

        if isinstance(creator, str):
            creator = [creator]

        if not isinstance(creator, list):
            return None

        authors: list[str] = []

        for author in creator:
            if author is None:
                continue

            author = str(author).strip()

            if author:
                authors.append(author)

        return authors or None

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        """
        Parse NewsData's publication timestamp.
        """

        if not value:
            return None

        if isinstance(value, datetime):
            return value

        if not isinstance(value, str):
            return None

        value = value.strip()

        if not value:
            return None

        try:
            return datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            return None

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> str | None:
        """
        Convert a value to a cleaned string.
        """

        if value is None:
            return None

        value = str(value).strip()

        return value or None