from app.clients.bedrock_embedding_client import BedrockEmbeddingClient


client = BedrockEmbeddingClient()
vector = client.embed("Finzer local Bedrock embedding smoke test.")
print(f"BEDROCK_EMBEDDING_OK dimension={len(vector)}")
print(f"first_5={vector[:5]}")
