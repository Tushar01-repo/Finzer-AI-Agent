from app.retrieval.context_builder import DocumentContextBuilder
from app.retrieval.document_retriever import DocumentRetriever


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)

QUERY = "What are the major risks associated with the company?"

TOP_K = 5
MAX_CONTEXT_TOKENS = 4000


def main():
    print("=" * 80)
    print("Finzer - Document Context Builder Test")
    print("=" * 80)

    print(f"\nDocument key:\n{DOCUMENT_KEY}")
    print(f"\nQuery:\n{QUERY}")
    print(f"\nTop K: {TOP_K}")
    print(f"Context budget: {MAX_CONTEXT_TOKENS}")

    # ---------------------------------------------------------
    # Step 1: Initialize retriever
    # ---------------------------------------------------------

    print("\nInitializing retriever...")

    retriever = DocumentRetriever()

    print(
        f"Embedding provider : "
        f"{retriever.embedding_provider}"
    )

    print(
        f"Embedding model    : "
        f"{retriever.embedding_model}"
    )

    print(
        f"Embedding dimension: "
        f"{retriever.embedding_dimension}"
    )

    # ---------------------------------------------------------
    # Step 2: Retrieve relevant chunks
    # ---------------------------------------------------------

    print("\nRetrieving document chunks...")

    results = retriever.retrieve(
        QUERY,
        document_key=DOCUMENT_KEY,
        top_k=TOP_K,
    )

    print(
        f"Retrieved chunks: {len(results)}"
    )

    if not results:
        raise RuntimeError(
            "Retriever returned no results."
        )

    # ---------------------------------------------------------
    # Step 3: Build context
    # ---------------------------------------------------------

    print("\nBuilding LLM context...")

    builder = DocumentContextBuilder(
        max_context_tokens=MAX_CONTEXT_TOKENS,
    )

    built_context = builder.build(
        results
    )

    if not built_context.context:
        raise RuntimeError(
            "Context builder produced empty context."
        )

    # ---------------------------------------------------------
    # Step 4: Summary
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("CONTEXT SUMMARY")
    print("=" * 80)

    print(
        f"\nRetrieved chunks : "
        f"{len(results)}"
    )

    print(
        f"Selected sources : "
        f"{built_context.source_count}"
    )

    print(
        f"Estimated tokens : "
        f"{built_context.total_tokens}"
    )

    print(
        f"Token budget     : "
        f"{MAX_CONTEXT_TOKENS}"
    )

    assert built_context.source_count > 0

    assert (
        built_context.total_tokens
        <= MAX_CONTEXT_TOKENS
        or built_context.source_count == 1
    )

    # ---------------------------------------------------------
    # Step 5: Source metadata
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("SELECTED SOURCES")
    print("=" * 80)

    for source in built_context.sources:
        print()

        print(
            f"[Source {source['source_number']}]"
        )

        print(
            f"Retrieval Rank : "
            f"{source['retrieval_rank']}"
        )

        print(
            f"Chunk ID       : "
            f"{source['chunk_id']}"
        )

        print(
            f"Chunk Index    : "
            f"{source['chunk_index']}"
        )

        print(
            f"Content Type   : "
            f"{source['content_type']}"
        )

        print(
            f"Pages          : "
            f"{source['page_start']}-"
            f"{source['page_end']}"
        )

        print(
            f"Section        : "
            f"{source['section']}"
        )

        print(
            f"Subsection     : "
            f"{source['subsection']}"
        )

        print(
            f"Heading        : "
            f"{source['heading']}"
        )

        print(
            f"Chunk Tokens   : "
            f"{source['token_count']}"
        )

        print(
            f"Budget Tokens  : "
            f"{source['estimated_context_tokens']}"
        )

        print(
            f"Similarity     : "
            f"{source['similarity']:.4f}"
        )

    # ---------------------------------------------------------
    # Step 6: Show exact future LLM context
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("EXACT CONTEXT FOR FUTURE LLM")
    print("=" * 80)
    print()

    print(
        built_context.context
    )

    print()

    # ---------------------------------------------------------
    # Final checks
    # ---------------------------------------------------------

    source_numbers = [
        source["source_number"]
        for source in built_context.sources
    ]

    expected_source_numbers = list(
        range(
            1,
            built_context.source_count + 1,
        )
    )

    assert (
        source_numbers
        == expected_source_numbers
    ), "Source numbering is not sequential."

    chunk_ids = [
        source["chunk_id"]
        for source in built_context.sources
    ]

    assert (
        len(chunk_ids)
        == len(set(chunk_ids))
    ), "Duplicate chunks found in context."

    print("=" * 80)
    print("DOCUMENT CONTEXT BUILDER TEST PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()