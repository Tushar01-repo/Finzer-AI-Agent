# Finzer AI --- MCP, Tool Registry & Retrieval Architecture

## 1. Purpose

This document records the MCP servers, agent-facing tools, retrieval
components, tool contracts, registry, and end-to-end flows implemented
so far for the Finzer AI ReAct platform.

The repository is intentionally split into two planes:

``` text
Finzer-AI-Agent/
├── ingestion_service/   # ingestion, analysis, embeddings, indexing, retrieval
└── ReAct_agent/         # MCP tools, RAG adapters, governance, future ReAct agent
```

The main architectural rule is:

> `ingestion_service` owns ingestion/indexing/retrieval logic, while
> `ReAct_agent` owns online agent orchestration and tool usage.

Existing ingestion logic is not duplicated inside the agent.

------------------------------------------------------------------------

## 2. High-Level Architecture

``` text
                         FINZER AI
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
      INGESTION / INDEXING          ONLINE / QUERY
           PLANE                       PLANE
     ingestion_service/             ReAct_agent/
               │                         │
               │                         ▼
               │                   Tool Registry
               │                     14 tools
               │                         │
               │       ┌─────────────────┼─────────────────┐
               │       │                 │                 │
               │       ▼                 ▼                 ▼
               │   Mutual Fund          Gold            Wishlist
               │      MCP               MCP               MCP
               │
               │                         +
               │
               │                Local RAG Tools
               │                 ┌──────┴──────┐
               │                 ▼             ▼
               │            Document RAG    News RAG
               │                 │             │
               └─────────────────┴──────┬──────┘
                                        ▼
                              PostgreSQL + pgvector
```

------------------------------------------------------------------------

# 3. MCP Foundation

Phase 1 established three MCP servers:

1.  Mutual Fund MCP
2.  Gold MCP
3.  Wishlist MCP

All MCP tools have typed contracts in the ReAct tool registry.

------------------------------------------------------------------------

## 3.1 Mutual Fund MCP

### Purpose

Provides read-only mutual fund information to the future ReAct agent.

### Provider

MFAPI:

``` text
https://api.mfapi.in
```

### MCP Tools

``` text
search_mutual_funds
get_mutual_fund_details
get_latest_nav
get_nav_history
```

### Responsibilities

#### `search_mutual_funds(query)`

Searches mutual fund schemes by name/query.

Example use:

``` text
User:
"Find SBI Small Cap Fund"

        ↓

search_mutual_funds("SBI Small Cap Fund")
```

#### `get_mutual_fund_details(scheme_code)`

Returns detailed scheme information for a known scheme code.

#### `get_latest_nav(scheme_code)`

Returns the latest available NAV.

A validated example during development used SBI Small Cap Fund Direct
Growth:

``` text
scheme_code = 125497
```

#### `get_nav_history(scheme_code, start_date, end_date)`

Returns locally filtered historical NAV observations within the
requested date range.

### Important behavior

Provider-side history filtering was not relied upon. The application
performs the requested date filtering locally to ensure the returned
observations respect the requested range.

### Files

``` text
ReAct_agent/app/mcp_servers/mutual_fund/
├── models.py
├── client.py
├── tools.py
└── server.py
```

Tests:

``` text
test_mutual_fund_tools.py
test_mutual_fund_mcp.py
```

### Status

``` text
Implementation      COMPLETE
Tool tests          PASSED
MCP protocol test   PASSED
Status              FROZEN
```

------------------------------------------------------------------------

# 3.2 Gold MCP

## Purpose

Provides current and historical gold-market information.

## Provider

GoldPrice.dev.

The API key is supplied through environment configuration and must never
be committed to source control.

``` text
GOLDPRICE_API_KEY
```

## MCP Tools

``` text
gold_spot_price
gold_carat_prices
gold_price_history
gold_conversion
```

### `gold_spot_price`

Returns the current spot price in a requested currency.

### `gold_carat_prices`

Returns per-gram gold prices for supported carat purities.

### `gold_price_history`

Returns historical OHLC observations for a date range and interval.

Provider plan restrictions are mapped into structured errors rather than
exposed as arbitrary HTTP exceptions.

