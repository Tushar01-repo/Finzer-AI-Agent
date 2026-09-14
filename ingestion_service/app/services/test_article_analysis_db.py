from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase
from app.services.llm_analyzer import ArticleAnalyzer


def main() -> None:
    print("=" * 70)
    print("Finzer - PostgreSQL -> LLM -> PostgreSQL Test")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. Initialize database
    # ---------------------------------------------------------

    database = PostgresDatabase()
    repository = ArticleRepository(database)

    # ---------------------------------------------------------
    # 2. Initialize LLM analyzer
    # ---------------------------------------------------------

    analyzer = ArticleAnalyzer()

    print()
    print("LLM configuration")
    print("-----------------")
    print("LLM URL:", analyzer.base_url)
    print("Model:", analyzer.model)
    print(
        "Relevance threshold:",
        analyzer.relevance_threshold,
    )

    # ---------------------------------------------------------
    # 3. Get ONE pending article
    # ---------------------------------------------------------

    pending_articles = repository.get_pending_articles(
        limit=1
    )

    if not pending_articles:
        print()
        print("No pending articles found.")
        return

    article = pending_articles[0]

    print()
    print("Article selected")
    print("----------------")
    print("Article key:", article.article_key)
    print("Title:", article.title)
    print("Source:", article.source)
    print("Published:", article.published_at)
    print(
        "Content length:",
        len(article.content or ""),
    )

    if not article.content:
        print()
        print("Article has no content.")
        print("Skipping analysis.")
        return

    # ---------------------------------------------------------
    # 4. Run LLM analysis
    # ---------------------------------------------------------

    print()
    print("Sending article to LLM...")

    result = analyzer.analyze(
        feed_id="company_tcs",
        feed_target=(
            "Tata Consultancy Services (TCS)"
        ),
        feed_description=(
            "News materially related to Tata Consultancy "
            "Services, including earnings, contracts, "
            "acquisitions, partnerships, leadership, "
            "AI initiatives, client wins or losses, "
            "stock performance, and events likely to "
            "affect TCS operations or valuation."
        ),
        title=article.title,
        source=article.source,
        published_at=(
            article.published_at.isoformat()
            if article.published_at
            else None
        ),
        content=article.content,
    )

    # ---------------------------------------------------------
    # 5. Display analysis
    # ---------------------------------------------------------

    print()
    print("LLM Analysis")
    print("------------")

    print(
        "Valid article:",
        result.is_valid_article,
    )

    print(
        "Relevance score:",
        result.relevance_score,
    )

    print(
        "Relevant:",
        result.is_relevant,
    )

    print(
        "Reason:",
        result.relevance_reason,
    )

    print(
        "Summary:",
        result.summary,
    )

    print(
        "Key facts:",
        result.key_facts,
    )

    print(
        "Companies:",
        result.companies_mentioned,
    )

    print(
        "Market impact:",
        result.market_impact,
    )

    # ---------------------------------------------------------
    # 6. Save analysis into PostgreSQL
    # ---------------------------------------------------------

    print()
    print("Saving analysis to PostgreSQL...")

    repository.save_article_analysis(
        article_key=article.article_key,
        is_valid_article=(
            result.is_valid_article
        ),
        relevance_score=(
            result.relevance_score
        ),
        is_relevant=result.is_relevant,
        relevance_reason=(
            result.relevance_reason
        ),
        summary=result.summary,
        key_facts=result.key_facts,
        companies_mentioned=(
            result.companies_mentioned
        ),
        market_impact=result.market_impact,
        llm_analysis=result.raw_response,
    )

    print("Analysis saved successfully.")

    # ---------------------------------------------------------
    # 7. Show final status
    # ---------------------------------------------------------

    if not result.is_valid_article:
        status = "invalid"

    elif result.is_relevant:
        status = "analyzed"

    else:
        status = "irrelevant"

    print()
    print("=" * 70)
    print("Processing completed")
    print("=" * 70)

    print("Article key:", article.article_key)
    print("Relevance:", result.relevance_score)
    print("Final status:", status)


if __name__ == "__main__":
    main()