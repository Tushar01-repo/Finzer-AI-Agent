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

    Every extraction result contains structured information
    describing whether extraction succeeded or why it failed.
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

    MIN_CONTENT_LENGTH = 500
    MIN_PARAGRAPHS = 3

    CHALLENGE_PHRASES = (
        "one-time security check",
        "verify you are human",
        "verify that you are human",
        "checking your browser",
        "access denied",
        "captcha",
        "cloudflare",
        "enable javascript",
        "enable cookies",
        "please wait while we verify",
    )

    def __init__(
        self,
        timeout: int = 20,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout

        self.session = (
            session
            or requests.Session()
        )

        self.session.headers.update(
            self.HEADERS
        )

    def extract(
        self,
        url: str,
    ) -> dict[str, Any]:
        """
        Fetch and extract article information.

        Returns a structured dictionary for both successful
        and failed extraction attempts.

        Failure types may include:
            - blocked
            - not_found
            - server_error
            - timeout
            - connection_error
            - request_error
            - security_challenge
            - insufficient_content
            - extraction_error
        """

        result: dict[str, Any] = {
            "url": url,
            "title": None,
            "authors": [],
            "published_at": None,
            "content": None,
            "top_image": None,

            # Extraction metadata
            "status": "failed",
            "method": None,
            "error": None,
            "error_type": None,
            "status_code": None,
            "paragraph_count": 0,
        }

        try:
            html, status_code = self._fetch_html(
                url
            )

            result["status_code"] = (
                status_code
            )

            if self._contains_security_challenge(
                html
            ):
                result["error_type"] = (
                    "security_challenge"
                )

                result["error"] = (
                    "Publisher returned a security "
                    "or anti-bot challenge page."
                )

                return result

            # ----------------------------------------------------------
            # Primary extraction: newspaper3k
            # ----------------------------------------------------------

            newspaper_result = (
                self._extract_with_newspaper(
                    url,
                    html,
                )
            )

            if newspaper_result:
                content = (
                    newspaper_result.get(
                        "content"
                    )
                    or ""
                )

                paragraph_count = (
                    self._count_paragraphs(
                        content
                    )
                )

                if self._is_content_valid(
                    content,
                    paragraph_count,
                ):
                    result.update(
                        newspaper_result
                    )

                    result["status"] = (
                        "success"
                    )

                    result["method"] = (
                        "newspaper3k"
                    )

                    result[
                        "paragraph_count"
                    ] = paragraph_count

                    result["error"] = None
                    result["error_type"] = None

                    return result

            # ----------------------------------------------------------
            # Fallback extraction: BeautifulSoup
            # ----------------------------------------------------------

            bs4_result = (
                self._extract_with_bs4(
                    url,
                    html,
                )
            )

            if bs4_result:
                content = (
                    bs4_result.get(
                        "content"
                    )
                    or ""
                )

                paragraph_count = (
                    bs4_result.get(
                        "paragraph_count",
                        0,
                    )
                )

                if self._is_content_valid(
                    content,
                    paragraph_count,
                ):
                    result.update(
                        bs4_result
                    )

                    result["status"] = (
                        "success"
                    )

                    result["method"] = (
                        "beautifulsoup"
                    )

                    result[
                        "paragraph_count"
                    ] = paragraph_count

                    result["error"] = None
                    result["error_type"] = None

                    return result

            # ----------------------------------------------------------
            # HTML was fetched successfully but usable article content
            # could not be extracted.
            # ----------------------------------------------------------

            result["error_type"] = (
                "insufficient_content"
            )

            result["error"] = (
                "Publisher page was fetched, but sufficient "
                "article content could not be extracted."
            )

            return result

        except requests.Timeout as exc:
            result["error_type"] = "timeout"

            result["error"] = (
                f"Publisher request timed out "
                f"after {self.timeout} seconds: {exc}"
            )

            return result

        except requests.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            result["status_code"] = (
                status_code
            )

            result["error_type"] = (
                self._classify_http_error(
                    status_code
                )
            )

            if (
                status_code
                in self.BLOCKED_STATUS_CODES
            ):
                result["error"] = (
                    f"Publisher returned HTTP "
                    f"{status_code}."
                )

            elif status_code == 404:
                result["error"] = (
                    "Publisher returned HTTP 404."
                )

            elif (
                status_code is not None
                and status_code >= 500
            ):
                result["error"] = (
                    f"Publisher returned server error "
                    f"HTTP {status_code}."
                )

            else:
                result["error"] = (
                    str(exc)
                )

            return result

        except requests.ConnectionError as exc:
            result["error_type"] = (
                "connection_error"
            )

            result["error"] = str(exc)

            return result

        except requests.RequestException as exc:
            result["error_type"] = (
                "request_error"
            )

            result["error"] = str(exc)

            return result

        except Exception as exc:
            result["error_type"] = (
                "extraction_error"
            )

            result["error"] = str(exc)

            return result

    def _fetch_html(
        self,
        url: str,
    ) -> tuple[str, int]:
        """
        Fetch publisher HTML.

        Returns:
            Tuple containing:
                - response HTML
                - HTTP status code
        """

        response = self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        return (
            response.text,
            response.status_code,
        )

    @staticmethod
    def _extract_with_newspaper(
        url: str,
        html: str,
    ) -> dict[str, Any] | None:
        """
        Extract article metadata and content using newspaper3k.
        """

        try:
            article = Article(url)

            article.set_html(
                html
            )

            article.parse()

            content = (
                article.text
                or ""
            ).strip()

            if not content:
                return None

            return {
                "title": (
                    article.title
                    or ""
                ).strip()
                or None,

                "authors": (
                    article.authors
                    or []
                ),

                "published_at": (
                    article.publish_date
                ),

                "content": content,

                "top_image": (
                    article.top_image
                    or ""
                ).strip()
                or None,
            }

        except Exception:
            # Failure in newspaper3k should not stop extraction.
            # BeautifulSoup will be attempted next.
            return None

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
            content_container = (
                soup.select_one(
                    selector
                )
            )

            if content_container:
                break

        if content_container:
            paragraphs = (
                content_container.find_all(
                    "p"
                )
            )
        else:
            paragraphs = soup.find_all(
                "p"
            )

        text_parts: list[str] = []

        seen_paragraphs: set[str] = set()

        for paragraph in paragraphs:
            text = paragraph.get_text(
                " ",
                strip=True,
            )

            text = " ".join(
                text.split()
            )

            if len(text) < 40:
                continue

            # Avoid duplicated paragraphs.
            normalized_text = (
                text.lower()
            )

            if (
                normalized_text
                in seen_paragraphs
            ):
                continue

            seen_paragraphs.add(
                normalized_text
            )

            text_parts.append(
                text
            )

        content = "\n\n".join(
            text_parts
        ).strip()

        if not content:
            return None

        image = soup.find(
            "meta",
            property="og:image",
        )

        top_image = None

        if image:
            top_image = image.get(
                "content"
            )

        return {
            "title": title,
            "authors": [],
            "published_at": None,
            "content": content,
            "top_image": top_image,
            "paragraph_count": len(
                text_parts
            ),
        }

    def _is_content_valid(
        self,
        content: str,
        paragraph_count: int,
    ) -> bool:
        """
        Check whether extracted content is substantial enough
        to be treated as an article.
        """

        if not content:
            return False

        if (
            len(content)
            < self.MIN_CONTENT_LENGTH
        ):
            return False

        if (
            paragraph_count
            < self.MIN_PARAGRAPHS
        ):
            return False

        return True

    @staticmethod
    def _count_paragraphs(
        content: str,
    ) -> int:
        """
        Estimate paragraph count from extracted text.
        """

        if not content:
            return 0

        paragraphs = [
            paragraph.strip()
            for paragraph in content.split(
                "\n"
            )
            if paragraph.strip()
        ]

        return len(paragraphs)

    def _contains_security_challenge(
        self,
        html: str,
    ) -> bool:
        """
        Detect common anti-bot / security challenge pages.
        """

        if not html:
            return False

        normalized_html = (
            html.lower()
        )

        return any(
            phrase
            in normalized_html
            for phrase
            in self.CHALLENGE_PHRASES
        )

    def _classify_http_error(
        self,
        status_code: int | None,
    ) -> str:
        """
        Convert an HTTP error status into an internal
        extraction failure category.
        """

        if (
            status_code
            in self.BLOCKED_STATUS_CODES
        ):
            return "blocked"

        if status_code == 404:
            return "not_found"

        if (
            status_code is not None
            and status_code >= 500
        ):
            return "server_error"

        return "http_error"