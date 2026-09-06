from app.services.rss_parser import RSSParser


def test_parse_rss_entry():
    rss_content = b"""
    <rss version="2.0">
        <channel>
            <title>Google News</title>

            <item>
                <title>TCS reports strong quarterly results</title>
                <link>https://news.google.com/rss/articles/example</link>
                <pubDate>Fri, 05 Sep 2026 10:00:00 GMT</pubDate>
                <source url="https://example.com">
                    Example News
                </source>
            </item>
        </channel>
    </rss>
    """

    feed = {
        "feed_id": "company_tcs",
        "feed_type": "company",
        "feed_value": "tcs",
        "query": "TCS OR Tata Consultancy Services",
        "enabled": True,
    }

    parser = RSSParser()

    articles = parser.parse(
        rss_content,
        feed,
    )

    assert len(articles) == 1

    article = articles[0]

    assert article["feed_id"] == "company_tcs"
    assert article["rss_title"] == "TCS reports strong quarterly results"
    assert (
        article["google_news_link"]
        == "https://news.google.com/rss/articles/example"
    )
    assert article["rss_published"] is not None
    assert article["rss_source"] == "Example News"


def test_parse_multiple_entries():
    rss_content = b"""
    <rss version="2.0">
        <channel>

            <item>
                <title>Article One</title>
                <link>https://news.google.com/article/1</link>
            </item>

            <item>
                <title>Article Two</title>
                <link>https://news.google.com/article/2</link>
            </item>

        </channel>
    </rss>
    """

    feed = {
        "feed_id": "market_india",
        "feed_type": "market",
        "feed_value": "india",
        "query": "India stock market",
        "enabled": True,
    }

    parser = RSSParser()

    articles = parser.parse(
        rss_content,
        feed,
    )

    assert len(articles) == 2
    assert articles[0]["rss_title"] == "Article One"
    assert articles[1]["rss_title"] == "Article Two"


def test_missing_optional_fields():
    rss_content = b"""
    <rss version="2.0">
        <channel>

            <item>
                <title>Article Without Metadata</title>
                <link>https://example.com/article</link>
            </item>

        </channel>
    </rss>
    """

    feed = {
        "feed_id": "market_india",
        "feed_type": "market",
        "feed_value": "india",
        "query": "India stock market",
        "enabled": True,
    }

    parser = RSSParser()

    articles = parser.parse(
        rss_content,
        feed,
    )

    assert len(articles) == 1

    article = articles[0]

    assert article["rss_title"] == "Article Without Metadata"
    assert article["google_news_link"] == "https://example.com/article"
    assert article["rss_published"] is None
    assert article["rss_source"] is None


def test_empty_rss():
    rss_content = b"""
    <rss version="2.0">
        <channel>
        </channel>
    </rss>
    """

    feed = {
        "feed_id": "market_india",
        "feed_type": "market",
        "feed_value": "india",
        "query": "India stock market",
        "enabled": True,
    }

    parser = RSSParser()

    articles = parser.parse(
        rss_content,
        feed,
    )

    assert articles == []