### `gold_conversion`

Converts a quantity of gold into the requested supported target
representation/currency.

## Error Model

The client defines structured provider errors:

``` text
GoldPriceAPIError
GoldPriceAPITimeoutError
GoldPriceAPIAuthError
GoldPriceAPIPlanError
GoldPriceAPINotFoundError
GoldPriceAPIResponseError
```

## MCP server

All exposed tools use:

``` python
@mcp.tool(structured_output=False)
```

A critical Windows/subprocess detail is preserving the current
environment when launching the MCP server:

``` python
server_env = os.environ.copy()
```

## Files

``` text
ReAct_agent/app/mcp_servers/gold/
├── models.py
├── client.py
├── tools.py
└── server.py
```

Test:

``` text
test_gold_mcp.py
```

## Status

``` text
Implementation      COMPLETE
Provider calls       VERIFIED
MCP protocol test    PASSED
Status               FROZEN
```

------------------------------------------------------------------------

# 3.3 Wishlist MCP

## Purpose

Wishlist is the stateful user-interest component.

It is deliberately separate from financial information providers.

It supports:

``` text
wishlist_get
wishlist_check
wishlist_add
wishlist_remove
```

## Database Model

Conceptually:

``` text
wishlist_id
user_id
asset_type
asset_id
asset_name
metadata JSONB
created_at
updated_at
```

Uniqueness:

``` text
UNIQUE(user_id, asset_type, asset_id)
```

Supported asset types currently include:

``` text
MUTUAL_FUND
GOLD
```

## Operations

### `wishlist_get`

Returns the user's current wishlist.

### `wishlist_check`

Checks whether a particular asset is already present.

### `wishlist_add`

Adds an asset.

The database operation is concurrency-safe and idempotent using:

``` sql
ON CONFLICT DO NOTHING
```

### `wishlist_remove`

Removes an asset and is also designed to be idempotent.

## Error taxonomy

``` text
VALIDATION_ERROR
DATABASE_CONFIGURATION_ERROR
DATABASE_ERROR
INTERNAL_ERROR
```

## Approval semantics

Wishlist reads do not require approval.

Wishlist mutations are registered as:

``` text
operation = WRITE
approval  = CONDITIONAL
```

An explicit request such as:

``` text
"Add SBI Small Cap Fund to my wishlist"
```

may later be treated by the governance layer as direct authorization.

A statement such as:

``` text
"I like SBI Small Cap Fund"
```

must not automatically trigger a wishlist mutation.

## Files

``` text
ReAct_agent/app/mcp_servers/wishlist/
├── models.py
├── repository.py
├── tools.py
└── server.py
```

Tests:

``` text
test_wishlist_repository.py
test_wishlist_tools.py
test_wishlist_mcp.py
```

## Status

``` text
Repository tests     PASSED
Tool tests           14/14 PASSED
MCP protocol tests   13 cases PASSED
Status               FROZEN
```

------------------------------------------------------------------------

# 4. Tool Contracts

The central contract model is:

``` text
ReAct_agent/app/tools/contracts.py
```

## Enums

### ToolSource

``` text
MUTUAL_FUND
GOLD
WISHLIST
DOCUMENT_RAG
NEWS_RAG
```

### ToolOperation

``` text
READ
WRITE
```

### ToolRisk

``` text
LOW
MEDIUM
HIGH
```

### ApprovalPolicy

``` text
NEVER
CONDITIONAL
ALWAYS
```

### ToolTransport

``` text
MCP
LOCAL
```

## ToolContract

Each registered tool describes:

``` text
name
description
source
transport
server_name
operation
risk
approval
idempotent
timeout_seconds
max_retries
requires_user_context
returns_evidence
```

This contract becomes the foundation for the future execution gate.

The ReAct model will not be trusted to decide whether an operation is
safe. The execution/governance layer will inspect the registered
contract.

------------------------------------------------------------------------

# 5. Tool Registry

File:

``` text
ReAct_agent/app/tools/registry.py
```

The registry currently contains 14 tools.

