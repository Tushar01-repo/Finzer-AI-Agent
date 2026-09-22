# Finzer AI Agent --- Complete Local Ingestion Setup

This README documents the local end-to-end setup currently used for the
**Finzer AI Agent news ingestion pipeline**.

The current scope is **news/article ingestion only**. IPO PDF ingestion,
chunking, retrieval, and the user-facing RAG layer are intentionally
outside this setup for now.

------------------------------------------------------------------------

## 1. Current Architecture

``` text
NewsData.io
    |
    v
Local Python Ingestion Service
    |
    +--> Extract / normalize / deduplicate
    |
    v
Local PostgreSQL + pgvector
    |
    v
Local RabbitMQ
    |
    v
article.processing
    |
    v
Article Processing Worker
    |
    v
LLM Router
    |
    +--> Primary: Amazon Bedrock / GPT-OSS
    |
    +--> Fallback: OpenAI generator
    |
    v
LLM Article Analysis
    |
    +--> invalid --------------------------> status = invalid
    |
    +--> relevance < 0.65 ----------------> status = irrelevant
    |
    +--> relevance >= 0.65 ---------------> status = analyzed
                                                |
                                                v
                                         article.embedding
                                                |
                                                v
                                      Embedding Worker
                                                |
                                                v
                                      Embedding Router
                                                |
                    +---------------------------+--------------------+
                    |                                                |
                    v                                                v
          Bedrock embedding                                  OpenAI embedding
             primary                                            fallback
          (currently blocked)                           text-embedding-3-small
                                                                     |
                                                                     v
                                                               1024 dimensions
                                                                     |
                                                                     v
                                                         PostgreSQL + pgvector
                                                                     |
                                                                     v
                                                              status = embedded
```

### Core design rule

The synchronous ingestion layer performs:

-   discovery
-   article extraction
-   normalization
-   deduplication
-   persistence
-   queue publication

The asynchronous workers perform expensive AI operations:

-   LLM analysis
-   relevance classification
-   summarization
-   key-fact extraction
-   market-impact analysis
-   embedding generation

------------------------------------------------------------------------

# 2. Project Location

Example Windows project structure:

``` text
C:\Users\<USER>\Finzer-AI-Agent\
|
+-- venv\
|
+-- ingestion_service\
    |
    +-- app\
    |   +-- clients\
    |   +-- services\
    |   +-- workers\
    |   +-- repositories\
    |   +-- config\
    |
    +-- scripts\
    +-- local.env
```

Enter the ingestion service:

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
```

Activate the virtual environment:

``` powershell
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
```

------------------------------------------------------------------------

# 3. Local Services

The local pipeline currently requires:

  Component                  Location               Purpose
  -------------------------- ---------------------- -----------------------------------------
  Python ingestion service   Local machine          Discovery and extraction
  PostgreSQL                 Docker/local           Persistent application data
  pgvector                   PostgreSQL extension   Vector storage
  RabbitMQ                   Docker/local           Async processing queues
  Processing worker          Local Python           LLM analysis
  Embedding worker           Local Python           Embedding generation
  Bedrock GPT-OSS            AWS                    Primary LLM inference
  OpenAI                     Cloud API              Generator fallback / embedding fallback

> PostgreSQL and RabbitMQ are local, but article text sent to
> Bedrock/OpenAI leaves the local machine for model inference.

------------------------------------------------------------------------

# 4. PostgreSQL

## Connection

The local PostgreSQL instance is exposed on:

``` text
Host:     127.0.0.1
Port:     5433
Database: finzer
Username: finzer
Password: <your local PostgreSQL password>
```

Application configuration:

``` env
DATABASE_URL=postgresql://finzer:<PASSWORD>@127.0.0.1:5433/finzer
```

Do not commit the real password.

## Check PostgreSQL container

``` powershell
docker ps
```

To inspect PostgreSQL container environment variables when necessary:

``` powershell
docker inspect finzer-postgres-local --format '{{range .Config.Env}}{{println .}}{{end}}'
```

Do not share or commit passwords printed by this command.

## Connect using psql

``` powershell
docker exec -it finzer-postgres-local psql -U finzer -d finzer
```

------------------------------------------------------------------------

# 5. pgAdmin Connection

In pgAdmin:

``` text
Servers
  -> Register
  -> Server
