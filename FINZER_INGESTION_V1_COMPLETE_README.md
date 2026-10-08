# Finzer AI --- Ingestion Pipeline v1

> **Status:** Complete and E2E validated\
> **Scope:** News ingestion and IPO/document ingestion through persisted
> 1024-dimensional embeddings.\
> **Out of scope:** RAG generation, reranking, agents, chat/API/UI.

## 1. Architecture

### News

``` text
NewsData.io / configured feeds
→ discovery + extraction + normalization + deduplication
→ PostgreSQL
→ RabbitMQ: article.processing
→ LLM analysis + application relevance threshold
→ RabbitMQ: article.embedding
→ Embedding Router
→ PostgreSQL + pgvector
```

### IPO / documents

``` text
SEBI / local PDF / future providers
→ discovery
→ PDF download + validation
→ PyMuPDF structured parsing
→ pdfplumber table extraction
→ style profiling + TOC detection
→ structure/heading detection
→ hierarchy assignment
→ table validation
→ section-aware hybrid chunking
→ PostgreSQL
→ RabbitMQ: document.embedding
→ Document Embedding Worker
→ Embedding Router
→ PostgreSQL + pgvector
```

Core rules:

-   Preserve document structure before chunking.
-   Native PyMuPDF text is authoritative; extracted tables are
    supplementary.
-   Deterministic PDF processing is synchronous in v1; expensive
    embedding is asynchronous.
-   Store content and embeddings separately.
-   Never mix incompatible embedding spaces in one searchable index.
-   ACK RabbitMQ work only after successful persistence.
-   Keep credentials only in local environment configuration.

## 2. Local infrastructure

  Component                  Location       Purpose
  -------------------------- -------------- ------------------------------
  Python ingestion service   Local          Pipeline logic
  PostgreSQL                 Docker/local   Persistent data
  pgvector                   PostgreSQL     Vector storage
  RabbitMQ                   Docker/local   Queues/retries/DLQ
  Bedrock                    AWS            Configured AI provider
  OpenAI                     Cloud          Generator/embedding fallback

Validated local services:

``` text
PostgreSQL: 127.0.0.1:5433 / database finzer / user finzer
Container:  finzer-postgres-local

RabbitMQ:   AMQP 5672 / Management 15672 / vhost /finzer
Container:  finzer-rabbitmq-local
```

Do not put PostgreSQL passwords, RabbitMQ passwords, OpenAI keys, AWS
credentials, or news API keys in this README or source control.

## 3. Important project files

``` text
ingestion_service/
├── app/
│   ├── config/
│   │   └── settings.py
│   ├── clients/
│   │   ├── bedrock_llm_client.py
│   │   ├── openai_llm_client.py
│   │   ├── llm_router.py
│   │   ├── bedrock_embedding_client.py
│   │   ├── openai_embedding_client.py
│   │   └── embedding_router.py
│   ├── repositories/
│   │   ├── database.py
│   │   ├── article_repository.py
│   │   └── document_repository.py
│   ├── queue/
│   │   ├── queue_topology.py
│   │   ├── queue_publisher.py
│   │   └── retry_router.py
│   ├── workers/
│   │   ├── article_processing_worker.py
│   │   ├── article_embedding_worker.py
│   │   └── document_embedding_worker.py
│   ├── document_ingestion/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── downloader.py
│   │   ├── parser.py
│   │   ├── table_extractor.py
│   │   ├── chunker.py
│   │   ├── service.py
│   │   ├── embedding_publisher.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── sebi.py
│   │   ├── structure/
│   │   │   ├── __init__.py
│   │   │   ├── style_profiler.py
│   │   │   ├── toc_detector.py
│   │   │   ├── structure_detector.py
│   │   │   └── hierarchy_assigner.py
│   │   └── tables/
│   │       ├── __init__.py
│   │       └── table_validator.py
│   ├── db/migrations/
│   │   └── 002_create_document_tables.sql
│   └── main.py
├── data/documents/raw/
│   └── HitechFlowSolutionsDAP_p.pdf
├── local.env
├── requirements.txt
├── run_doc_migration_table.py
├── check_postgres_db.py
├── test_real_document_ingestion.py
├── run_document_embedding_publish.py
├── verify_document_embedding.py
├── test_document_retrieval.py
├── test_document_retrieval_quality.py
└── test_document_context.py
```

The last three retrieval/context files validate the output of ingestion;
RAG itself is a separate phase.

## 4. Shared infrastructure files

### `app/config/settings.py`

Loads `local.env` and centralizes DB, RabbitMQ, queue, provider, model
and embedding-dimension configuration.