``` text
Tool Registry
│
├── MUTUAL FUND MCP
│   ├── search_mutual_funds
│   ├── get_mutual_fund_details
│   ├── get_latest_nav
│   └── get_nav_history
│
├── GOLD MCP
│   ├── gold_spot_price
│   ├── gold_carat_prices
│   ├── gold_price_history
│   └── gold_conversion
│
├── WISHLIST MCP
│   ├── wishlist_get
│   ├── wishlist_check
│   ├── wishlist_add
│   └── wishlist_remove
│
├── DOCUMENT RAG
│   └── document_rag
│
└── NEWS RAG
    └── news_rag
```

## Registry counts

``` text
Total tools             14
READ tools              12
WRITE tools              2
Evidence tools          10
Approval-capable tools   2
```

The only write tools are:

``` text
wishlist_add
wishlist_remove
```

The only approval-capable tools are also:

``` text
wishlist_add
wishlist_remove
```

The four wishlist operations require user context.

Document RAG and News RAG are:

``` text
transport             LOCAL
operation             READ
risk                  LOW
approval              NEVER
requires_user_context False
returns_evidence      True
```

## Registry helper functions

``` text
get_tool_contract
require_tool_contract
tool_exists
list_tool_contracts
get_tools_by_source
get_read_tools
get_write_tools
get_tools_requiring_user_context
get_evidence_tools
get_approval_capable_tools
validate_tool_registry
```

## Validation rules

The registry validates important invariants including:

``` text
registry key == canonical tool name
MCP tools must define server_name
LOCAL tools must not define an MCP server
READ tools cannot require approval
ALWAYS approval only applies to WRITE operations
timeout must be positive
max_retries cannot be negative
```

## Tests

The combined Phase 2 registry test passed:

``` text
14 passed
```

------------------------------------------------------------------------

# 6. Document / IPO Retrieval

Document retrieval belongs to `ingestion_service`, not the ReAct agent.

## Indexed data

The document ingestion pipeline produces:

``` text
documents
document_chunks
document_chunk_embeddings
```

The validated document flow included a real Hi-Tech Flow Solutions
Limited IPO/DRHP document.

The pipeline processed:

``` text
17 pages
313 extracted elements
30 chunks
30 persisted embeddings
1024 embedding dimensions
```

## Retriever

File:

``` text
ingestion_service/app/retrieval/document_retriever.py
```

Interface:

``` python
retrieve(
    query: str,
    *,
    document_key: str,
    top_k: int = 5,
)
```

## Retrieval flow

``` text
User query
    │
    ▼
EmbeddingRouter
    │
    ▼
Query embedding
    │
    ▼
document_chunk_embeddings
    │
    ├── document_key filter
    ├── embedding provider filter
    ├── embedding model filter
    ├── embedding dimension filter
    └── cosine similarity
    │
    ▼
Ranked document chunks
```

Provider/model/dimension filtering prevents incompatible vector spaces
from being compared.

------------------------------------------------------------------------

# 7. Document Context Builder

File:

``` text
ingestion_service/app/retrieval/context_builder.py
```

The context builder converts ranked document chunks into bounded RAG
context.

Output concept:

``` text
BuiltContext
├── context
├── sources
├── source_count
└── total_tokens
```

Responsibilities include:

``` text
preserve retrieval rank
deduplicate chunk IDs
enforce context token budget
retain source metadata
construct grounded context
```

This component is specific to document RAG.

It must not be confused with the future ReAct Agent Context Manager.

------------------------------------------------------------------------

# 8. Document RAG Bridge

File:

``` text
ingestion_service/app/retrieval/document_rag_bridge.py
```

The bridge provides a clean process boundary between:

``` text
ReAct_agent
      │
      ▼
ingestion_service
```

Flow:

``` text
ReAct Document RAG Tool
        │
        ▼
Document RAG Backend
        │
        │ subprocess
        ▼
document_rag_bridge
        │
        ▼
DocumentRetriever
        │
        ▼
DocumentContextBuilder
        │
        ▼
PostgreSQL + pgvector
```

The ReAct agent therefore does not copy retrieval SQL or ingestion
internals.

------------------------------------------------------------------------