```

### General

``` text
Name: Finzer Local
```

### Connection

``` text
Host name/address: 127.0.0.1
Port:              5433
Maintenance DB:    finzer
Username:          finzer
Password:          <your local PostgreSQL password>
```

After connecting:

``` text
Finzer Local
└── Databases
    └── finzer
        └── Schemas
            └── public
                └── Tables
```

Important tables include:

``` text
articles
article_embeddings
```

------------------------------------------------------------------------

# 6. Verify pgvector

Inside PostgreSQL:

``` sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
```

The local environment has been validated with pgvector installed.

To inspect the embedding table:

``` sql
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'article_embeddings'
ORDER BY ordinal_position;
```

Also inspect both relevant tables:

``` sql
SELECT
    table_name,
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('articles', 'article_embeddings')
ORDER BY table_name, ordinal_position;
```

The design keeps the vector data in the dedicated `article_embeddings`
table rather than treating the vector as normal article content.

------------------------------------------------------------------------

# 7. RabbitMQ

RabbitMQ is running locally in Docker.

Typical local ports:

``` text
AMQP:       5672
Management: 15672
VHost:      /finzer
```

## Check container

``` powershell
docker ps
```

## List queues

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

Expected queues:

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

------------------------------------------------------------------------

# 8. RabbitMQ Retry Strategy

The retry queues currently use:

``` text
retry.1 = 30 seconds
retry.2 = 120 seconds / 2 minutes
retry.3 = 600 seconds / 10 minutes
```

Verify:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name arguments
```

Example topology:

``` text
article.processing
       |
       | failure
       v
article.processing.retry.1
       |
       | 30 sec TTL
       v
article.processing
       |
       | failure
       v
article.processing.retry.2
       |
       | 120 sec TTL
       v
article.processing
       |
       | failure
       v
article.processing.retry.3
       |
       | 600 sec TTL
       v
article.processing
       |
       | final failure
       v
article.processing.dlq
```

The embedding queues use the same retry intervals.

A retry queue normally has zero consumers. Messages wait for their TTL
and are dead-lettered back to the main queue.

------------------------------------------------------------------------

# 9. Environment Configuration

Keep secrets in `local.env` or the project's configured local
environment file.

Do not commit:

-   OpenAI API keys
-   AWS credentials
-   NewsData API keys
-   PostgreSQL passwords
-   RabbitMQ passwords

Representative configuration:

``` env
DATABASE_URL=postgresql://finzer:<PASSWORD>@127.0.0.1:5433/finzer

GENERATOR_PROVIDER=auto
GENERATOR_PRIMARY=bedrock
GENERATOR_FALLBACK=openai

EMBEDDING_PROVIDER=auto
EMBEDDING_PRIMARY=bedrock
EMBEDDING_FALLBACK=openai
EMBEDDING_DIMENSION=1024

BEDROCK_LLM_MAX_TOKENS=1800
BEDROCK_LLM_TEMPERATURE=0.0
```

Use the actual variable names already defined by the application for
provider credentials and model identifiers.

------------------------------------------------------------------------

# 10. Generator Routing

Generation is allowed to fall back dynamically.

Current intended routing:

``` text
LLM Router
    |
    v
Amazon Bedrock GPT-OSS
    |
    | API/provider failure
    v
OpenAI generator fallback
```

The currently working Bedrock generator uses GPT-OSS through the
configured Bedrock-compatible endpoint.

The worker startup should show:

``` text
LLM: configured through LLM Router
Relevance threshold: 0.65
```

During processing:

``` text
Generator route: bedrock (openai.gpt-oss-120b)
Bedrock LLM request attempt 1/3
```

------------------------------------------------------------------------

# 11. Article Analysis

One LLM analysis call performs the main structured analysis.

The model produces fields such as:

