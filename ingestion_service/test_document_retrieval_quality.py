from app.retrieval.document_retriever import DocumentRetriever


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)

TOP_K = 5


QUERIES = [
    "What are the major risks associated with the company?",
    "What is the company's primary business?",
    "What are the company's competitive strengths?",
    "What are the objects or purpose of the IPO issue?",
    "What outstanding litigation does the company have?",
]


def print_result(
    rank: int,
    result: dict,
) -> None:
    content = (
        result.get("content") or ""
    ).strip()

    # Keep output compact enough to compare multiple queries.
    preview = " ".join(
        content.split()
    )[:300]

    print(
        f"#{rank:<2} "
        f"score={result['similarity']:.4f} | "
        f"chunk={result['chunk_id']} | "
        f"index={result['chunk_index']} | "
        f"type={result['content_type']} | "
        f"pages={result['page_start']}-{result['page_end']}"
    )

    print(
        f"    section    = "
        f"{result.get('section')}"
    )

    print(
        f"    subsection = "
        f"{result.get('subsection')}"
    )

    print(
        f"    heading    = "
        f"{result.get('heading')}"
    )

    print(
        f"    preview    = "
        f"{preview}"
    )

    print()


def main():
    print("=" * 80)
    print("Finzer - Document Retrieval Quality Test")
    print("=" * 80)

    print(f"\nDocument key:\n{DOCUMENT_KEY}")
    print(f"\nQueries: {len(QUERIES)}")
    print(f"Top K: {TOP_K}")

    print("\nInitializing retriever...")

    retriever = DocumentRetriever()

    print(
        f"Provider  : "
        f"{retriever.embedding_provider}"
    )

    print(
        f"Model     : "
        f"{retriever.embedding_model}"
    )

    print(
        f"Dimension : "
        f"{retriever.embedding_dimension}"
    )

    all_results = []

    for query_number, query in enumerate(
        QUERIES,
        start=1,
    ):
        print("\n" + "=" * 80)

        print(
            f"QUERY {query_number}/{len(QUERIES)}"
        )

        print("=" * 80)

        print(f"\n{query}\n")

        results = retriever.retrieve(
            query,
            document_key=DOCUMENT_KEY,
            top_k=TOP_K,
        )

        if not results:
            raise RuntimeError(
                f"No retrieval results for query: {query}"
            )

        all_results.append(
            {
                "query": query,
                "results": results,
            }
        )

        for rank, result in enumerate(
            results,
            start=1,
        ):
            print_result(
                rank,
                result,
            )

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for query_number, item in enumerate(
        all_results,
        start=1,
    ):
        query = item["query"]
        results = item["results"]

        top_result = results[0]

        print()
        print(
            f"{query_number}. {query}"
        )

        print(
            f"   Top score   : "
            f"{top_result['similarity']:.4f}"
        )

        print(
            f"   Top section : "
            f"{top_result.get('section')}"
        )

        print(
            f"   Top pages   : "
            f"{top_result['page_start']}-"
            f"{top_result['page_end']}"
        )

        print(
            f"   Top chunk   : "
            f"{top_result['chunk_id']}"
        )

    print("\n" + "=" * 80)
    print("DOCUMENT RETRIEVAL QUALITY TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()