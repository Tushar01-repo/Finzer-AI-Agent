from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class GoogleNewsSearchResult:
    """Represents one article discovered through Google News Search."""

    title: str
    url: str
    source: str | None = None
    published_text: str | None = None


class GoogleSearchNewsParser:
    """
    Parses Google Search News HTML results.

    The parser is intentionally separated from the HTTP provider.
    This keeps network communication and HTML parsing independent.
    """

    GOOGLE_BASE_URL = "https://www.google.com"

    def parse(self, html: str) -> List[GoogleNewsSearchResult]:
        """
        Parse Google Search News HTML and return discovered articles.
        """

        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "html.parser")

        results: list[GoogleNewsSearchResult] = []

        for result in self._find_result_containers(soup):
            parsed_result = self._parse_result(result)

            if parsed_result is not None:
                results.append(parsed_result)

        return self._deduplicate(results)

    def _find_result_containers(self, soup: BeautifulSoup) -> list:
        """
        Find containers that potentially represent Google News results.

        Google can change its HTML structure, so we intentionally use
        several selectors rather than depending on a single CSS class.
        """

        selectors = [
            "div.SoaBEf",
            "div.MjjYud",
            "div.Gx5Zad",
        ]

        containers = []

        for selector in selectors:
            containers.extend(soup.select(selector))

        if containers:
            return self._unique_elements(containers)

        return self._fallback_containers(soup)

    def _fallback_containers(self, soup: BeautifulSoup) -> list:
        """
        Fallback discovery based on links.

        This provides some resilience when Google changes result
        container class names.
        """

        containers = []

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")

            if self._is_candidate_url(href):
                containers.append(anchor)

        return containers

    def _parse_result(self, container) -> GoogleNewsSearchResult | None:
        """Parse one potential search-result container."""

        anchor = self._find_article_link(container)

        if anchor is None:
            return None

        title = self._extract_title(container, anchor)

        if not title:
            return None

        url = self._extract_url(anchor)

        if not url:
            return None

        source = self._extract_source(container)
        published_text = self._extract_published_text(container)

        return GoogleNewsSearchResult(
            title=title,
            url=url,
            source=source,
            published_text=published_text,
        )

    def _find_article_link(self, container):
        """Find the primary article link."""

        if getattr(container, "name", None) == "a":
            return container

        for anchor in container.find_all("a", href=True):
            href = anchor.get("href", "")

            if self._is_candidate_url(href):
                return anchor

        return None

    def _extract_title(self, container, anchor) -> str | None:
        """Extract article title."""

        # Google commonly puts the title inside the anchor.
        title = anchor.get_text(" ", strip=True)

        if title:
            return title

        # Fallback to common heading tags.
        heading = container.find(["h1", "h2", "h3", "h4"])

        if heading:
            title = heading.get_text(" ", strip=True)

        return title or None

    def _extract_url(self, anchor) -> str | None:
        """Extract and normalize the article URL."""

        href = anchor.get("href")

        if not href:
            return None

        if href.startswith("/"):
            href = urljoin(self.GOOGLE_BASE_URL, href)

        if href.startswith("http://") or href.startswith("https://"):
            return href

        return None

    def _extract_source(self, container) -> str | None:
        """Extract publisher/source name when available."""

        selectors = [
            ".NUnG9d",
            ".CEMjEf",
            ".VuuXrf",
        ]

        for selector in selectors:
            element = container.select_one(selector)

            if element:
                value = element.get_text(" ", strip=True)

                if value:
                    return value

        # Generic fallback: look for short text blocks that are not
        # the article title.
        for element in container.find_all(["div", "span"]):
            text = element.get_text(" ", strip=True)

            if (
                text
                and len(text) <= 100
                and "http" not in text
            ):
                return text

        return None

    def _extract_published_text(self, container) -> str | None:
        """Extract relative publication-time text when available."""

        text = container.get_text(" ", strip=True)

        if not text:
            return None

        # Keep this deliberately simple. We will normalize actual
        # timestamps later if Google exposes structured time data.
        time_indicators = [
            "ago",
            "hour",
            "hours",
            "minute",
            "minutes",
            "day",
            "days",
            "week",
            "weeks",
            "month",
            "months",
            "year",
            "years",
        ]

        parts = text.split()

        for index, part in enumerate(parts):
            if part.lower() in time_indicators and index > 0:
                candidate = " ".join(parts[max(0, index - 2): index + 1])
                return candidate

        return None

    def _is_candidate_url(self, href: str) -> bool:
        """Determine whether a link can represent an article."""

        if not href:
            return False

        if href.startswith("http://") or href.startswith("https://"):
            return not self._is_google_internal_url(href)

        if href.startswith("/"):
            return not href.startswith((
                "/search",
                "/preferences",
                "/settings",
                "/advanced_search",
            ))

        return False

    def _is_google_internal_url(self, url: str) -> bool:
        """Exclude Google-owned navigation URLs."""

        google_domains = (
            "google.com",
            "google.co.in",
            "googleusercontent.com",
            "gstatic.com",
        )

        lowered = url.lower()

        return any(
            domain in lowered
            for domain in google_domains
        )

    def _deduplicate(
        self,
        results: list[GoogleNewsSearchResult],
    ) -> list[GoogleNewsSearchResult]:
        """Remove duplicate URLs while preserving order."""

        seen: set[str] = set()
        unique_results: list[GoogleNewsSearchResult] = []

        for result in results:
            if result.url in seen:
                continue

            seen.add(result.url)
            unique_results.append(result)

        return unique_results

    def _unique_elements(self, elements: list) -> list:
        """Remove duplicate BeautifulSoup elements."""

        seen: set[int] = set()
        unique = []

        for element in elements:
            element_id = id(element)

            if element_id in seen:
                continue

            seen.add(element_id)
            unique.append(element)

        return unique