``` json
{
  "is_valid_article": true,
  "relevance_score": 0.82,
  "is_relevant": true,
  "relevance_type": "direct",
  "financial_event_types": ["market_movement"],
  "relevance_reason": "...",
  "summary": "...",
  "key_facts": ["..."],
  "companies_mentioned": ["..."],
  "market_impact": "...",
  "impact_direction": "positive",
  "impact_horizon": "short_term"
}
```

The application, rather than the model, is authoritative for the final
relevance threshold.

Current threshold:

``` text
0.65
```

Decision:

``` text
score >= 0.65 -> relevant
score <  0.65 -> irrelevant
```

Do not trust only the model-provided `is_relevant` boolean.

------------------------------------------------------------------------

# 12. Article Status Lifecycle

Main statuses:

``` text
pending
   |
   v
processing
   |
   +--> invalid
   |
   +--> irrelevant
   |
   +--> analyzed
            |
            v
         embedded
```

Meaning:

  Status         Meaning
  -------------- ------------------------------------------------------
  `pending`      Article is waiting for AI processing
  `processing`   Worker is processing the article
  `invalid`      LLM determined article is unusable
  `irrelevant`   Valid article but relevance score is below threshold
  `analyzed`     Relevant article successfully analyzed
  `failed`       Processing failed
  `embedded`     Vector generated and stored successfully

------------------------------------------------------------------------

# 13. Start the Processing Worker

Open a PowerShell terminal:

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_processing_worker
```

Expected:

``` text
Finzer Article Processing Worker
Queue: article.processing
Embedding queue: article.embedding
LLM: configured through LLM Router
Relevance threshold: 0.65

Waiting for article messages...
```

Do not run the worker file directly by filesystem path. Run it as a
Python module so package imports resolve correctly.

------------------------------------------------------------------------

# 14. Important Python Worker Restart Rule

Python workers do **not** automatically reload modified source files.

If you modify:

``` text
llm_analyzer.py
bedrock_llm_client.py
llm_router.py
article_processing_worker.py
```

or another imported Python module, stop the worker:

``` text
Ctrl+C
```

and restart:

``` powershell
python -m app.workers.article_processing_worker
```

Otherwise the existing process can continue using the old imported
class/code.

This was observed when `_build_analysis()` had been restored on disk but
the old worker process still had the previous `ArticleAnalyzer` loaded.

Useful validation:

``` powershell
python -c "from app.services.llm_analyzer import ArticleAnalyzer; print(hasattr(ArticleAnalyzer, '_build_analysis'))"
```

Expected:

``` text
True
```

Compile check:

``` powershell
python -m py_compile app/services/llm_analyzer.py
```

No output means the file compiled successfully.

------------------------------------------------------------------------

# 15. Start the Embedding Worker

Open another terminal:

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_embedding_worker
```

Current startup behavior:

``` text
Checking embedding provider: bedrock...
Embedding provider bedrock unavailable: ValidationException: Operation not allowed

Checking embedding provider: openai...
Embedding provider selected and locked: openai (text-embedding-3-small)
```

Then:

``` text
Finzer Article Embedding Worker
Queue: article.embedding
Embedding provider: openai (session locked)
Model: text-embedding-3-small
Dimension: 1024

Waiting for embedding messages...
```

------------------------------------------------------------------------

# 16. Why the Embedding Provider Is Locked

Generation and embedding have different fallback semantics.

LLM generation may safely choose another provider for a later request.

Embeddings must not silently switch provider article-by-article.

Even when two models produce vectors with the same dimension:

``` text
1024 dimensions != same vector space
```

Mixing vectors from unrelated embedding models in the same retrieval
index can make similarity search invalid.

Therefore the embedding router:

1.  probes providers when the worker starts,
2.  chooses the first working provider,
3.  locks that provider for the worker session/index.

Current behavior:

``` text
Bedrock embedding
    |
    | ValidationException
    v
OpenAI text-embedding-3-small
    |
    v
LOCK FOR SESSION
```

If the embedding model/provider is deliberately changed later, the
corresponding retrieval corpus should be deliberately re-embedded rather
than silently mixed.

