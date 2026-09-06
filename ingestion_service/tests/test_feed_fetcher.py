from unittest.mock import Mock

from app.services.feed_fetcher import FeedFetcher


def test_build_feed_url():
    fetcher = FeedFetcher(
        timeout=5,
        delay_seconds=0,
    )

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS OR Tata Consultancy Services",
        "enabled": True,
    }

    url = fetcher.build_feed_url(feed)

    assert url.startswith(
        "https://news.google.com/rss/search?"
    )

    assert "q=TCS+OR+Tata+Consultancy+Services" in url
    assert "hl=en-IN" in url
    assert "gl=IN" in url
    assert "ceid=IN%3Aen" in url


def test_fetch_returns_response_content():
    mock_session = Mock()

    mock_response = Mock()
    mock_response.content = b"<rss>test</rss>"

    mock_session.get.return_value = mock_response

    fetcher = FeedFetcher(
        timeout=5,
        delay_seconds=0,
        session=mock_session,
    )

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS OR Tata Consultancy Services",
        "enabled": True,
    }

    content = fetcher.fetch(feed)

    assert content == b"<rss>test</rss>"

    mock_session.get.assert_called_once()

    mock_response.raise_for_status.assert_called_once()


def test_fetch_uses_configured_timeout():
    mock_session = Mock()

    mock_response = Mock()
    mock_response.content = b"<rss>test</rss>"

    mock_session.get.return_value = mock_response

    fetcher = FeedFetcher(
        timeout=7,
        delay_seconds=0,
        session=mock_session,
    )

    feed = {
        "feed_id": "market_india",
        "feed_type": "market",
        "feed_value": "india",
        "query": "India stock market",
        "enabled": True,
    }

    fetcher.fetch(feed)

    _, kwargs = mock_session.get.call_args

    assert kwargs["timeout"] == 7
    assert kwargs["allow_redirects"] is True