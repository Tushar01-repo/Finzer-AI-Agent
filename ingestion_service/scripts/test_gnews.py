from gnews import GNews

from app.services.article_content_extractor import ArticleContentExtractor


def main() -> None:
    print("=" * 80)
    print("GNEWS + ARTICLE EXTRACTION TEST")
    print("=" * 80)
    print()

    # ------------------------------------------------------------------
    # Step 1: Initialize GNews
    # ------------------------------------------------------------------
    google_news = GNews(
        language="en",
        country="IN",
        period="1d",
        max_results=10,
    )

    print("Searching Google News for: TCS")
    print()

    # ------------------------------------------------------------------
    # Step 2: Search news
    # ------------------------------------------------------------------
    articles = google_news.get_news("TCS")

    print(f"Articles returned by GNews: {len(articles)}")
    print()

    if not articles:
        print("No articles returned by GNews.")
        return

    # ------------------------------------------------------------------
    # Step 3: Display discovered articles
    # ------------------------------------------------------------------
    print("-" * 80)
    print("DISCOVERED ARTICLES")
    print("-" * 80)

    for index, article in enumerate(articles, start=1):
        print(f"\n[{index}]")
        print(f"Title     : {article.get('title')}")
        print(f"Published : {article.get('published date')}")
        print(f"Publisher : {article.get('publisher')}")
        print(f"URL       : {article.get('url')}")

    # ------------------------------------------------------------------
    # Step 4: Try extracting the first article
    # ------------------------------------------------------------------
    first_article = articles[0]
    article_url = first_article.get("url")

    print()
    print("=" * 80)
    print("ARTICLE EXTRACTION TEST")
    print("=" * 80)
    print()

    print(f"URL: {article_url}")
    print()

    if not article_url:
        print("GNews did not return an article URL.")
        return

    extractor = ArticleContentExtractor()

    result = extractor.extract(article_url)

    print(f"Status : {result.get('status')}")
    print(f"Title  : {result.get('title')}")
    print(f"Error  : {result.get('error')}")
    print()

    content = result.get("content", "")

    print(f"Content length: {len(content)} characters")
    print()

    print("-" * 80)
    print("CONTENT PREVIEW")
    print("-" * 80)

    print(content[:3000])

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()