------------------------------------------------------------------------

# 17. Current Bedrock Embedding Issue

Bedrock embedding invocation currently returns:

``` text
ValidationException: Operation not allowed
```

The application handles this by selecting the OpenAI fallback.

This does not currently block the pipeline.

Current working embedding path:

``` text
OpenAI
  -> text-embedding-3-small
  -> 1024 dimensions
  -> PostgreSQL / pgvector
```

------------------------------------------------------------------------

# 18. Run Ingestion

Example company feed:

``` powershell
python -m app.main --feed-id company_infosys
```

The ingestion layer:

``` text
NewsData.io
    |
    v
Discover candidate articles
    |
    v
Extract article content
    |
    v
Normalize
    |
    v
Deduplicate
    |
    v
Insert/update PostgreSQL
    |
    v
Publish to article.processing
```

The current extractor uses a layered strategy such as:

``` text
Requests
   -> newspaper3k
   -> BeautifulSoup
```

with retry/error classification.

------------------------------------------------------------------------

# 19. Extraction Retry Behavior

HTTP extraction retries transient failures such as:

``` text
429
500
502
503
504
connection failures
read timeouts
```

Typical retry configuration:

``` text
retry_count = 2
```

meaning up to three total attempts.

The extractor does not repeatedly retry permanent failures such as
obvious authentication/security blocks or unusable content.

------------------------------------------------------------------------

# 20. Processing Flow

For every queued article:

``` text
article.processing
        |
        v
Load article from PostgreSQL
        |
        v
Send article to LLM Router
        |
        v
Structured Article Analysis
        |
        v
Validate/normalize model output
        |
        v
Application relevance threshold
```

### Irrelevant

``` text
relevance < 0.65
        |
        v
status = irrelevant
        |
        v
ACK RabbitMQ message
```

No embedding message should be produced.

### Relevant

``` text
relevance >= 0.65
        |
        v
status = analyzed
        |
        v
publish article.embedding
        |
        v
ACK processing message
```

------------------------------------------------------------------------

# 21. Embedding Flow

The embedding worker receives only articles ready for vectorization.

``` text
article.embedding
       |
       v
Load analyzed article
       |
       v
Build embedding input
       |
       v
Session-locked embedding provider
       |
       v
Generate 1024-d vector
       |
       v
Save to article_embeddings
       |
       v
status = embedded
       |
       v
ACK RabbitMQ message
```

Validated worker output has included:

``` text
Current status: analyzed
Embedding input length: ...
Sending article to openai embeddings...
Embedding dimension: 1024
Embedding saved to PostgreSQL.
Status: embedded
RabbitMQ message ACKed.
```

------------------------------------------------------------------------

# 22. Verify Articles in pgAdmin

Open:

``` text
finzer
  -> Schemas
  -> public
  -> Tables
  -> articles
  -> View/Edit Data
  -> All Rows
```

Or use Query Tool:

``` sql
SELECT
    article_id,
    article_key,
    title,
    status
FROM public.articles
ORDER BY article_id DESC;
```

Check specifically for embedded records:

``` sql
SELECT
    article_id,
    article_key,
    title,
    status
FROM public.articles
WHERE status = 'embedded'
ORDER BY article_id DESC;
```

------------------------------------------------------------------------

# 23. Verify Embeddings in PostgreSQL

First inspect the schema so queries use the actual current column names:

``` sql
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'article_embeddings'
ORDER BY ordinal_position;
```

Then:

``` sql
SELECT *
FROM public.article_embeddings
LIMIT 10;
```

The vector will appear similar to:

``` text
[-0.021..., 0.034..., -0.008..., ...]
```

Do not manually count vector elements.

Once the vector column name is confirmed, pgvector can report its
dimensions using:

``` sql
SELECT vector_dims(<embedding_column>)
FROM public.article_embeddings
LIMIT 10;
```

Expected dimension:

``` text
1024
```

------------------------------------------------------------------------

# 24. Verify a Specific Article

