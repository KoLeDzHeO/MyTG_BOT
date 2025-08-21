"""Async wrapper around OpenAI Responses API."""

import asyncio
import logging
from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_OUTPUT_TOKENS

log = logging.getLogger(__name__)

_client: OpenAI | None = None


def _mask(key: str | None) -> str:
    if not key:
        return ""
    return key[:4] + "…" + key[-4:]


def _get_client() -> OpenAI:
    """Lazily instantiate OpenAI client.

    The key is taken from environment via ``OPENAI_API_KEY``.  We keep a
    single global instance because the client is thread-safe.
    """

    global _client
    if _client is None:
        log.info("Creating OpenAI client (%s)", _mask(OPENAI_API_KEY))
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


async def ask_gpt(
    prompt: str,
    *,
    system: str = "Отвечай кратко и по делу для телеграм-чата.",
    model: str = OPENAI_MODEL,
    max_tokens: int = OPENAI_MAX_OUTPUT_TOKENS,
) -> str:
    """Call OpenAI Responses API asynchronously and return plain text reply."""

    client = _get_client()

    def _call() -> str:
        resp = client.responses.create(
            model=model,
            input=prompt,
            instructions=system,
            max_output_tokens=max_tokens,
        )
        return (resp.output_text or "").strip()

    # The SDK is synchronous, run it in a background thread to avoid blocking
    return await asyncio.to_thread(_call)

