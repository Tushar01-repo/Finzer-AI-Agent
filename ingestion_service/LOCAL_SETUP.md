# Finzer local runtime + Amazon Bedrock

This setup keeps PostgreSQL, pgvector, RabbitMQ, ingestion state, LLM analysis, and embeddings persisted locally. Amazon Bedrock is used only for inference.

This package does **not** implement IPO/PDF ingestion yet.

## 1. Configure

Copy/edit `local.env` and replace only the placeholders:

- `NEWSDATA_API_KEY`
- `BEDROCK_API_KEY`

The local Docker credentials already match `docker-compose.yml`.

## 2. Install Python dependencies

From `ingestion_service` with your virtual environment activated:

```powershell
pip install -r requirements.txt
```

## 3. Start local infrastructure

```powershell
docker compose up -d
```

Optional checks:

```powershell
docker compose ps
docker logs finzer-postgres-local
docker logs finzer-rabbitmq-local
```

RabbitMQ management UI is available on `http://localhost:15672` using the local credentials from `docker-compose.yml`.

## 4. Initialize the local database

The normal ingestion command initializes `schema.sql`, but you can initialize explicitly:

```powershell
python -c "from app.repositories.database import PostgresDatabase; PostgresDatabase().initialize_schema(); print('DB_SCHEMA_OK')"
```

## 5. Smoke-test Bedrock before starting workers

LLM:

```powershell
python -m scripts.test_bedrock_llm
```

Embedding (Titan V2, normalized 1024 dimensions):

```powershell
python -m scripts.test_bedrock_embedding
```

Expected embedding output includes `dimension=1024`.

## 6. Start the article processing worker

Open a new terminal, activate the same virtual environment, `cd` to `ingestion_service`, then:

```powershell
python -m app.workers.article_processing_worker
```

This consumes `article.processing`, calls Bedrock GPT-OSS, saves analysis to local PostgreSQL, and publishes relevant articles to `article.embedding`.

## 7. Start the embedding worker

Open another terminal:

```powershell
python -m app.workers.article_embedding_worker
```

This consumes `article.embedding`, calls Titan Text Embeddings V2 with 1024 dimensions, and saves vectors to local PostgreSQL `article_embeddings`.

## 8. Run ingestion

Open another terminal:

```powershell
python -m app.main --feed-id company_infosys
```

Replace the feed ID as needed.

## 9. Verify local data

```sql
SELECT article_key, title, processing_status, relevance_score, is_relevant
FROM articles
ORDER BY created_at DESC
LIMIT 20;
```

```sql
SELECT article_key, embedding_model, embedding_dimension, embedded_at
FROM article_embeddings
ORDER BY embedded_at DESC
LIMIT 20;
```

Expected successful relevant-article path:

`pending -> processing -> analyzed -> embedded`

Invalid/irrelevant articles remain stored locally but are not embedded.

## Stop local infrastructure

Stop containers without deleting data:

```powershell
docker compose stop
```

Restart later:

```powershell
docker compose start
```

Delete containers but retain named volumes:

```powershell
docker compose down
```

Delete containers **and all local Finzer PostgreSQL/RabbitMQ data** only when intentionally resetting:

```powershell
docker compose down -v
```