Two successfully embedded article keys observed during E2E validation
were:

``` text
17067bd0bd1f2f14be14fb0a86e7c28507a464dc7eb7935528f5fcf66b6f9af9
0cc3cb8d6f6d6b4fcd5f5e49050a40fe1d943182ad42228fef88d1826e750e0d
```

Check them:

``` sql
SELECT
    article_id,
    article_key,
    title,
    status
FROM public.articles
WHERE article_key IN (
    '17067bd0bd1f2f14be14fb0a86e7c28507a464dc7eb7935528f5fcf66b6f9af9',
    '0cc3cb8d6f6d6b4fcd5f5e49050a40fe1d943182ad42228fef88d1826e750e0d'
);
```

Expected:

``` text
status = embedded
```

Then verify corresponding rows in `article_embeddings` using the
relationship columns present in the current schema.

------------------------------------------------------------------------

# 25. Check Queue Health

Run:

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

Healthy idle state should generally resemble:

``` text
article.processing          consumers=1
article.embedding           consumers=1
```

with zero ready/unacknowledged messages when all work has completed.

Retry and DLQ queues should normally be empty after a successful run.

------------------------------------------------------------------------

# 26. DLQ Replay

A replay utility was added for failed processing messages:

``` powershell
python -m scripts.replay_processing_dlq
```

The replay operation should:

1.  read a message from `article.processing.dlq`,
2.  republish its body to `article.processing`,
3.  reset retry metadata as intended,
4.  ACK the old DLQ message only after successful republish.

Do not repeatedly replay messages without first fixing the underlying
failure.

------------------------------------------------------------------------

# 27. LLM JSON Truncation Fix

Earlier GPT-OSS responses were occasionally truncated in the middle of
JSON.

The effective fix included:

``` env
BEDROCK_LLM_MAX_TOKENS=1800
BEDROCK_LLM_TEMPERATURE=0.0
```

and a more compact output contract.

The Bedrock client should also preserve useful response metadata such
as:

``` text
finish_reason
usage
```

If:

``` text
finish_reason = length
```

the response should be treated as truncated rather than as ordinary
malformed JSON.

After the fix, previously failing articles returned complete structured
JSON and were successfully processed.

------------------------------------------------------------------------

# 28. Useful Troubleshooting Commands

## Docker containers

``` powershell
docker ps
```

## RabbitMQ queue counts

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name consumers messages_ready messages_unacknowledged
```

## RabbitMQ queue arguments / TTL

``` powershell
docker exec finzer-rabbitmq-local rabbitmqctl list_queues -p /finzer name arguments
```

## Validate ArticleAnalyzer method

``` powershell
python -c "from app.services.llm_analyzer import ArticleAnalyzer; print(hasattr(ArticleAnalyzer, '_build_analysis'))"
```

## Compile analyzer

``` powershell
python -m py_compile app/services/llm_analyzer.py
```

## Start processing worker

``` powershell
python -m app.workers.article_processing_worker
```

## Start embedding worker

``` powershell
python -m app.workers.article_embedding_worker
```

## Run Infosys ingestion

``` powershell
python -m app.main --feed-id company_infosys
```

## PostgreSQL shell

``` powershell
docker exec -it finzer-postgres-local psql -U finzer -d finzer
```

------------------------------------------------------------------------

# 29. Recommended Startup Order

For a normal local run:

``` text
1. Start Docker
      |
      v
2. Start/check PostgreSQL
      |
      v
3. Start/check RabbitMQ
      |
      v
4. Activate Python virtual environment
      |
      v
5. Start article processing worker
      |
      v
6. Start article embedding worker
      |
      v
7. Run ingestion
      |
      v
8. Watch processing worker
      |
      v
9. Watch embedding worker
      |
      v
10. Verify PostgreSQL + queues
```

Commands:

### Terminal 1 --- processing

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_processing_worker
```

