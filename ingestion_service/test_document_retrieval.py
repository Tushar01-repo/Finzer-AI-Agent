from app.retrieval.document_retriever import DocumentRetriever


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)

QUERY = "What are the major risks associated with the company?"

TOP_K = 5


def main():
    print("=" * 70)
    print("Finzer - Document Retrieval Test")
    print("=" * 70)

    print(f"\nDocument key:\n{DOCUMENT_KEY}")
    print(f"\nQuery:\n{QUERY}")
    print(f"\nTop K: {TOP_K}")

    print("\nInitializing retriever...")

    retriever = DocumentRetriever()

    print(
        f"Embedding provider: "
        f"{retriever.embedding_provider}"
    )
    print(
        f"Embedding model: "
        f"{retriever.embedding_model}"
    )
    print(
        f"Embedding dimension: "
        f"{retriever.embedding_dimension}"
    )

    print("\nGenerating query embedding and searching pgvector...")

    results = retriever.retrieve(
        QUERY,
        document_key=DOCUMENT_KEY,
        top_k=TOP_K,
    )

    print(f"\nRetrieved {len(results)} chunks.")

    if not results:
        raise RuntimeError(
            "No chunks were returned by the retriever."
        )

    print("\n" + "=" * 70)
    print("TOP RETRIEVAL RESULTS")
    print("=" * 70)

    for rank, result in enumerate(
        results,
        start=1,
    ):
        content = (
            result.get("content") or ""
        ).strip()

        preview = (
            content[:700]
            .replace("\n", " ")
            .strip()
        )

        print()
        print("-" * 70)
        print(f"RANK #{rank}")
        print("-" * 70)

        print(
            f"Similarity   : "
            f"{result['similarity']:.4f}"
        )

        print(
            f"Chunk ID     : "
            f"{result['chunk_id']}"
        )

        print(
            f"Chunk Index  : "
            f"{result['chunk_index']}"
        )

        print(
            f"Content Type : "
            f"{result['content_type']}"
        )

        print(
            f"Pages        : "
            f"{result['page_start']}"
            f"-"
            f"{result['page_end']}"
        )

        print(
            f"Section      : "
            f"{result.get('section')}"
        )

        print(
            f"Subsection   : "
            f"{result.get('subsection')}"
        )

        print(
            f"Heading      : "
            f"{result.get('heading')}"
        )

        print(
            f"Token Count  : "
            f"{result['token_count']}"
        )

        print(
            f"Provider     : "
            f"{result['provider']}"
        )

        print(
            f"Model        : "
            f"{result['model']}"
        )

        print("\nContent preview:")
        print(preview)

    print("\n" + "=" * 70)
    print("DOCUMENT RETRIEVAL TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()