Representative non-secret settings:

``` env
DATABASE_URL=postgresql://finzer:<PASSWORD>@127.0.0.1:5433/finzer
GENERATOR_PROVIDER=auto
GENERATOR_PRIMARY=bedrock
GENERATOR_FALLBACK=openai
EMBEDDING_PROVIDER=auto
EMBEDDING_PRIMARY=bedrock
EMBEDDING_FALLBACK=openai
EMBEDDING_DIMENSION=1024
```

Use the actual variable names in the current `settings.py` for
credentials/model IDs.

### `app/repositories/database.py`

Low-level psycopg connection helper. `execute()` performs a query but is
not the general row-fetch API. For reads:

``` python
with db.connect() as connection:
    with connection.cursor() as cursor:
        cursor.execute(...)
        rows = cursor.fetchall()
```

### `app/queue/queue_topology.py`

Declares durable main/retry/DLQ queues and TTL/dead-letter behavior.

### `app/queue/queue_publisher.py`

Generic persistent JSON publisher reused by news and document paths.

### `app/queue/retry_router.py`

Routes failed work through retry queues and eventually DLQ.

Validated retry intervals:

``` text
retry.1 = 30 seconds
retry.2 = 120 seconds
retry.3 = 600 seconds
then → DLQ
```

## 5. AI clients

### `bedrock_llm_client.py`

Amazon Bedrock generator implementation used through `LLMRouter`.

### `openai_llm_client.py`

OpenAI generator/fallback implementation.

### `llm_router.py`

Decouples workers from one generator provider:

``` text
worker → LLMRouter → Bedrock / OpenAI fallback
```

### `bedrock_embedding_client.py`

Bedrock embedding implementation. During final local document validation
its provider probe failed authorization.

### `openai_embedding_client.py`

OpenAI embedding implementation. Final document validation used
`text-embedding-3-small` at 1024 dimensions.

### `embedding_router.py`

Probes providers and locks one provider/model for the worker session.
Final document run:

``` text
Bedrock unavailable
→ OpenAI available
→ lock openai / text-embedding-3-small / 1024
```

Do not switch embedding spaces halfway through one index.

## 6. Document ingestion files

### `models.py`

Defines pipeline contracts including `DiscoveredDocument`,
`DownloadedDocument`, `BoundingBox`, `DocumentElement`,
`ExtractedTable`, `ParsedDocument`, and `DocumentChunk`. Element types
include heading/paragraph/table; chunk types include text/table.

### `providers/base.py`

Source-provider abstraction. It allows SEBI today and NSE/BSE/company IR
later without rewriting downstream parsing.

### `providers/sebi.py`

SEBI discovery implementation. Returns source-independent
discovered-document metadata. Some SEBI records may not have direct PDF
URLs; a filing-page resolver can be added later without changing
downstream processing.

### `downloader.py`

Downloads and validates PDFs and records file path/name/size/SHA-256.
SHA-256 helps identify duplicate or changed source files.

### `parser.py`

Primary PyMuPDF parser. Uses structured extraction such as
`page.get_text("dict", sort=True)` to preserve pages, blocks/spans,
coordinates, font size/name, boldness and layout signals. The validated
17-page PDF produced 313 logical elements.

### `table_extractor.py`

Uses pdfplumber to discover table candidates while leaving authoritative
text intact. The validated PDF produced 15 candidates.

### `structure/style_profiler.py`

Profiles dominant body typography and relative styles. Heading detection
is therefore relative to each document rather than one hardcoded font
size.

### `structure/toc_detector.py`

Looks for a usable TOC in early pages. The validated sample had no
usable TOC; processing correctly continued.

### `structure/structure_detector.py`

Detects physical headings/structure using font/style, boldness,
numbering, standalone/short lines, capitalization, whitespace/layout,
TOC evidence and table vetoes. It preserves original headings rather
than forcing a fixed IPO taxonomy.

### `structure/hierarchy_assigner.py`

Assigns section/subsection/heading context and lets paragraphs inherit
hierarchy. Validated patterns include top-level numeric → section,
alphabetic → subsection, nested numeric/Roman → heading.

### `tables/table_validator.py`

Rejects false/over-broad table candidates before table chunks are
created. Validated sample: 15 candidates → 7 accepted, 8 rejected.

### `chunker.py`

Creates retrieval-ready chunks while preserving hierarchy and page
metadata.

Validated v1 configuration:

``` text
target = 800 tokens
max    = 1000 tokens
overlap = 100 tokens
tokenizer = cl100k_base
```

