from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase
from app.services.article_processing_service import ArticleProcessingService
from app.services.llm_analyzer import ArticleAnalyzer


def main() -> None:
    database = PostgresDatabase()

    repository = ArticleRepository(
        database=database
    )

    analyzer = ArticleAnalyzer()

    service = ArticleProcessingService(
        repository=repository,
        analyzer=analyzer,
    )

    stats = service.process_pending_articles(
        feed_id="company_tcs",
        feed_target="Tata Consultancy Services (TCS)",
        feed_description=(
            "News materially related to Tata Consultancy Services, "
            "including earnings, contracts, acquisitions, partnerships, "
            "leadership, AI initiatives, client wins or losses, "
            "stock performance, and events likely to affect "
            "TCS operations or valuation."
        ),
        limit=10,
    )

    print()
    print("Article processing completed.")
    print("-----------------------------")
    print("Fetched:   ", stats["fetched"])
    print("Processed: ", stats["processed"])
    print("Relevant:  ", stats["relevant"])
    print("Irrelevant:", stats["irrelevant"])
    print("Invalid:   ", stats["invalid"])
    print("Failed:    ", stats["failed"])


if __name__ == "__main__":
    main()