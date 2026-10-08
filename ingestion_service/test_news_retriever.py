from datetime import datetime, timezone

from app.retrieval.news_retriever import NewsRetriever


def print_results(name: str, results: list[dict]) -> None:
    print()
    print("=" * 80)
    print(name)
    print("=" * 80)

    if not results:
        print("NO RESULTS")
        return

    for result in results:
        print()
        print(f"Rank:       {result['retrieval_rank']}")
        print(f"Title:      {result['title']}")
        print(f"Source:     {result['source']}")
        print(f"Published:  {result['published_at']}")
        print(f"Companies:  {result['companies_mentioned']}")
        print(f"Similarity: {result['similarity']}")
        print(f"Provider:   {result['embedding_provider']}")
        print(f"Model:      {result['embedding_model']}")


def main() -> None:
    retriever = NewsRetriever()

    # ---------------------------------------------------------
    # TEST 1
    # Semantic retrieval for HDFC Bank.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "HDFC Bank share price outlook and analyst target",
        top_k=2,
    )

    print_results(
        "TEST 1 - HDFC SEMANTIC RETRIEVAL",
        results,
    )

    assert len(results) > 0
    assert "HDFC" in results[0]["title"].upper()

    # ---------------------------------------------------------
    # TEST 2
    # Semantic retrieval for Apple Pay.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "Apple Pay launch in India",
        top_k=2,
    )

    print_results(
        "TEST 2 - APPLE PAY SEMANTIC RETRIEVAL",
        results,
    )

    assert len(results) > 0
    assert "APPLE PAY" in results[0]["title"].upper()

    # ---------------------------------------------------------
    # TEST 3
    # Exact company metadata filter.
    #
    # Only the Apple Pay article currently mentions Visa.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "digital payments in India",
        company="Visa",
        top_k=5,
    )

    print_results(
        "TEST 3 - VISA COMPANY FILTER",
        results,
    )

    assert len(results) == 1
    assert "Visa" in results[0]["companies_mentioned"]

    # ---------------------------------------------------------
    # TEST 4
    # Both indexed articles currently mention HDFC Bank.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "HDFC Bank",
        company="HDFC Bank",
        top_k=5,
    )

    print_results(
        "TEST 4 - HDFC BANK COMPANY FILTER",
        results,
    )

    assert len(results) == 2

    for result in results:
        assert "HDFC Bank" in result["companies_mentioned"]

    # ---------------------------------------------------------
    # TEST 5
    # Publication date lower bound.
    #
    # Both current indexed articles are from 2026-09-21.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "Indian financial markets",
        published_after=datetime(
            2026,
            9,
            21,
            tzinfo=timezone.utc,
        ),
        top_k=5,
    )

    print_results(
        "TEST 5 - DATE FILTER",
        results,
    )

    assert len(results) == 2

    # ---------------------------------------------------------
    # TEST 6
    # Future date should return no articles.
    # ---------------------------------------------------------
    results = retriever.retrieve(
        "Indian financial markets",
        published_after=datetime(
            2030,
            1,
            1,
            tzinfo=timezone.utc,
        ),
        top_k=5,
    )

    print_results(
        "TEST 6 - FUTURE DATE FILTER",
        results,
    )

    assert results == []

    print()
    print("=" * 80)
    print("ALL NEWS RETRIEVER TESTS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()