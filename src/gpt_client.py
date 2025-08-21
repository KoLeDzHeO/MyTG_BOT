"""Async wrapper around OpenAI Responses API with fallback."""

import asyncio
import logging
import openai
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
    """Call OpenAI Responses API asynchronously and return plain text reply.

    The function first tries the ``Responses`` API and attempts to obtain the
    text from ``output_text``.  If the field is missing or empty, it falls back
    to ``resp.output[0].content[0].text``.  As a last resort the legacy chat
    completions API is used.  The returned string is not stripped or otherwise
    modified.
    """

    client = _get_client()

    def _call() -> str:
        # Try Responses API
        resp = client.responses.create(
            model=model,
            input=prompt,
            instructions=system,
            max_output_tokens=max_tokens,
        )
        text = resp.output_text or ""
        if not text:
            try:
                text = resp.output[0].content[0].text or ""
            except Exception:
                text = ""
        if not text:
            # Fallback to Chat Completions
            chat = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
            )
            text = chat.choices[0].message.content or ""
        return text

    # The SDK is synchronous, run it in a background thread to avoid blocking
    return await asyncio.to_thread(_call)


def client_diagnostics() -> dict[str, object]:
    """Log and return diagnostic info about the OpenAI client."""

    client = _get_client()
    info = {
        "sdk_version": openai.__version__,
        "api_key": bool(OPENAI_API_KEY),
        "responses_api": hasattr(client, "responses"),
        "chat_completions_api": hasattr(getattr(client, "chat", None), "completions"),
    }
    log.info(
        "OpenAI SDK %s key=%s responses=%s chat_completions=%s",
        info["sdk_version"],
        _mask(OPENAI_API_KEY),
        info["responses_api"],
        info["chat_completions_api"],
    )
    return info

