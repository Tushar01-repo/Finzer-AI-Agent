from openai import OpenAI

from app.config.settings import settings


client = OpenAI(
    api_key=settings.BEDROCK_API_KEY,
    base_url=settings.BEDROCK_LLM_BASE_URL,
    timeout=60,
)

response = client.chat.completions.create(
    model=settings.BEDROCK_LLM_MODEL,
    messages=[{"role": "user", "content": "Reply with exactly: BEDROCK_LLM_OK"}],
    max_tokens=30,
    temperature=0,
)
print(response.choices[0].message.content)