# 9. ReAct Document RAG Adapter

Files:

``` text
ReAct_agent/app/tools/document_rag.py
ReAct_agent/app/tools/document_rag_backend.py
```

## Agent-facing input

Conceptually:

``` text
query
document_key
top_k
max_context_tokens
```

## Error behavior

Validation errors are non-retryable:

``` text
VALIDATION_ERROR
retryable = false
```

Retrieval/infrastructure failures are represented as:

``` text
RETRIEVAL_ERROR
retryable = true
```

## Windows UTF-8 boundary

The backend explicitly sets:

``` text
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
```

and launches the child process with UTF-8 decoding.

This prevents Unicode corruption for financial documents containing
characters such as the Indian rupee symbol and non-ASCII text.

## E2E result

The Document RAG test suite passed:

``` text
4 passed
```

The real retrieval test returned the expected "Objects of the Offer"
section as the top result.

## Status

``` text
Document Retriever       COMPLETE
Context Builder           COMPLETE
Bridge                    COMPLETE
ReAct backend             COMPLETE
Agent-facing tool         COMPLETE
E2E                       PASSED
Status                    FROZEN
```

------------------------------------------------------------------------

# 10. News Ingestion Representation

The article ingestion pipeline stores analyzed financial-news
information.

Important article analysis fields include:

``` text
is_valid_article
relevance_score
is_relevant
relevance_reason
summary
key_facts
companies_mentioned
market_impact
llm_analysis
analyzed_at
processing_status
```

The article embedding worker intentionally does not embed the entire raw
article.

The semantic representation is built from:

``` text
Title
Summary
Key Facts
Market Impact
```

This keeps retrieval focused on the analyzed financial meaning of the
article.

------------------------------------------------------------------------

# 11. News Embeddings

Embeddings are stored in:

``` text
article_embeddings
```

with:

``` text
article_key
embedding
embedding_model
embedding_provider
embedding_dimension
embedded_at
```

The validated environment contained:

``` text
Provider:   openai
Model:      text-embedding-3-small
Dimension:  1024
```

The retrieval layer requires the query embedding
provider/model/dimension to match the indexed vectors.

------------------------------------------------------------------------

# 12. News Retriever

File:

``` text
ingestion_service/app/retrieval/news_retriever.py
```

Interface:

``` python
retrieve(
    query: str,
    *,
    top_k: int = 5,
    company: str | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
)
```

## Retrieval flow

``` text
Natural-language query
        │
        ▼
EmbeddingRouter
        │
        ▼
Query embedding
        │
        ▼
article_embeddings
        │
        ├── provider
        ├── model
        ├── dimension
        ├── processing_status=embedded
        ├── optional company filter
        └── optional publication bounds
        │
        ▼
Cosine similarity
        │
        ▼
Ranked financial-news evidence
```

## Returned evidence

Each result can include:

``` text
retrieval_rank
article_key
title
url
source
authors
published_at
summary
key_facts
companies_mentioned
market_impact
relevance_score
relevance_reason
embedding_provider
embedding_model
embedding_dimension
embedded_at
similarity
```

## Real semantic tests

Two real indexed articles were used during validation.

### HDFC query

Query:

``` text
HDFC Bank share price outlook and analyst target
```

Top result:

``` text
HDFC Bank article
similarity ≈ 0.7083
```

The unrelated Apple Pay article ranked second at approximately:

``` text
0.3332
```

### Apple Pay query

Query:

``` text
Apple Pay launch in India
```

Top result:

``` text
Apple Pay article
similarity ≈ 0.7506
```

The HDFC article ranked second at approximately:

``` text
0.2779
```

This demonstrated meaningful semantic ranking even with the small
two-article test corpus.

------------------------------------------------------------------------

# 13. News Metadata Filtering

News retrieval supports structured filtering in addition to semantic
similarity.

## Company filter

Example:

``` text
company = "Visa"
```

returned only the indexed Apple Pay article that included Visa in
`companies_mentioned`.

Example:

``` text
company = "HDFC Bank"
```

returned both indexed articles because both contained HDFC Bank in their
analyzed company metadata.

