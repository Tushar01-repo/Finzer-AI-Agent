import logging
from typing import Any

import requests
from bs4 import BeautifulSoup
from newspaper import Article
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class ArticleContentExtractor:
    """
    Fetches and extracts article content from a publisher URL.

    Extraction strategy:
        1. Fetch publisher HTML using requests
        2. Retry transient HTTP/network failures
        3. Try newspaper3k extraction
        4. Fall back to BeautifulSoup
        5. Validate extracted content
        6. Return structured success/failure information

    Retries are only intended for transient failures.

    We retry:
        - Connection failures
        - Read failures / timeouts
        - HTTP 429
        - Selected HTTP 5xx responses

    We do not retry:
        - HTTP 401
        - HTTP 403
        - HTTP 404
        - Security challenge pages
        - Insufficient extracted content

    This component does not:
        - Resolve Google News URLs
        - Deduplicate articles
        - Store articles
        - Publish messages
        - Use Playwright/browser automation
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
    }

    RETRY_STATUS_CODES = {
        429,
        500,
        502,
        503,
        504,
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
        retry_count: int = 2,
        backoff_factor: float = 1.0,
        session: requests.Session | None = None,
    ):
        """
        Args:
            timeout:
                HTTP request timeout in seconds.

            retry_count:
                Number of retries after the initial request.

                retry_count=2 means:

                    initial request
                    + retry 1
                    + retry 2

            backoff_factor:
                Controls exponential delay between retries.

            session:
                Optional requests.Session.
                Useful for testing/dependency injection.
        """

        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than zero."
            )

        if retry_count < 0:
            raise ValueError(
                "retry_count cannot be negative."
            )

        if backoff_factor < 0:
            raise ValueError(
                "backoff_factor cannot be negative."
            )

        self.timeout = timeout
        self.retry_count = retry_count
        self.backoff_factor = backoff_factor

        self.session = (
            session
            or requests.Session()
        )

        self.session.headers.update(
            self.HEADERS
        )

        self._configure_retries()

    def _configure_retries(self) -> None:
        """
        Configure retry behavior for HTTP and HTTPS requests.

        GET requests may be retried for:
            - connection failures
            - read failures
            - HTTP 429
            - selected 5xx errors
        """

        retry_strategy = Retry(
            total=self.retry_count,
            connect=self.retry_count,
            read=self.retry_count,
            status=self.retry_count,
            allowed_methods={
                "GET",
            },
            status_forcelist=self.RETRY_STATUS_CODES,
            backoff_factor=self.backoff_factor,
            respect_retry_after_header=True,
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy
        )

        self.session.mount(
            "http://",
            adapter,
        )

        self.session.mount(
            "https://",
            adapter,
        )

    def extract(
        self,
        url: str,
    ) -> dict[str, Any]:
        """
        Fetch and extract article information.

        Returns structured information for both success
        and failure cases.
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

            # ----------------------------------------------------------
            # Security challenge detection
            # ----------------------------------------------------------

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
            # HTML fetched, but content was not sufficient
            # ----------------------------------------------------------

            result["error_type"] = (
                "insufficient_content"
            )

            result["error"] = (
                "Publisher page was fetched, but sufficient "
                "article content could not be extracted."
            )

            return result

        # --------------------------------------------------------------
        # Timeout
        # --------------------------------------------------------------

        except requests.Timeout as exc:
            result["error_type"] = (
                "timeout"
            )

            result["error"] = (
                "Publisher request timed out after retries "
                f"were exhausted: {exc}"
            )

            return result

        # --------------------------------------------------------------
        # HTTP errors
        # --------------------------------------------------------------

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

            elif status_code == 429:
                result["error"] = (
                    "Publisher returned HTTP 429 "
                    "after retries were exhausted."
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
                    f"HTTP {status_code} after retries "
                    f"were exhausted."
                )

            else:
                result["error"] = (
                    str(exc)
                )

            return result

        # --------------------------------------------------------------
        # Connection errors
        #
        # urllib3 may wrap exhausted read/connect timeouts inside
        # requests.ConnectionError.
        #
        # Detect those cases so they remain classified as "timeout".
        # --------------------------------------------------------------

        except requests.ConnectionError as exc:
            if self._is_retry_exhausted_timeout(
                exc
            ):
                result["error_type"] = (
                    "timeout"
                )

                result["error"] = (
                    "Publisher request timed out after "
                    f"retries were exhausted: {exc}"
                )

            else:
                result["error_type"] = (
                    "connection_error"
                )

                result["error"] = (
                    "Publisher connection failed after "
                    f"retries were exhausted: {exc}"
                )

            return result

        # --------------------------------------------------------------
        # Other requests errors
        # --------------------------------------------------------------

        except requests.RequestException as exc:
            result["error_type"] = (
                "request_error"
            )

            result["error"] = (
                str(exc)
            )

            return result

        # --------------------------------------------------------------
        # Unexpected extraction errors
        # --------------------------------------------------------------

        except Exception as exc:
            result["error_type"] = (
                "extraction_error"
            )

            result["error"] = (
                str(exc)
            )

            return result

    def _fetch_html(
        self,
        url: str,
    ) -> tuple[str, int]:
        """
        Fetch publisher HTML.

        Retry behavior is handled by the configured
        requests Session.
        """

        logger.debug(
            "Fetching article HTML: url=%s",
            url,
        )

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

        Failure here does not fail the complete extraction because
        BeautifulSoup is attempted afterwards.
        """

        try:
            article = Article(
                url
            )

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

        except Exception as exc:
            logger.debug(
                "newspaper3k extraction failed: %s",
                exc,
            )

            return None

    @staticmethod
    def _extract_with_bs4(
        url: str,
        html: str,
    ) -> dict[str, Any] | None:
        """
        Extract article content using BeautifulSoup.
        """

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        # --------------------------------------------------------------
        # Remove common non-content elements
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------

        title = None

        if soup.title:
            title = soup.title.get_text(
                " ",
                strip=True,
            )

        # --------------------------------------------------------------
        # Search for common article containers
        # --------------------------------------------------------------

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
            paragraphs = (
                soup.find_all(
                    "p"
                )
            )

        # --------------------------------------------------------------
        # Extract and deduplicate paragraphs
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # OpenGraph image
        # --------------------------------------------------------------

        image = soup.find(
            "meta",
            property="og:image",
        )

        top_image = None

        if image:
            top_image = (
                image.get(
                    "content"
                )
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
        Determine whether extracted text is substantial enough
        to represent a real article.
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

        return len(
            paragraphs
        )

    def _contains_security_challenge(
        self,
        html: str,
    ) -> bool:
        """
        Detect common anti-bot/security challenge pages.
        """

        if not html:
            return False

        normalized_html = (
            html.lower()
        )

        return any(
            phrase in normalized_html
            for phrase in self.CHALLENGE_PHRASES
        )

    def _classify_http_error(
        self,
        status_code: int | None,
    ) -> str:
        """
        Convert HTTP status codes into internal failure categories.
        """

        if (
            status_code
            in self.BLOCKED_STATUS_CODES
        ):
            return "blocked"

        if status_code == 404:
            return "not_found"

        if status_code == 429:
            return "request_error"

        if (
            status_code is not None
            and status_code >= 500
        ):
            return "server_error"

        return "http_error"

    @staticmethod
    def _is_retry_exhausted_timeout(
        exc: Exception,
    ) -> bool:
        """
        Detect timeout failures that urllib3/requests may wrap
        inside ConnectionError after retry exhaustion.

        Example chain:

            requests.ConnectionError
                ↓
            urllib3.MaxRetryError
                ↓
            ReadTimeoutError

        We inspect both exception class names and messages so the
        final failure remains classified as "timeout".
        """

        current: BaseException | None = (
            exc
        )

        visited: set[int] = set()

        while current is not None:
            current_id = id(
                current
            )

            if current_id in visited:
                break

            visited.add(
                current_id
            )

            class_name = (
                current
                .__class__
                .__name__
                .lower()
            )

            message = (
                str(current)
                .lower()
            )

            timeout_class_indicators = (
                "timeout",
                "readtimeouterror",
                "connecttimeouterror",
            )

            timeout_message_indicators = (
                "timed out",
                "read timeout",
                "connect timeout",
                "connection timeout",
            )

            if any(
                indicator in class_name
                for indicator
                in timeout_class_indicators
            ):
                return True

            if any(
                indicator in message
                for indicator
                in timeout_message_indicators
            ):
                return True

            current = (
                current.__cause__
                or current.__context__
            )

        return False