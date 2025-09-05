import asyncio
import logging
import os

import requests
from openai import OpenAI

from src.core.config import config
from src.utils.text import mask

_client: OpenAI | None = None
_client_token: str | None = None


def _get_client(api_token: str) -> OpenAI:
    global _client, _client_token
    if _client is None or _client_token != api_token:
        os.environ["OPENAI_API_KEY"] = api_token
        _client = OpenAI()
        _client_token = api_token
    return _client


async def ask_openai(
    *,
    api_token: str,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str,
    timeout: int | None = None,
) -> str:
    timeout = timeout or config.GPT_HTTP_TIMEOUT
    async def _request() -> str:
        for attempt in range(config.GPT_MAX_RETRIES):
            client = _get_client(api_token)
            text = ""
            try:
                resp = await asyncio.to_thread(
                    client.responses.create,
                    model=model,
                    input=prompt,
                    instructions=system,
                    max_output_tokens=max_tokens,
                )
                text = getattr(resp, "output_text", "") or ""
                if not text:
                    text = resp.output[0].content[0].text
            except Exception as e:
                logging.warning("[openai] responses error %s", mask(str(e)))
            if not text:
                try:
                    resp = await asyncio.to_thread(
                        client.chat.completions.create,
                        model=model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=max_tokens,
                    )
                    text = resp.choices[0].message.content
                except Exception as e:
                    logging.error("[openai] chat error %s", mask(str(e)))
                    text = ""
            if text:
                return text
            if attempt < config.GPT_MAX_RETRIES - 1:
                await asyncio.sleep(
                    config.GPT_RETRY_BACKOFF_BASE * (2 ** attempt)
                )
        return ""

    try:
        return await asyncio.wait_for(_request(), timeout)
    except Exception as e:
        logging.error("[openai] timeout %s", mask(str(e)))
        return ""


async def ask_groq(
    *,
    api_token: str,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str,
    timeout: int | None = None,
) -> str:
    timeout = timeout or config.GPT_HTTP_TIMEOUT
    url = "https://api.groq.com/openai/v1/chat/completions"

    async def _request() -> str:
        for attempt in range(config.GPT_MAX_RETRIES):
            try:
                resp = await asyncio.to_thread(
                    requests.post,
                    url,
                    headers={"Authorization": f"Bearer {api_token}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                    },
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content")
                if not content:
                    content = choice.get("delta", {}).get("content", "")
                return content or ""
            except Exception as e:
                logging.error("[groq] error %s", mask(str(e)))
                if attempt < config.GPT_MAX_RETRIES - 1:
                    await asyncio.sleep(
                        config.GPT_RETRY_BACKOFF_BASE * (2 ** attempt)
                    )
        return ""

    try:
        return await asyncio.wait_for(_request(), timeout)
    except Exception as e:
        logging.error("[groq] timeout %s", mask(str(e)))
        return ""