## Publication filters

Supported:

``` text
published_after
published_before
```

These allow the future agent to constrain retrieval to a relevant time
window.

Example future request:

``` text
"What is the latest news about HDFC Bank?"
```

can eventually be translated into:

``` text
query           = "HDFC Bank latest financial developments"
company         = "HDFC Bank"
published_after = <resolved freshness window>
top_k           = 5
```

Freshness policy itself will belong to the later
evidence-validation/context layer rather than being hard-coded into the
retriever.

------------------------------------------------------------------------

# 14. News RAG Bridge

File:

``` text
ingestion_service/app/retrieval/news_rag_bridge.py
```

Responsibilities:

``` text
parse CLI inputs
validate date range
call NewsRetriever
return structured JSON
```

Supported bridge inputs:

``` text
query
top_k
company
published_after
published_before
```

The bridge is intentionally thin.

It does not duplicate retrieval SQL.

------------------------------------------------------------------------

# 15. ReAct News RAG Backend

File:

``` text
ReAct_agent/app/tools/news_rag_backend.py
```

Flow:

``` text
ReAct_agent
     │
     ▼
IngestionNewsRAGBackend
     │
     │ subprocess
     ▼
ingestion_service
     │
     ▼
news_rag_bridge
```

The backend preserves the environment so database and embedding-provider
configuration remain available.

It also forces UTF-8:

``` text
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
```

The backend parses the final valid JSON line because the embedding
router may emit provider-selection diagnostic output before the bridge
response.

------------------------------------------------------------------------

# 16. Agent-Facing News RAG Tool

File:

``` text
ReAct_agent/app/tools/news_rag.py
```

The tool separates argument validation from retrieval implementation.

Conceptual flow:

``` text
Agent arguments
      │
      ▼
NewsRAGInput
      │
      ▼
Validation
      │
      ▼
NewsRAGBackend
      │
      ▼
NewsRAGResult
      │
      ▼
Structured observation
```

The agent-facing layer knows nothing about:

``` text
PostgreSQL
pgvector SQL
EmbeddingRouter internals
subprocess implementation
article indexing
```

That separation is intentional.

------------------------------------------------------------------------

# 17. News RAG E2E Tests

The complete real path was tested:

``` text
NewsRAGTool
    │
    ▼
IngestionNewsRAGBackend
    │
    ▼
UTF-8 subprocess
    │
    ▼
news_rag_bridge
    │
    ▼
NewsRetriever
    │
    ▼
EmbeddingRouter
    │
    ▼
OpenAI query embedding
    │
    ▼
PostgreSQL + pgvector
```

Tests covered:

``` text
Apple Pay semantic retrieval
HDFC semantic retrieval
Visa company filter
HDFC Bank company filter
publication date filtering
future-date empty results
invalid date ranges
empty query validation
empty company validation
Unicode subprocess regression
```

Result:

``` text
10 passed
```

## Status

``` text
News Retriever           COMPLETE
News RAG Bridge          COMPLETE
ReAct backend             COMPLETE
Agent-facing tool         COMPLETE
E2E                       10/10 PASSED
Status                    FROZEN
```

------------------------------------------------------------------------

# 18. Complete Tool / Retrieval Architecture

``` text
                              USER
                               │
                               ▼
                     ┌──────────────────┐
                     │ Future ReAct     │
                     │ Agent            │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ Tool Registry    │
                     │ 14 contracts     │
                     └────────┬─────────┘
                              │
          ┌───────────────────┼─────────────────────┐
          │                   │                     │
          ▼                   ▼                     ▼
       MCP Tools          Local RAG             Governance
          │                   │                  metadata
   ┌──────┼──────┐      ┌─────┴─────┐
   ▼      ▼      ▼      ▼           ▼
 Mutual  Gold  Wishlist Document    News
 Fund    MCP    MCP       RAG       RAG
 MCP                       │         │
                           ▼         ▼
                      RAG Backends
                           │
                           │ subprocess boundary
                           ▼
                 ┌──────────────────────┐
                 │ ingestion_service    │
                 └──────────┬───────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
        DocumentRetriever          NewsRetriever
                │                       │
        ContextBuilder                  │
                │                       │
                └───────────┬───────────┘
                            ▼
                   EmbeddingRouter
                            │
                            ▼
                 PostgreSQL + pgvector
```

