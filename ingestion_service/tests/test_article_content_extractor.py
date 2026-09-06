from unittest.mock import Mock

import requests

from app.services.article_content_extractor import (
    ArticleContentExtractor,
)


ARTICLE_URL = "https://example.com/article"


def test_newspaper_extraction_success():
    html = """
    <html>
        <head>
            <title>Test Financial Article</title>
        </head>

        <body>
            <article>
                <p>
                    TCS reported strong quarterly results with
                    significant revenue growth across its major
                    business segments during the quarter.
                </p>

                <p>
                    The company also reported improved margins
                    and continued demand from international clients.
                </p>
            </article>
        </body>
    </html>
    """

    mock_session = Mock()

    mock_response = Mock()
    mock_response.text = html

    mock_session.get.return_value = mock_response

    extractor = ArticleContentExtractor(
        timeout=10,
        session=mock_session,
    )

    result = extractor.extract(ARTICLE_URL)

    assert result["status"] == "success"
    assert result["content"] is not None
    assert "TCS reported strong quarterly results" in result["content"]


def test_bs4_fallback():
    html = """
    <html>
        <head>
            <title>Fallback Financial Article</title>

            <meta
                property="og:image"
                content="https://example.com/image.jpg"
            >
        </head>

        <body>
            <nav>Navigation</nav>

            <div class="article-body">
                <p>
                    Reliance Industries announced a major
                    investment plan focused on expanding its
                    energy and technology businesses.
                </p>

                <p>
                    The company expects the investment to support
                    long-term growth and strengthen its position
                    across multiple business segments.
                </p>
            </div>

            <footer>Footer</footer>
        </body>
    </html>
    """

    extractor = ArticleContentExtractor(
        timeout=10,
    )

    result = extractor._extract_with_bs4(
        ARTICLE_URL,
        html,
    )

    assert result is not None
    assert result["title"] == "Fallback Financial Article"
    assert "Reliance Industries announced" in result["content"]
    assert "Navigation" not in result["content"]
    assert "Footer" not in result["content"]
    assert result["top_image"] == (
        "https://example.com/image.jpg"
    )


def test_http_403_is_handled():
    mock_session = Mock()

    response = Mock()
    response.status_code = 403

    error = requests.HTTPError(
        "403 Client Error",
        response=response,
    )

    mock_session.get.side_effect = error

    extractor = ArticleContentExtractor(
        timeout=10,
        session=mock_session,
    )

    result = extractor.extract(ARTICLE_URL)

    assert result["status"] == "failed"
    assert "HTTP 403" in result["error"]


def test_http_429_is_handled():
    mock_session = Mock()

    response = Mock()
    response.status_code = 429

    error = requests.HTTPError(
        "429 Client Error",
        response=response,
    )

    mock_session.get.side_effect = error

    extractor = ArticleContentExtractor(
        timeout=10,
        session=mock_session,
    )

    result = extractor.extract(ARTICLE_URL)

    assert result["status"] == "failed"
    assert "HTTP 429" in result["error"]


def test_network_error_is_handled():
    mock_session = Mock()

    mock_session.get.side_effect = (
        requests.RequestException(
            "Connection failed"
        )
    )

    extractor = ArticleContentExtractor(
        timeout=10,
        session=mock_session,
    )

    result = extractor.extract(ARTICLE_URL)

    assert result["status"] == "failed"
    assert result["error"] == "Connection failed"


def test_empty_content_returns_failed():
    html = """
    <html>
        <head>
            <title>Empty Article</title>
        </head>

        <body>
            <div>
                No useful article paragraphs here.
            </div>
        </body>
    </html>
    """

    extractor = ArticleContentExtractor(
        timeout=10,
    )

    result = extractor.extract(
        ARTICLE_URL,
    )

    assert result["status"] == "failed"
    assert result["content"] is None