Large text sections are split only when necessary. Large tables split by
rows and repeat headers. Validated result:

``` text
30 total chunks
23 text
7 table
max chunk = 943 tokens
chunks > 1000 = 0
```

### `service.py`

Synchronous document orchestrator:

``` text
discover/upsert
→ download/local DownloadedDocument
→ parse
→ extract tables
→ style profile
→ TOC
→ structure
→ hierarchy
→ chunk
→ persist
```

It updates document statuses and failure state but does not embed
directly.

### `embedding_publisher.py`

Loads all chunks for a `document_key`, publishes `{"chunk_id": ...}` to
`document.embedding`, and marks the document as embedding. The worker
reloads authoritative content from PostgreSQL.

## 7. Document repository

### `app/repositories/document_repository.py`

Important operations:

``` text
upsert_discovered_document
get_by_key
get_document_id
update_status
save_downloaded_document
replace_chunks
get_chunk
get_chunks_for_document
get_embedding_input
get_chunks_pending_embedding
has_embedding
save_embedding
mark_document_embedding
mark_document_embedded_if_complete
```

Important guarantees:

-   chunk replacement removes stale dependent embeddings through
    FK/cascade behavior;
-   embedding identity is exact `chunk_id + provider + model`;
-   1024-dimensional vectors are validated before persistence;
-   document status becomes `embedded` only when every chunk has the
    expected provider/model embedding.

## 8. Document embedding worker

### `app/workers/document_embedding_worker.py`

Consumes:

``` text
document.embedding
```

Message:

``` json
{"chunk_id": 123}
```

Flow:

``` text
message
→ load chunk
→ exact provider/model duplicate check
→ EmbeddingRouter
→ generate vector
→ validate 1024 dimensions
→ save embedding
→ check document completeness
→ status embedded when complete
→ ACK
```

On failure it routes through document retry queues and eventually DLQ.

## 9. Document database schema

Migration:

``` text
app/db/migrations/002_create_document_tables.sql
```

### `documents`

Key fields:

``` text
document_id, document_key, source, company_name, document_type,
source_title, filing_url, pdf_url, file_name, file_sha256,
file_size_bytes, published_at, status, metadata, created_at, updated_at
```

Status lifecycle:

``` text
discovered → downloading → downloaded → parsing → parsed
→ chunked → embedding → embedded
```

Any stage may become `failed`.

### `document_chunks`

``` text
chunk_id, document_id, chunk_index, content_type, content,
page_start, page_end, section, subsection, heading,
token_count, metadata, created_at
```

Unique logical position: `(document_id, chunk_index)`.

### `document_chunk_embeddings`

``` text
embedding_id, chunk_id, provider, model, dimension,
embedding VECTOR(1024), created_at
```

Unique embedding identity: `(chunk_id, provider, model)`.

No HNSW/IVFFlat index is required for the initial 30-chunk corpus. Add
ANN indexing when corpus size warrants it.

## 10. RabbitMQ document queues

There is intentionally no `document.processing` queue in v1.
Parsing/structure/chunking are synchronous.

``` text
document.embedding
document.embedding.retry.1
document.embedding.retry.2
document.embedding.retry.3
document.embedding.dlq
```

## 11. News ingestion files

### `app/main.py`

News ingestion entry point. Example:

``` powershell
python -m app.main --feed-id company_infosys
```

It discovers/extracts/normalizes/deduplicates articles, persists them
and publishes `article.processing`.

### `article_repository.py`

Article persistence, status and embedding data access.

### `article_processing_worker.py`

Consumes `article.processing`, runs structured LLM analysis and applies
the application relevance threshold:

``` text
score >= 0.65 → analyzed → article.embedding
score < 0.65  → irrelevant
```

The application threshold is authoritative rather than only the model's
`is_relevant` flag.

### `article_embedding_worker.py`

Consumes `article.embedding`, builds embedding input, uses
`EmbeddingRouter`, saves the vector and marks the article embedded.

News queues:

``` text
article.processing
article.processing.retry.1
article.processing.retry.2
article.processing.retry.3
article.processing.dlq
article.embedding
article.embedding.retry.1
article.embedding.retry.2
article.embedding.retry.3
article.embedding.dlq
```

## 12. Setup commands

From PowerShell:

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
```

Start/check Docker:

``` powershell
docker ps
docker start finzer-postgres-local
docker start finzer-rabbitmq-local
docker ps
```

PostgreSQL shell:

``` powershell
docker exec -it finzer-postgres-local psql -U finzer -d finzer
```

Check pgvector:

``` sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
```

RabbitMQ queues:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

Retry arguments:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name arguments
```

