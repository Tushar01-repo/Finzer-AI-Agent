import os
from openai import OpenAI

client = OpenAI(
    api_key="",
    base_url="https://bedrock-mantle.us-east-1.api.aws/v1",
)

try:
    response = client.chat.completions.create(
        model="openai.gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": "What is Amazon Bedrock?",
            }
        ],
        max_tokens=300,
        temperature=0.3,
    )

    print(response.choices[0].message.content)

except Exception as error:
    print(f"Bedrock request failed: {error}")