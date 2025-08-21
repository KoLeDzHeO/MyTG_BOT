from openai import OpenAI
from .config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_OUTPUT_TOKENS

_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

def ask_gpt(prompt: str, system: str = "Отвечай кратко и по делу для телеграм-чата.") -> str:
    client = get_client()
    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        instructions=system,
        max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
    )
    return (resp.output_text or "").strip()
