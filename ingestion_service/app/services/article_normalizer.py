import hashlib
import re
from datetime import datetime
from typing import Any
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlparse,
    urlunparse,
)


class ArticleNormalizer:
    """
    Normalizes extracted article data and generates deterministic hashes.

    Responsibilities:
    - Normalize publisher URLs
    - Normalize text fields
    - Normalize source names
    - Normalize published timestamps
    - Generate article_key
    - Generate content_hash
    """

    TRACKING_PARAMETERS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
    }

    def normalize(
        self,
        article: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Normalize an extracted article.

        The returned dictionary contains the original useful
        fields plus canonical URL and hashes.
        """

        normalized_url = self.normalize_url(
            article.get("url")
        )

        normalized_title = self.normalize_text(
            article.get("title")
        )

        normalized_content = self.normalize_text(
            article.get("content")
        )

        normalized_source = self.normalize_text(
            article.get("source")
        )

        normalized = {
            **article,
            "url": normalized_url,
            "title": normalized_title,
            "content": normalized_content,
            "source": normalized_source,
            "published_at": self.normalize_datetime(
                article.get("published_at")
            ),
            "article_key": self.generate_hash(
                normalized_url
            ),
            "content_hash": self.generate_hash(
                normalized_content
            ),
        }

        return normalized

    @classmethod
    def normalize_url(
        cls,
        url: str | None,
    ) -> str | None:
        """
        Normalize a publisher URL.

        Removes:
        - URL fragments
        - Common tracking parameters

        Normalizes:
        - scheme
        - hostname
        - trailing slash
        - query parameter ordering
        """

        if not url:
            return None

        url = url.strip()

        if not url:
            return None

        parsed = urlparse(url)

        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()

        if not hostname:
            return url

        port = parsed.port

        if port:
            if (
                (scheme == "http" and port != 80)
                or (scheme == "https" and port != 443)
            ):
                hostname = f"{hostname}:{port}"

        netloc = hostname

        if parsed.username or parsed.password:
            # Preserve authentication syntax if present.
            # This is mainly defensive; article URLs normally
            # should not contain credentials.
            user_info = parsed.username or ""

            if parsed.password:
                user_info += f":{parsed.password}"

            netloc = f"{user_info}@{netloc}"

        path = parsed.path or "/"

        if path != "/":
            path = path.rstrip("/")

        query_parameters = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key.lower() not in cls.TRACKING_PARAMETERS
        ]

        query_parameters.sort()

        query = urlencode(
            query_parameters,
            doseq=True,
        )

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                query,
                "",
            )
        )

    @staticmethod
    def normalize_text(
        value: str | None,
    ) -> str | None:
        """
        Normalize whitespace in text.
        """

        if value is None:
            return None

        value = str(value)

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        value = value.strip()

        return value or None

    @staticmethod
    def normalize_datetime(
        value: Any,
    ) -> datetime | None:
        """
        Normalize datetime values.

        Naive datetimes are returned unchanged.
        Aware datetimes are converted to UTC.
        """

        if value is None:
            return None

        if not isinstance(value, datetime):
            return value

        if value.tzinfo is not None:
            from datetime import timezone

            return value.astimezone(
                timezone.utc
            )

        return value

    @staticmethod
    def generate_hash(
        value: str | None,
    ) -> str | None:
        """
        Generate SHA-256 hash for a string.
        """

        if value is None:
            return None

        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()