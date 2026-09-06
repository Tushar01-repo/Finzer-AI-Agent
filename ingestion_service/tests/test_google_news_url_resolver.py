from unittest.mock import Mock

import requests

from app.services.google_news_url_resolver import (
    GoogleNewsURLResolver,
)


GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/articles/"
    "example_token_123"
)


def test_is_google_news_url():
    assert (
        GoogleNewsURLResolver.is_google_news_url(
            GOOGLE_NEWS_URL
        )
        is True
    )


def test_non_google_news_url():
    assert (
        GoogleNewsURLResolver.is_google_news_url(
            "https://example.com/article"
        )
        is False
    )


def test_extract_token():
    token = GoogleNewsURLResolver._extract_token(
        GOOGLE_NEWS_URL
    )

    assert token == "example_token_123"


def test_resolve_non_google_news_url():
    resolver = GoogleNewsURLResolver()

    url = "https://example.com/article"

    assert resolver.resolve(url) == url


def test_resolve_successfully():
    mock_session = Mock()

    wrapper_response = Mock()
    wrapper_response.text = """
        <html>
            <div
                data-n-a-sg="test_signature"
                data-n-a-ts="123456789"
            >
            </div>
        </html>
    """

    decode_response = Mock()

    decode_response.text = """
    )]}'
    [
        [
            [
                "https://publisher.com/article/tcs-results"
            ]
        ]
    ]
    """

    mock_session.get.return_value = wrapper_response
    mock_session.post.return_value = decode_response

    resolver = GoogleNewsURLResolver(
        timeout=10,
        session=mock_session,
    )

    resolved_url = resolver.resolve(
        GOOGLE_NEWS_URL
    )

    assert (
        resolved_url
        == "https://publisher.com/article/tcs-results"
    )

    mock_session.get.assert_called_once()
    mock_session.post.assert_called_once()


def test_resolution_failure_returns_original_url():
    mock_session = Mock()

    mock_session.get.side_effect = (
        requests.RequestException("network error")
    )

    resolver = GoogleNewsURLResolver(
        timeout=10,
        session=mock_session,
    )

    resolved_url = resolver.resolve(
        GOOGLE_NEWS_URL
    )

    assert resolved_url == GOOGLE_NEWS_URL