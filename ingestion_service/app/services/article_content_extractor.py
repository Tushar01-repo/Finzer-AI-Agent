from typing import Any

import requests
from bs4 import BeautifulSoup
from newspaper import Article


class ArticleContentExtractor:
    """
    Fetches and extracts article content from a publisher URL.

    Extraction strategy:
        1. Fetch article HTML
        2. Try newspaper3k
        3. Fall back to BeautifulSoup

    This component does not:
        - Resolve Google News URLs
        - Deduplicate articles
        - Store articles
        - Publish messages
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
    }

    BLOCKED_STATUS_CODES = {
        401,
        403,
        429,
    }

    def __init__(
        self,
        timeout: int = 20,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)

    def extract(
        self,
        url: str,
    ) -> dict[str, Any]:
        """
        Fetch and extract article information.

        Returns a structured dictionary even when extraction
        partially fails.
        """

        result = {
            "url": url,
            "title": None,
            "authors": [],
            "published_at": None,
            "content": None,
            "top_image": None,
            "status": "failed",
            "error": None,
        }

        try:
            html = self._fetch_html(url)

            newspaper_result = self._extract_with_newspaper(
                url,
                html,
            )

            if newspaper_result:
                result.update(newspaper_result)
                result["status"] = "success"
                return result

            bs4_result = self._extract_with_bs4(
                url,
                html,
            )

            if bs4_result:
                result.update(bs4_result)
                result["status"] = "success"
                return result

            result["error"] = "Article content extraction failed."

            return result

        except requests.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            if status_code in self.BLOCKED_STATUS_CODES:
                result["error"] = (
                    f"Publisher returned HTTP {status_code}."
                )
            else:
                result["error"] = str(exc)

            return result

        except requests.RequestException as exc:
            result["error"] = str(exc)
            return result

        except Exception as exc:
            result["error"] = str(exc)
            return result

    def _fetch_html(self, url: str) -> str:
        """
        Fetch publisher HTML.
        """

        response = self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response.text

    @staticmethod
    def _extract_with_newspaper(
        url: str,
        html: str,
    ) -> dict[str, Any] | None:
        """
        Extract article metadata and content using newspaper3k.
        """

        article = Article(url)

        article.set_html(html)
        article.parse()

        content = (article.text or "").strip()

        if not content:
            return None

        return {
            "title": (article.title or "").strip() or None,
            "authors": article.authors or [],
            "published_at": article.publish_date,
            "content": content,
            "top_image": (article.top_image or "").strip() or None,
        }

    @staticmethod
    def _extract_with_bs4(
        url: str,
        html: str,
    ) -> dict[str, Any] | None:
        """
        Extract article content using BeautifulSoup fallback.
        """

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for element in soup(
            [
                "script",
                "style",
                "nav",
                "header",
                "footer",
                "aside",
                "form",
                "noscript",
            ]
        ):
            element.decompose()

        title = None

        if soup.title:
            title = soup.title.get_text(
                " ",
                strip=True,
            )

        content_container = None

        selectors = [
            "article",
            '[itemprop="articleBody"]',
            ".article-body",
            ".article-content",
            ".story-body",
            ".story-content",
            ".post-content",
            ".entry-content",
            ".article__body",
            ".story__body",
        ]

        for selector in selectors:
            content_container = soup.select_one(selector)

            if content_container:
                break

        if content_container:
            paragraphs = content_container.find_all("p")
        else:
            paragraphs = soup.find_all("p")

        text_parts = []

        for paragraph in paragraphs:
            text = paragraph.get_text(
                " ",
                strip=True,
            )

            if len(text) >= 40:
                text_parts.append(text)

        content = "\n\n".join(text_parts).strip()

        if not content:
            return None

        image = soup.find(
            "meta",
            property="og:image",
        )

        top_image = None

        if image:
            top_image = image.get("content")

        return {
            "title": title,
            "authors": [],
            "published_at": None,
            "content": content,
            "top_image": top_image,
        }