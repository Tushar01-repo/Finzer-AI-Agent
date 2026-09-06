import base64
import json
import re
from typing import Any

import requests


class GoogleNewsURLResolver:
    """
    Resolves Google News article wrapper URLs to the original
    publisher URL.

    This component only handles URL resolution.
    It does not fetch or extract article content.
    """

    GOOGLE_NEWS_ARTICLE_PATTERN = re.compile(
        r"/rss/(?:articles|read)/([^/?]+)"
    )

    DECODE_URL = (
        "https://news.google.com/_/DotsSplashUi/data/batchexecute"
    )

    def __init__(
        self,
        timeout: int = 15,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()

    def resolve(self, google_news_url: str) -> str:
        """
        Resolve a Google News URL to the original publisher URL.

        If resolution fails, the original URL is returned.
        """

        if not google_news_url:
            return google_news_url

        if not self.is_google_news_url(google_news_url):
            return google_news_url

        try:
            token = self._extract_token(google_news_url)

            if not token:
                return google_news_url

            params = self._get_decoding_params(
                google_news_url
            )

            if not params:
                return google_news_url

            resolved_url = self._decode_url(
                token=token,
                signature=params["signature"],
                timestamp=params["timestamp"],
            )

            return resolved_url or google_news_url

        except (requests.RequestException, ValueError, KeyError):
            return google_news_url

    @staticmethod
    def is_google_news_url(url: str) -> bool:
        """
        Check whether a URL is a Google News RSS article wrapper.
        """

        return bool(
            GoogleNewsURLResolver.GOOGLE_NEWS_ARTICLE_PATTERN.search(
                url
            )
        )

    @classmethod
    def _extract_token(cls, url: str) -> str | None:
        """
        Extract the opaque Google News article token.
        """

        match = cls.GOOGLE_NEWS_ARTICLE_PATTERN.search(url)

        if not match:
            return None

        return match.group(1)

    def _get_decoding_params(
        self,
        google_news_url: str,
    ) -> dict[str, str] | None:
        """
        Fetch the Google News article wrapper page and extract
        the signature and timestamp required for decoding.
        """

        response = self.session.get(
            google_news_url,
            timeout=self.timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        html = response.text

        signature_match = re.search(
            r'data-n-a-sg="([^"]+)"',
            html,
        )

        timestamp_match = re.search(
            r'data-n-a-ts="([^"]+)"',
            html,
        )

        if not signature_match or not timestamp_match:
            return None

        return {
            "signature": signature_match.group(1),
            "timestamp": timestamp_match.group(1),
        }

    def _decode_url(
        self,
        token: str,
        signature: str,
        timestamp: str,
    ) -> str | None:
        """
        Send the decoding request to Google News.
        """

        payload = [
            [
                "Fbv4je",
                json.dumps(
                    [
                        [
                            token,
                            signature,
                            timestamp,
                        ]
                    ]
                ),
                None,
                "generic",
            ]
        ]

        response = self.session.post(
            self.DECODE_URL,
            data={
                "f.req": json.dumps(payload),
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        return self._extract_decoded_url(response.text)

    @staticmethod
    def _extract_decoded_url(
        response_text: str,
    ) -> str | None:
        """
        Extract the publisher URL from Google's batchexecute response.
        """

        # Google wraps the response in an anti-XSSI prefix.
        cleaned = response_text.lstrip()

        if cleaned.startswith(")]}'"):
            cleaned = cleaned[4:]

        try:
            outer = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        def search(value: Any) -> str | None:
            if isinstance(value, str):
                if value.startswith(("http://", "https://")):
                    return value
                return None

            if isinstance(value, list):
                for item in value:
                    result = search(item)

                    if result:
                        return result

            return None

        return search(outer)