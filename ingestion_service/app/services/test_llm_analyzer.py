from app.services.llm_analyzer import ArticleAnalyzer

analyzer = ArticleAnalyzer()

result = analyzer.analyze(
    feed_id="company_tcs",
    feed_target="Tata Consultancy Services (TCS)",
    feed_description=(
        "News materially related to Tata Consultancy Services, including "
        "earnings, contracts, acquisitions, partnerships, leadership, "
        "AI initiatives, client wins or losses, stock performance, and "
        "events likely to affect TCS operations or valuation."
    ),
    title="TCS wins major digital transformation contract",
    source="Example Financial News",
    published_at="2026-09-10",
    content="""
Tata Consultancy Services announced that it secured a major digital
transformation contract with a global financial institution.

The agreement includes cloud modernization, artificial intelligence,
and automation services.

The financial value of the agreement was not disclosed.

Advertisement

Subscribe to our newsletter.

TCS shares were trading higher following the announcement.
""",
)

print("Valid:", result.is_valid_article)
print("Score:", result.relevance_score)
print("Relevant:", result.is_relevant)
print("Reason:", result.relevance_reason)
print("Summary:", result.summary)
print("Key facts:", result.key_facts)
print("Companies:", result.companies_mentioned)
print("Market impact:", result.market_impact)
print("Raw response:", result.raw_response)