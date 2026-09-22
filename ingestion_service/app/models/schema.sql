CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS feeds (
    feed_id VARCHAR(100) PRIMARY KEY,
    feed_type VARCHAR(50) NOT NULL,
    feed_value VARCHAR(100) NOT NULL,
    query TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS articles (
    article_id BIGSERIAL PRIMARY KEY,
    article_key CHAR(64) NOT NULL UNIQUE,
    title TEXT,
    url TEXT NOT NULL,
    source VARCHAR(255),
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at TIMESTAMPTZ,
    content TEXT,
    content_hash CHAR(64),
    summary TEXT,
    processing_status VARCHAR(50) NOT NULL DEFAULT 'pending',
    is_valid_article BOOLEAN,
    relevance_score DOUBLE PRECISION,
    is_relevant BOOLEAN,
    relevance_reason TEXT,
    key_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    companies_mentioned JSONB NOT NULL DEFAULT '[]'::jsonb,
    market_impact TEXT,
    llm_analysis JSONB,
    analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safe upgrades for databases created by earlier Finzer versions.
ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_valid_article BOOLEAN;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_relevant BOOLEAN;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS relevance_reason TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS key_facts JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS companies_mentioned JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS market_impact TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_analysis JSONB;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS article_feeds (
    article_key CHAR(64) NOT NULL,
    feed_id VARCHAR(100) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (article_key, feed_id),
    CONSTRAINT fk_article_feeds_article FOREIGN KEY (article_key)
        REFERENCES articles(article_key) ON DELETE CASCADE,
    CONSTRAINT fk_article_feeds_feed FOREIGN KEY (feed_id)
        REFERENCES feeds(feed_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS article_embeddings (
    article_key CHAR(64) PRIMARY KEY,
    embedding vector(1024) NOT NULL,
    embedding_model VARCHAR(255) NOT NULL,
    embedding_provider VARCHAR(50) NOT NULL DEFAULT 'unknown',
    embedding_dimension INTEGER NOT NULL DEFAULT 1024,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_article_embeddings_article FOREIGN KEY (article_key)
        REFERENCES articles(article_key) ON DELETE CASCADE,
    CONSTRAINT chk_article_embedding_dimension CHECK (embedding_dimension = 1024)
);

ALTER TABLE article_embeddings ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(50) NOT NULL DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_articles_processing_status ON articles(processing_status);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_article_feeds_feed_id ON article_feeds(feed_id);
