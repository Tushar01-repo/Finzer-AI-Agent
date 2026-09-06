from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)


class GoogleSearchNewsProvider:
    """
    Discovers news articles using Google Search News.

    Google Search News endpoint:
        https://www.google.com/search?q=<query>&tbm=nws

    This provider is responsible only for article discovery.
    Article content extraction is handled separately by
    ArticleContentExtractor.
    """

    BASE_URL = "https://www.google.com/search"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
    }

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        timeout: int | None = None,
        delay_seconds: float | None = None,
        max_retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
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

        self.max_retries = max_retries

        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)

    def build_search_url(self, feed: dict[str, Any]) -> str:
        """
        Build Google Search News URL from a feed configuration.
        """

        query = feed["query"]

        response = requests.Request(
            "GET",
            self.BASE_URL,
            params={
                "q": query,
                "tbm": "nws",
                "hl": settings.GOOGLE_NEWS_LANGUAGE,
                "gl": settings.GOOGLE_NEWS_COUNTRY,
            },
        ).prepare()

        return response.url

    def search(self, feed: dict[str, Any]) -> str:
        """
        Fetch Google Search News HTML for the supplied feed.

        Returns:
            Raw HTML response body.

        Raises:
            requests.HTTPError:
                When Google Search cannot be reached successfully
                after retry attempts.
        """

        url = self.build_search_url(feed)

        logger.info(
            "Searching Google News: feed_id=%s query=%s",
            feed["feed_id"],
            feed["query"],
        )

        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                logger.info(
                    "Google Search response: feed_id=%s status=%s attempt=%s",
                    feed["feed_id"],
                    response.status_code,
                    attempt,
                )

                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    if attempt == self.max_retries:
                        response.raise_for_status()

                    backoff_seconds = 2 ** attempt

                    logger.warning(
                        "Retryable Google response: "
                        "feed_id=%s status=%s retry_in=%ss",
                        feed["feed_id"],
                        response.status_code,
                        backoff_seconds,
                    )

                    time.sleep(backoff_seconds)
                    continue

                response.raise_for_status()

                return response.text

            except requests.RequestException:
                if attempt == self.max_retries:
                    logger.exception(
                        "Google Search failed after retries: feed_id=%s",
                        feed["feed_id"],
                    )
                    raise

                backoff_seconds = 2 ** attempt

                logger.warning(
                    "Google Search request failed: "
                    "feed_id=%s retry_in=%ss",
                    feed["feed_id"],
                    backoff_seconds,
                )

                time.sleep(backoff_seconds)

        raise RuntimeError(
            f"Google Search failed unexpectedly for feed "
            f"{feed['feed_id']}"
        )