import asyncio
import logging
from openai import OpenAI

from src.utils.text_utils import mask

_client: OpenAI | None = None
_client_key: str | None = None


def _get_client(api_key: str) -> OpenAI:
    global _client, _client_key
    if _client is None or _client_key != api_key:
        _client = OpenAI(api_key=api_key)
        _client_key = api_key
    return _client


async def ask_gpt(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str = "Отвечай кратко и по делу для телеграм-чата.",
    timeout: int = 30,
) -> str:
    def _request() -> str:
        client = _get_client(api_key)
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
        except Exception as e:
            logging.warning("responses err %s", mask(str(e)))
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
            except Exception as e:
                logging.error("chat err %s", mask(str(e)))
                text = ""
        return text

    try:
        return await asyncio.wait_for(asyncio.to_thread(_request), timeout)
    except Exception as e:
        logging.error("gpt timeout err %s", mask(str(e)))
        return ""
