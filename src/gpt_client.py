from openai import OpenAI
from .config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_OUTPUT_TOKENS

_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

def ask_gpt(
    prompt: str,
    system: str = "Отвечай кратко и по делу для телеграм-чата.",
    model: str = OPENAI_MODEL,
    max_tokens: int = OPENAI_MAX_OUTPUT_TOKENS,
) -> str:
    client = get_client()
    resp = client.responses.create(
        model=model,
        input=prompt,
        instructions=system,
        max_output_tokens=max_tokens,
    )
    return (resp.output_text or "").strip()
