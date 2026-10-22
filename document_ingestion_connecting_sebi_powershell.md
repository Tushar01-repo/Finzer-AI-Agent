@'
from app.document_ingestion.providers.sebi import SEBIDocumentProvider
from app.document_ingestion.service import DocumentIngestionService
from app.document_ingestion.embedding_publisher import DocumentEmbeddingPublisher
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository

database = PostgresDatabase()
repository = DocumentRepository(database)
service = DocumentIngestionService(repository=repository)
provider = SEBIDocumentProvider()

for document in provider.discover(start_page=1, end_page=1):
    print(f"\nFound: {document.title}")

    if not document.pdf_url:
        print("Skipping: no direct PDF URL.")
        continue

    key = service.build_document_key(document)
    existing = repository.get_by_key(key)

    if existing:
        print(f"Skipping existing document: status={existing['status']}")
        continue

    print(f"Downloading: {document.pdf_url}")
    result = service.ingest(document)

    publisher = DocumentEmbeddingPublisher(database=database)
    published = publisher.publish_document(result.document_key)

    print(f"\nDocument ID: {result.document_id}")
    print(f"Document key: {result.document_key}")
    print(f"Chunks queued: {published['published']}")
    print("Watch Terminal 1 for embedding progress.")
    break
else:
    print("No new document with a direct PDF URL found on page 1.")
'@ | python -