Connections:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_connections user vhost peer_host state
```

## 13. First-time document DB migration

For a fresh DB:

``` powershell
python .\run_doc_migration_table.py
python .\check_postgres_db.py
```

Manual verification:

``` powershell
docker exec -it finzer-postgres-local psql -U finzer -d finzer
```

``` sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'documents',
    'document_chunks',
    'document_chunk_embeddings'
  )
ORDER BY table_name;
```

## 14. Run the full IPO/document ingestion pipeline

Use separate terminals.

### Terminal 1 --- embedding worker

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.document_embedding_worker
```

Leave it running.

### Terminal 2 --- ingest real PDF

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python .\test_real_document_ingestion.py
```

Despite the `test_` name, this is the validated local real-PDF ingestion
runner used for v1.

Expected high-level state:

``` text
PDF → parsed → tables/structure/hierarchy → chunks
→ PostgreSQL → status chunked
```

### Terminal 2 --- publish chunks

``` powershell
python .\run_document_embedding_publish.py
```

Watch Terminal 1 consume `document.embedding`.

### Terminal 2 --- verify final embeddings

``` powershell
python -m py_compile .\verify_document_embedding.py
python .\verify_document_embedding.py
```

Validated expected result:

``` text
document_status           = embedded
provider                  = openai
model                     = text-embedding-3-small
expected_dimension        = 1024
total_chunks              = 30
embedded_chunks           = 30
missing_embeddings        = 0
valid_dimension_chunks    = 30
invalid_dimension_chunks  = 0

FULL DOCUMENT EMBEDDING VERIFICATION PASSED
```

### Short document run checklist

Infrastructure:

``` powershell
docker start finzer-postgres-local
docker start finzer-rabbitmq-local
docker ps
```

Worker terminal:

``` powershell
python -m app.workers.document_embedding_worker
```

Ingestion/admin terminal:

``` powershell
python .\test_real_document_ingestion.py
python .\run_document_embedding_publish.py
python .\verify_document_embedding.py
```

## 15. Run the full news ingestion pipeline

### Terminal 1 --- processing

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_processing_worker
```

### Terminal 2 --- embedding

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_embedding_worker
```

### Terminal 3 --- ingestion

``` powershell
cd C:\Users\paltu\Finzer-AI-Agent\ingestion_service
C:\Users\paltu\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.main --feed-id company_infosys
```

Use other feed IDs from the project's configured feed definitions.

## 16. Useful verification commands

Queue state:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

Document status:

``` sql
SELECT document_id, document_key, company_name, document_type, status
FROM public.documents
ORDER BY document_id DESC;
```

Document chunks:

``` sql
SELECT chunk_id, chunk_index, content_type, page_start, page_end,
       section, subsection, heading, token_count
FROM public.document_chunks
WHERE document_id = 4
ORDER BY chunk_index;
```

Document embeddings:

``` sql
SELECT dce.embedding_id, dce.chunk_id, dce.provider, dce.model,
       dce.dimension, vector_dims(dce.embedding) AS actual_dimension
FROM public.document_chunk_embeddings dce
ORDER BY dce.chunk_id;
```

Embedding counts:

``` sql
SELECT provider, model, dimension, COUNT(*) AS embedding_count
FROM public.document_chunk_embeddings
GROUP BY provider, model, dimension
ORDER BY provider, model;
```

News statuses:

``` sql
SELECT article_id, article_key, title, status
FROM public.articles
ORDER BY article_id DESC
LIMIT 50;
```

Embedded news:

``` sql
SELECT article_id, article_key, title, status
FROM public.articles
WHERE status = 'embedded'
ORDER BY article_id DESC;
```

## 17. Compile checks after code changes

``` powershell
python -m py_compile .\app\document_ingestion\service.py
python -m py_compile .\app\document_ingestion\embedding_publisher.py
python -m py_compile .\app\workers\document_embedding_worker.py
python -m py_compile .\verify_document_embedding.py
```

Compile whichever Python file was modified before running E2E.

## 18. Validated IPO example

File:

``` text
data/documents/raw/HitechFlowSolutionsDAP_p.pdf
```

Results:

``` text
Pages:              17
Parsed elements:    313
Table candidates:   15
Valid tables:       7
Total chunks:       30
Text chunks:        23
Table chunks:       7
Maximum chunk:      943 tokens
Chunks > 1000:      0
```

Persisted identity:

``` text
document_id = 4
document_key =
3adccc083d26e3b574fb187d92c87e80be56adee2060c285eb45049c5dae85b5