### Terminal 2 --- embedding

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.workers.article_embedding_worker
```

### Terminal 3 --- ingestion / administration

``` powershell
cd C:\Users\<USER>\Finzer-AI-Agent\ingestion_service
C:\Users\<USER>\Finzer-AI-Agent\venv\Scripts\Activate.ps1
python -m app.main --feed-id company_infosys
```

------------------------------------------------------------------------

# 30. Shutdown

Stop Python workers with:

``` text
Ctrl+C
```

If you use Docker Compose for local infrastructure, use the
corresponding Compose stop/down command defined by the project.

Before destructive shutdown commands, confirm whether PostgreSQL data is
stored in a Docker volume. Do not remove volumes unless you
intentionally want to delete local database data.

------------------------------------------------------------------------

# 31. Current E2E Validation Status

The following has been validated:

``` text
Local PostgreSQL                     PASS
pgvector                             PASS
Local RabbitMQ                       PASS
News article ingestion               PASS
Article extraction                   PASS
PostgreSQL persistence               PASS
article.processing publication       PASS
Processing worker                    PASS
Bedrock GPT-OSS generation           PASS
Structured JSON analysis             PASS
0.65 relevance threshold             PASS
Irrelevant article filtering         PASS
Relevant -> embedding publication    PASS
Embedding worker                     PASS
Bedrock embedding probe              FAIL / account authorization
OpenAI embedding fallback            PASS
Provider session locking             PASS
text-embedding-3-small               PASS
1024-dimensional vectors             PASS
Embedding PostgreSQL persistence     PASS
Article status -> embedded           PASS
RabbitMQ ACK                         PASS
Retry queues                         PASS
DLQ handling/replay                  PASS
```

The Bedrock embedding authorization issue does not currently prevent the
application from completing the pipeline because the OpenAI embedding
fallback is operational.

------------------------------------------------------------------------

# 32. Current Proven End-to-End Path

``` text
NewsData.io
      |
      v
Local Ingestion
      |
      v
Article Extraction
      |
      v
Local PostgreSQL
      |
      v
Local RabbitMQ
      |
      v
article.processing
      |
      v
Processing Worker
      |
      v
Bedrock GPT-OSS
      |
      v
Structured Analysis
      |
      v
Application Relevance Filter
      |
      +---- < 0.65 ----> irrelevant -> ACK
      |
      +---- >= 0.65 ---> analyzed
                            |
                            v
                     article.embedding
                            |
                            v
                     Embedding Worker
                            |
                            v
                     Bedrock probe
                            |
                         unavailable
                            |
                            v
                  OpenAI text-embedding-3-small
                            |
                            v
                         1024-d
                            |
                            v
                 PostgreSQL / pgvector
                            |
                            v
                    status = embedded
                            |
                            v
                           ACK
```

------------------------------------------------------------------------

# 33. Deferred Work

The following is intentionally not part of this local setup yet:

-   IPO PDF ingestion
-   IPO document discovery APIs
-   PDF parsing
-   section-aware chunking
-   semantic/hybrid chunking
-   chunk-level embeddings
-   vector retrieval
-   reranking
-   RAG answer generation
-   frontend/query API
-   production deployment of the local ingestion stack

These should be added after the current news ingestion foundation is
stable.

------------------------------------------------------------------------

# 34. Security Notes

Never commit:

``` text
.env
local.env
AWS access keys
OpenAI API keys
NewsData API keys
PostgreSQL passwords
RabbitMQ passwords
```

Prefer environment variables or a secret-management system.

Also remember that although PostgreSQL and RabbitMQ are local, using
Bedrock/OpenAI sends the model input to those external inference
services.

------------------------------------------------------------------------

# 35. Summary

The local Finzer ingestion system now has a working asynchronous AI
pipeline:

``` text
Discover
 -> Extract
 -> Persist
 -> Queue
 -> Analyze
 -> Filter
 -> Embed
 -> Store vector
```

The important separation is:

``` text
PostgreSQL = persistent state
RabbitMQ   = asynchronous work transport
Bedrock    = primary LLM inference
OpenAI     = fallback / current embedding provider
pgvector   = local vector persistence
```

This provides the base required for the next Finzer phase: retrieval,
RAG, and eventually IPO document ingestion.