------------------------------------------------------------------------

# 19. Why MCP and RAG Are Different

MCP tools represent callable capabilities/services.

Examples:

``` text
get_latest_nav
gold_spot_price
wishlist_add
```

RAG tools represent retrieval over Finzer's indexed knowledge.

Examples:

``` text
document_rag
news_rag
```

Both appear uniformly to the future agent through `ToolContract`, but
their transports differ:

``` text
Mutual Fund   MCP
Gold          MCP
Wishlist      MCP
Document RAG  LOCAL
News RAG      LOCAL
```

This lets the future ReAct agent reason about tools without depending on
their underlying implementation.

------------------------------------------------------------------------

# 20. Evidence-Producing Tools

Evidence-producing tools currently include:

``` text
Mutual Fund tools    4
Gold tools           4
Document RAG         1
News RAG             1
───────────────────────
Total               10
```

Wishlist tools are state-management operations and therefore use:

``` text
returns_evidence = False
```

This distinction will feed directly into the future Evidence Validator.

------------------------------------------------------------------------

# 21. Planned Execution Governance

The future execution path is:

``` text
ReAct Agent
     │
     ▼
Structured Tool Call
     │
     ▼
Execution Gate
     │
     ├── tool exists?
     ├── arguments valid?
     ├── permission allowed?
     ├── within step budget?
     ├── within tool-call budget?
     ├── duplicate call?
     ├── timeout?
     ├── retry policy?
     └── approval required?
     │
     ▼
Tool Executor
     │
     ▼
MCP / RAG
     │
     ▼
Structured Observation
```

Suggested initial limits:

``` text
MAX_AGENT_STEPS      = 8
MAX_TOOL_CALLS       = 6
MAX_RETRIES_PER_TOOL = 2
```

These limits have not yet been implemented and belong to later
governance phases.

------------------------------------------------------------------------

# 22. Planned HITL / Approval Flow

``` text
Tool selected
     │
     ▼
Execution Gate
     │
     ▼
Approval required?
   ┌─┴─┐
   │   │
  NO  YES
   │   │
   │   ▼
   │  Ask User
   │   │
   │ ┌─┴──────┐
   │ │        │
   │approved denied
   │ │        │
   └─┘        ▼
    │    structured observation
    ▼
 Execute
```

Read-only financial retrieval normally requires no approval.

Wishlist mutations use conditional approval semantics.

------------------------------------------------------------------------

# 23. Planned Agent State

The next implementation phase is the agent foundation.

Conceptual `AgentState`:

``` text
AgentState
│
├── run_id
├── user_id
├── user_query
│
├── messages
├── conversation_summary
├── active_entities[]
│
├── intent
├── next_action
├── pending_tool_call
│
├── observations[]
├── evidence[]
├── errors[]
│
├── approval
│
├── step_count
├── tool_call_count
│
├── evidence_validation
└── final_answer
```

`AgentState` represents what is happening during an agent run.

It should not itself perform retrieval or execute tools.

------------------------------------------------------------------------

# 24. Planned Context Manager

The Context Manager will answer:

> What does the user's current message mean given the conversation?

Responsibilities are expected to include:

``` text
prepare_context()
resolve_references()
select_recent_messages()
select_relevant_observations()
maintain_active_entities()
enforce_context_budget()
```

Example:

``` text
User:
"Tell me about SBI Small Cap Fund."

        ↓

Resolved entity:
SBI Small Cap Fund
scheme_code = 125497

        ↓

User:
"What is its latest NAV?"

        ↓

Context Manager:
"its" → SBI Small Cap Fund → scheme_code 125497
```

The Context Manager should not choose the tool.

The ReAct agent decides what action to take.

------------------------------------------------------------------------

# 25. Planned Entity Tracking

Expected entity types include:

``` text
MUTUAL_FUND
GOLD
COMPANY
IPO_DOCUMENT
NEWS_TOPIC
```