file SHA-256 =
bda833d7d4de6d69570f633867428cd23c0b19803434c0d07b531066841f5f2f
```

Final:

``` text
30/30 chunks embedded
30/30 vectors = 1024 dimensions
provider/model = openai / text-embedding-3-small
document status = embedded
```

## 19. Troubleshooting

### PostgreSQL unavailable

``` powershell
docker start finzer-postgres-local
docker exec -it finzer-postgres-local psql -U finzer -d finzer
```

Confirm `DATABASE_URL` uses local port 5433.

### RabbitMQ unavailable

``` powershell
docker start finzer-rabbitmq-local
docker exec finzer-rabbitmq-local rabbitmqctl status
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

### `document.embedding` has ready messages but no consumer

``` powershell
python -m app.workers.document_embedding_worker
```

### Bedrock embedding authentication fails

Validated fallback behavior is:

``` text
Bedrock unavailable
→ OpenAI available
→ provider/model locked for worker session
```

If OpenAI fallback is intentionally configured, this is acceptable. Do
not mix providers inside the same index.

### Wrong vector dimension

Expected dimension is 1024. Check provider/model settings before
persisting any vector of another size.

### Document stuck in `embedding`

Check:

1.  `document.embedding` queue depth;
2.  worker process;
3.  retry queues/DLQ;
4.  provider/model stored in `document_chunk_embeddings`;
5.  whether every document chunk has the exact provider/model embedding.

## 20. Shutdown

Stop Python workers with `Ctrl+C`.

Stop containers without deleting volumes:

``` powershell
docker stop finzer-rabbitmq-local
docker stop finzer-postgres-local
```

Do not remove PostgreSQL volumes unless database deletion is
intentional.

## 21. Why there is no `document.processing` queue

This is intentional in v1:

``` text
PDF parse/structure/chunking → synchronous
embedding                   → asynchronous
```

The deterministic pipeline was kept synchronous so parsing/chunk-quality
errors remained observable while v1 was being built. A distributed
parsing stage can be added later if throughput requires it.

## 22. Scanned PDF policy

``` text
PDF
→ meaningful native text?
   ├─ yes → PyMuPDF
   └─ no  → OCR fallback
```

OCR should remain a fallback because native text/layout normally
preserves structure better.

## 23. Ingestion v1 completion checklist

``` text
NEWS
PostgreSQL + pgvector              ✅
RabbitMQ                           ✅
Discovery/extraction               ✅
Normalization/deduplication        ✅
article.processing                 ✅
LLM analysis/relevance             ✅
article.embedding                  ✅
1024-d vector persistence          ✅
Retry/DLQ                          ✅

IPO / DOCUMENTS
Provider abstraction               ✅
SEBI discovery                     ✅
PDF download/validation            ✅
SHA-256 identity                   ✅
PyMuPDF parsing                    ✅
Table extraction                   ✅
Style profiling                    ✅
TOC detection                      ✅
Structure detection                ✅
Hierarchy assignment               ✅
Table validation                   ✅
Section-aware chunking             ✅
Document DB schema/repository       ✅
Synchronous orchestration          ✅
document.embedding queues          ✅
Embedding publisher                ✅
Embedding worker                   ✅
Provider fallback/locking          ✅
1024-d pgvector persistence        ✅
30/30 full-document verification   ✅
```

## 24. Boundary after ingestion

Ingestion ends at durable structured content + embeddings:

``` text
raw source
→ ingestion
→ structured content
→ chunks
→ embeddings
→ PostgreSQL + pgvector
```

The following belong to the next architecture/design phase:

``` text
query understanding
retrieval orchestration
hybrid search
reranking
context construction
RAG generation
agent planning/tool selection
multi-agent workflows
answer API/UI
```

This separation lets ingestion v1 remain stable while the RAG/agentic
design is brainstormed independently.

## 25. Final validated document E2E

``` text
HitechFlowSolutionsDAP_p.pdf
→ PDFParser
→ 313 logical elements
→ PDFTableExtractor
→ 15 candidates
→ StyleProfiler + TOCDetector
→ StructureDetector
→ HierarchyAssigner
→ TableValidator
→ 7 valid tables
→ DocumentChunker
→ 30 chunks (23 text + 7 table)
→ DocumentRepository
→ PostgreSQL
→ EmbeddingPublisher
→ document.embedding
→ DocumentEmbeddingWorker
→ EmbeddingRouter
→ OpenAI text-embedding-3-small
→ 30 × 1024-dimensional vectors
→ document_chunk_embeddings
→ document.status = embedded
```

**Finzer ingestion v1 is complete.**
