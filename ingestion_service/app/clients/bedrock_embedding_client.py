import json
import os

import boto3
from botocore.config import Config

from app.config.settings import settings


class BedrockEmbeddingClient:
    provider = "bedrock"
    """Amazon Titan Text Embeddings V2 client using Bedrock Runtime."""

    def __init__(self) -> None:
        if not settings.BEDROCK_API_KEY:
            raise ValueError("BEDROCK_API_KEY is not configured.")
        if settings.EMBEDDING_DIMENSION not in {256, 512, 1024}:
            raise ValueError("Titan Text Embeddings V2 dimensions must be 256, 512, or 1024.")

        # Boto3/Bedrock supports Bedrock API-key auth through this variable.
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.BEDROCK_API_KEY

        self.model = settings.BEDROCK_EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.normalize = settings.EMBEDDING_NORMALIZE
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            config=Config(
                connect_timeout=settings.EMBEDDING_REQUEST_TIMEOUT,
                read_timeout=settings.EMBEDDING_REQUEST_TIMEOUT,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def embed(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            raise ValueError("Embedding input cannot be empty.")

        response = self.client.invoke_model(
            modelId=self.model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "inputText": text,
                    "dimensions": self.dimension,
                    "normalize": self.normalize,
                }
            ),
        )
        payload = json.loads(response["body"].read())
        vector = payload.get("embedding")
        if not isinstance(vector, list):
            raise ValueError(f"Bedrock embedding response has no vector: {payload}")
        if len(vector) != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}."
            )
        return [float(value) for value in vector]
