from app.providers.news.newsdata import NewsDataProvider


def main() -> None:
    provider = NewsDataProvider()

    print(f"Provider: {provider.name}")
    print("Discovering articles...\n")

    articles = provider.discover(
        query="Tata Consultancy Services",
        max_articles=20,
    )

    print(f"Articles discovered: {len(articles)}")
    print("=" * 80)

    for index, article in enumerate(articles, start=1):
        print(f"\nArticle {index}")
        print(f"Title       : {article.title}")
        print(f"Source      : {article.source}")
        print(f"URL         : {article.url}")
        print(f"Published   : {article.published_at}")
        print(f"Authors     : {article.authors}")
        print(f"Description : {article.description}")
        print("-" * 80)


if __name__ == "__main__":
    main()