Potential future types:

``` text
STOCK
ETF
INDEX
```

Example:

``` text
ResolvedEntity
├── entity_type = MUTUAL_FUND
├── name = SBI Small Cap Fund
├── canonical_id = 125497
└── metadata
```

For IPO documents, entity resolution will hide raw document hashes from
the reasoning model whenever possible.

Instead of requiring the model to know:

``` text
3adccc083d26e3b574fb187d92c87e80...
```

the intended flow is:

``` text
"Hi-Tech Flow Solutions"
        │
        ▼
Entity Resolver
        │
        ▼
document_key
        │
        ▼
document_rag
```

------------------------------------------------------------------------

# 26. Planned ReAct Loop

``` text
START
  │
  ▼
Prepare Context
  │
  ▼
ReAct Agent ◄─────────────────────────────┐
  │                                       │
  ▼                                       │
Next Action?                              │
  │                                       │
  ├── TOOL                                │
  │     │                                 │
  │     ▼                                 │
  │ Execution Gate                        │
  │     │                                 │
  │ Approval?                             │
  │   ┌─┴─┐                               │
  │   │   │                               │
  │  NO  YES                              │
  │   │   │                               │
  │   │   ▼                               │
  │   │ Ask User                          │
  │   │   │                               │
  │   └───┴──► Execute Tool               │
  │               │                       │
  │               ▼                       │
  │          Observation                  │
  │               │                       │
  │               └───────────────────────┘
  │
  ├── CLARIFY
  │      │
  │      ▼
  │   Ask User
  │
  └── ANSWER
         │
         ▼
   Evidence Validator
       │       │
      FAIL    PASS
       │       │
       └───────┤
               ▼
       Response Composer
               │
               ▼
             FINAL
```

------------------------------------------------------------------------

# 27. Evidence vs Observation

These concepts are intentionally separate.

## Observation

Describes what happened during a tool call.

Example:

``` text
tool_name = news_rag
status    = success
data      = 5 retrieved articles
```

## Evidence

Represents information that may support the final answer.

Example:

``` text
title
source
published_at
summary
similarity
```

This separation enables a later Evidence Validator to check:

``` text
freshness
entity match
source availability
completeness
conflicts
grounding
```

before the Response Composer generates the final answer.

------------------------------------------------------------------------

# 28. Current Implementation Status

``` text
PHASE 1 — MCP FOUNDATION                 COMPLETE / FROZEN

1.1 Mutual Fund MCP                     COMPLETE
1.2 Gold MCP                            COMPLETE
1.3 Wishlist MCP                        COMPLETE
1.4 Tool contracts/tests                COMPLETE


PHASE 2 — RAG TOOLS                      COMPLETE / FROZEN

2.1 Document / IPO RAG                  COMPLETE
2.2 News RAG                            COMPLETE
2.3 RAG registry integration            COMPLETE
2.4 Registry consistency tests          COMPLETE


PHASE 3 — AGENT FOUNDATION               NEXT

3.1 AgentState                          PENDING
3.2 Context Manager                     PENDING
3.3 Entity/context tracking             PENDING


PHASE 4 — REACT                          PENDING

4.1 ReAct node
4.2 Next-action router
4.3 Tool executor
4.4 Observation loop
4.5 Clarification route


PHASE 5 — GOVERNANCE                     PENDING

5.1 Execution gate
5.2 Permissions
5.3 Budgets / limits
5.4 Approval / HITL
5.5 Pause / resume


PHASE 6 — ANSWERING                      PENDING

6.1 Evidence validator
6.2 Freshness checks
6.3 Response composer
6.4 Citations / timestamps


PHASE 7 — PRODUCTION                     PENDING

7.1 E2E tests
7.2 Failure tests
7.3 Agent evaluation
7.4 Tracing / observability
7.5 Performance / cost controls
```

------------------------------------------------------------------------

# 29. Validated Test Summary

