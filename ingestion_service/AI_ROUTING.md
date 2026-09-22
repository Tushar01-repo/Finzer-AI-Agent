# Finzer AI Provider Routing

## Behavior

Generation and embeddings are routed independently.

- `GENERATOR_PROVIDER=auto`: try `GENERATOR_PRIMARY`, then `GENERATOR_FALLBACK` on request failure.
- `EMBEDDING_PROVIDER=auto`: probe providers when the embedding worker starts, select the first healthy provider, and lock it for the worker session.
- The HTTP MiniLM endpoint is not used by this implementation.

This means Bedrock can serve generation while OpenAI serves embeddings, or vice versa.

## Recommended configuration now

```env
GENERATOR_PROVIDER=auto
GENERATOR_PRIMARY=bedrock
GENERATOR_FALLBACK=openai

EMBEDDING_PROVIDER=auto
EMBEDDING_PRIMARY=bedrock
EMBEDDING_FALLBACK=openai

OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
OPENAI_LLM_MODEL=gpt-5.6-luna
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1024
```

Keep the existing Bedrock settings as shown in `local.env.example`.

## Database migration

Run the normal schema initializer. `schema.sql` now adds `embedding_provider` safely with `ADD COLUMN IF NOT EXISTS`. The vector remains `vector(1024)`.

## Smoke test

From the `ingestion_service` directory with the virtual environment active:

```powershell
python -m scripts.test_ai_routing
```

With the current Bedrock embedding authorization problem and a valid OpenAI key, the expected embedding selection is OpenAI.

## Start workers

```powershell
python -m app.workers.article_processing_worker
python -m app.workers.article_embedding_worker
```

Generation may fail over per request. Embeddings do not switch providers after the worker starts; restart the embedding worker to perform provider selection again.
