import time
from typing import Any

import requests

from app.config.settings import settings


class FeedFetcher:
    """
    Fetches RSS feeds from Google News.

    Responsibility:
    - Build Google News RSS URLs
    - Make HTTP requests
    - Apply timeout and request delay
    - Return raw RSS response content

    This class does not parse RSS or process articles.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "application/rss+xml, application/xml;q=0.9, "
            "text/xml;q=0.8, */*;q=0.7"
        ),
    }

    def __init__(
        self,
        timeout: int | None = None,
        delay_seconds: float | None = None,
        session: requests.Session | None = None,
    ):
        self.timeout = (
            timeout
            if timeout is not None
            else settings.REQUEST_TIMEOUT
        )

        self.delay_seconds = (
            delay_seconds
            if delay_seconds is not None
            else settings.REQUEST_DELAY_SECONDS
        )

        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)

    def build_feed_url(self, feed: dict[str, Any]) -> str:
        """
        Build a Google News RSS search URL from a feed configuration.
        """

        query = feed["query"]

        params = {
            "q": query,
            "hl": settings.GOOGLE_NEWS_LANGUAGE,
            "gl": settings.GOOGLE_NEWS_COUNTRY,
            "ceid": settings.GOOGLE_NEWS_CEID,
        }

        response = requests.Request(
            "GET",
            settings.GOOGLE_NEWS_BASE_URL,
            params=params,
        ).prepare()

        return response.url

    def fetch(self, feed: dict[str, Any]) -> bytes:
        """
        Fetch raw RSS content for a configured feed.

        Raises:
            requests.HTTPError:
                If Google News returns a non-success HTTP status.
            requests.RequestException:
                For network-related failures.
        """

        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        url = self.build_feed_url(feed)

        response = self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response.content