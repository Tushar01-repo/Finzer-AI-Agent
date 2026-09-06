ingestion_service/
│
├── app/
│   ├── __init__.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── feeds.yaml
│   │   └── feed_registry.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── feed.py
│   │   └── article.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── feed_fetcher.py
│   │   ├── rss_parser.py
│   │   ├── google_news_resolver.py
│   │   ├── article_extractor.py
│   │   ├── article_normalizer.py
│   │   └── deduplication.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── feed_repository.py
│   │   ├── article_repository.py
│   │   └── article_feed_repository.py
│   │
│   ├── messaging/
│   │   ├── __init__.py
│   │   ├── rabbitmq.py
│   │   └── publisher.py
│   │
│   └── api/
│       ├── __init__.py
│       └── ingestion.py
│
├── tests/
├── requirements.txt
├── .env.example
├── Dockerfile
└── README.md