``` text
Mutual Fund MCP
    Tool + protocol validation           PASSED

Gold MCP
    Provider + protocol validation       PASSED

Wishlist MCP
    Tool tests                           14/14 PASSED
    Protocol scenarios                   13 PASSED

Document RAG
    E2E tests                            4/4 PASSED

News RAG
    E2E tests                            10/10 PASSED

Combined Phase 2 Tool Registry
    Registry tests                       14/14 PASSED
```

------------------------------------------------------------------------

# 30. Key Architectural Decisions

## Decision 1 --- Separate ingestion and agent planes

``` text
ingestion_service
```

owns ingestion, indexing and retrieval.

``` text
ReAct_agent
```

owns online reasoning and orchestration.

## Decision 2 --- Do not duplicate retrieval

ReAct accesses ingestion retrieval through thin bridges/backends.

## Decision 3 --- Uniform tool contracts

MCP and local RAG tools use the same governance metadata through
`ToolContract`.

## Decision 4 --- Read operations require no approval

Current read-only financial/RAG operations use:

``` text
ApprovalPolicy.NEVER
```

## Decision 5 --- Mutations are explicit

Only wishlist add/remove are currently write operations.

## Decision 6 --- Evidence is first-class

Financial provider tools and RAG tools are explicitly marked as
evidence-producing.

## Decision 7 --- Provider/model/dimension must match

Vector retrieval only compares compatible embeddings.

## Decision 8 --- Preserve Unicode across process boundaries

RAG subprocess adapters force UTF-8 to support Indian financial text and
non-ASCII characters.

## Decision 9 --- Keep raw infrastructure away from the agent

The reasoning model should not need to understand:

``` text
SQL
pgvector internals
RabbitMQ
embedding persistence
subprocess implementation
raw document hashes where entity resolution can hide them
```

## Decision 10 --- Build and freeze one layer at a time

The implementation process is:

``` text
build
  ↓
compile
  ↓
real functional test
  ↓
E2E test
  ↓
freeze
  ↓
next component
```

------------------------------------------------------------------------

# 31. Current Repository Shape

``` text
Finzer-AI-Agent/
│
├── ingestion_service/
│   │
│   └── app/
│       ├── retrieval/
│       │   ├── document_retriever.py
│       │   ├── context_builder.py
│       │   ├── document_rag_bridge.py
│       │   ├── news_retriever.py
│       │   └── news_rag_bridge.py
│       │
│       ├── workers/
│       │   ├── article_processing_worker.py
│       │   └── article_embedding_worker.py
│       │
│       ├── repositories/
│       │   └── article_repository.py
│       │
│       └── clients/
│           └── embedding_router.py
│
└── ReAct_agent/
    │
    ├── app/
    │   │
    │   ├── mcp_servers/
    │   │   ├── mutual_fund/
    │   │   ├── gold/
    │   │   └── wishlist/
    │   │
    │   └── tools/
    │       ├── contracts.py
    │       ├── registry.py
    │       ├── document_rag.py
    │       ├── document_rag_backend.py
    │       ├── news_rag.py
    │       └── news_rag_backend.py
    │
    ├── test_document_rag_e2e.py
    ├── test_news_rag_e2e.py
    └── test_create_tool_registry_phase_2.py
```

The future agent directories will extend this with:

``` text
app/
├── agent/
│   ├── state.py
│   ├── context.py
│   ├── react.py
│   ├── router.py
│   └── graph.py
│
├── governance/
│   ├── execution_gate.py
│   └── approval.py
│
└── response/
    ├── evidence_validator.py
    └── composer.py
```

------------------------------------------------------------------------

# 32. Next Step

The next implementation phase is:

``` text
PHASE 3 — AGENT FOUNDATION
```

Starting with:

``` text
3.1 AgentState
```

followed by:

``` text
3.2 Context Manager
3.3 Entity/context tracking
```

The intended separation is:

``` text
Context Manager
    "What does the user mean?"

AgentState
    "What is happening in this run?"

ReAct Agent
    "What should I do next?"

Tool Registry / Execution Gate
    "Is this action valid and permitted?"

Tool Executor
    "Perform the action."

Evidence Validator
    "Do I have enough trustworthy evidence?"

Response Composer
    "How should the grounded answer be presented?"
```

This boundary should remain stable as the ReAct implementation is added.
