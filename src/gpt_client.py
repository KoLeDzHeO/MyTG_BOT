"""Async wrapper around OpenAI APIs with robust fallback + diagnostics."""

import asyncio
import logging
import openai as openai_pkg
from openai import OpenAI

from .config import (
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MODEL_FULL,
    OPENAI_MAX_OUTPUT_TOKENS
)

log = logging.getLogger(__name__)

_client: OpenAI | None = None
_DEFAULT_TIMEOUT = 30  # seconds


def _mask(key: str | None) -> str:
    if not key:
        return ""
    return key[:4] + "…" + key[-4:]


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        log.info("Creating OpenAI client (%s)", _mask(OPENAI_API_KEY))
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def client_diagnostics() -> dict:
    """Return a dict for startup logs (no network)."""
    version = getattr(openai_pkg, "__version__", "unknown")
    try:
        client = _get_client()
        responses_api = hasattr(client, "responses") and hasattr(client.responses, "create")
        chat_api = hasattr(client, "chat") and hasattr(client.chat.completions, "create")
    except Exception:
        responses_api = False
        chat_api = False
    log.info("OpenAI SDK %s key=%s responses=%s chat_completions=%s",
             version, _mask(OPENAI_API_KEY), responses_api, chat_api)
    return {
        "openai_version": version,
        "has_api_key": bool(OPENAI_API_KEY),
        "responses_api": responses_api,
        "chat_completions_api": chat_api,
        "model_mini": OPENAI_MODEL,
        "model_full": OPENAI_MODEL_FULL,
    }


async def ask_gpt(
    prompt: str,
    *,
    system: str = "Отвечай кратко и по делу для телеграм-чата.",
    model: str = OPENAI_MODEL,
    max_tokens: int = OPENAI_MAX_OUTPUT_TOKENS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Try Responses API; if empty/exception — fallback to Chat Completions."""
    client = _get_client()

    def _call_responses() -> str:
        resp = client.responses.create(
            model=model,
            input=prompt,
            instructions=system,
            max_output_tokens=max_tokens,
            timeout=timeout,
        )
        # SDK ≥ 1.40: output_text есть; ниже — резерв на всякий случай
        text = (getattr(resp, "output_text", "") or "").strip()
        if not text and hasattr(resp, "output") and resp.output:
            try:
                # старый формат
                text = resp.output[0].content[0].text.strip()
            except Exception:
                text = ""
        return text

    def _call_chat() -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            timeout=timeout,
        )
        choice = resp.choices[0] if resp.choices else None
        content = choice.message.content if choice and choice.message else ""
        return (content or "").strip()

    try:
        text = await asyncio.to_thread(_call_responses)
        if text:
            return text
        log.warning("Responses API returned empty text — using Chat Completions fallback.")
        return await asyncio.to_thread(_call_chat)
    except Exception as e:
        log.exception("Responses API exception: %s", e)
        return await asyncio.to_thread(_call_chat)

