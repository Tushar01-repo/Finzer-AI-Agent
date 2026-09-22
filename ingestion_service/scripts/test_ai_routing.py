from app.clients.embedding_router import EmbeddingRouter
from app.clients.llm_router import LLMRouter

print("Checking generator configuration...")
llm = LLMRouter()
print("Generator order:", llm.order)
print("Primary configured model:", llm.model)

print("\nChecking embedding providers...")
embedding = EmbeddingRouter()
print("Selected provider:", embedding.provider)
print("Selected model:", embedding.model)
print("Dimension:", embedding.dimension)
