import asyncio
from openai import OpenAI

from src.config import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


async def ask_gpt(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    system: str = "Отвечай кратко и по делу для телеграм-чата.",
    timeout: int = 30,
) -> str:
    def _request() -> str:
        client = _get_client()
        text = ""
        try:
            resp = client.responses.create(
                model=model,
                input=prompt,
                instructions=system,  # Responses API ждёт 'instructions'
                max_output_tokens=max_tokens,
            )
            text = getattr(resp, "output_text", "") or ""
            if not text:
                text = resp.output[0].content[0].text
        except Exception:
            pass
        if not text:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                )
                text = resp.choices[0].message.content
            except Exception:
                text = ""
        return text

    try:
        return await asyncio.wait_for(asyncio.to_thread(_request), timeout)
    except Exception:
        return ""
