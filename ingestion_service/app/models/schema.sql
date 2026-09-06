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

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS article_feeds (
    article_key CHAR(64) NOT NULL,
    feed_id VARCHAR(100) NOT NULL,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (article_key, feed_id),

    CONSTRAINT fk_article_feeds_article
        FOREIGN KEY (article_key)
        REFERENCES articles(article_key)
        ON DELETE CASCADE,

    CONSTRAINT fk_article_feeds_feed
        FOREIGN KEY (feed_id)
        REFERENCES feeds(feed_id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_articles_processing_status
    ON articles(processing_status);


CREATE INDEX IF NOT EXISTS idx_articles_published_at
    ON articles(published_at);


CREATE INDEX IF NOT EXISTS idx_article_feeds_feed_id
    ON article_feeds(feed_id);