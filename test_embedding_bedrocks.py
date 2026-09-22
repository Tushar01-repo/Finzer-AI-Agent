# import json
# import boto3
# from botocore.exceptions import ClientError


# REGION = "us-east-1"
# MODEL_ID = "amazon.titan-embed-text-v2:0"


# def main():
#     print("=" * 60)
#     print("Amazon Titan Text Embeddings V2 Test")
#     print("=" * 60)

#     # Show which AWS identity boto3 is using
#     session = boto3.Session(region_name=REGION)

#     credentials = session.get_credentials()
#     print(f"Region: {session.region_name}")
#     print(
#         f"Credential source: "
#         f"{credentials.method if credentials else 'NONE'}"
#     )

#     sts = session.client("sts")
#     identity = sts.get_caller_identity()

#     print(f"Account: {identity['Account']}")
#     print(f"ARN: {identity['Arn']}")
#     print()

#     # Create Bedrock Runtime client
#     bedrock = session.client(
#         "bedrock-runtime",
#         region_name=REGION,
#     )

#     text = (
#         "Infosys reported strong quarterly revenue growth "
#         "and increased its full-year guidance."
#     )

#     request_body = {
#         "inputText": text,
#         "dimensions": 1024,
#         "normalize": True,
#     }

#     print(f"Model: {MODEL_ID}")
#     print(f"Input: {text}")
#     print("Calling Bedrock...")
#     print()

#     try:
#         response = bedrock.invoke_model(
#             modelId=MODEL_ID,
#             contentType="application/json",
#             accept="application/json",
#             body=json.dumps(request_body),
#         )

#         result = json.loads(
#             response["body"].read().decode("utf-8")
#         )

#         embedding = result["embedding"]

#         print("TITAN_EMBEDDING_OK")
#         print(f"Dimension: {len(embedding)}")
#         print(f"First 5 values: {embedding[:5]}")
#         print(f"Input token count: {result.get('inputTextTokenCount')}")

#         # Check normalization
#         norm = sum(x * x for x in embedding) ** 0.5
#         print(f"Vector norm: {norm:.6f}")

#     except ClientError as exc:
#         error = exc.response.get("Error", {})

#         print("TITAN_EMBEDDING_FAILED")
#         print(f"Error code: {error.get('Code')}")
#         print(f"Message: {error.get('Message')}")
#         print(
#             f"HTTP status: "
#             f"{exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode')}"
#         )

#         raise


# if __name__ == "__main__":
#     main()

import boto3
import json

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
)

model_id = "amazon.nova-micro-v1:0"

request = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "text": "Reply with exactly: BEDROCK_RUNTIME_OK"
                }
            ],
        }
    ],
    "inferenceConfig": {
        "maxTokens": 50,
        "temperature": 0,
    },
}

try:
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(request),
        contentType="application/json",
        accept="application/json",
    )

    result = json.loads(response["body"].read())

    print("NOVA_INVOKE_OK")
    print(json.dumps(result, indent=2))

except Exception as e:
    print("NOVA_INVOKE_FAILED")
    print(type(e).__name__)
    print(e)