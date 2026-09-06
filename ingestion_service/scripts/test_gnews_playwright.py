from gnews import GNews


def main() -> None:
    print("=" * 80)
    print("GNEWS PLAYWRIGHT TEST")
    print("=" * 80)
    print()

    google_news = GNews(
        language="en",
        country="IN",
        period="1d",
        max_results=10,
    )

    print("Searching for TCS...")
    print()

    articles = google_news.get_news("TCS")

    print(f"Articles returned: {len(articles)}")
    print()

    for index, article in enumerate(articles, start=1):
        print(f"[{index}]")
        print(f"Title     : {article.get('title')}")
        print(f"Publisher : {article.get('publisher')}")
        print(f"Published : {article.get('published date')}")
        print(f"URL       : {article.get('url')}")
        print()

    print("=" * 80)


if __name__ == "__main__":
    main()