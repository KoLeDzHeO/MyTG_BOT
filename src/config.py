import os
from typing import Set

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() in ("1", "true", "yes")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8080"))


def _csv_to_int_set(s: str) -> Set[int]:
    return {int(x) for x in s.split(",") if x.strip()} if s else set()


TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MODEL_FULL = os.getenv("OPENAI_MODEL_FULL", "gpt-4o")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "400"))
OPENAI_MAX_OUTPUT_TOKENS_FULL = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS_FULL", "600"))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "8000"))
MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "3500"))
CONTEXT_TURNS = int(os.getenv("CONTEXT_TURNS", "5"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "3"))
ALLOWED_CHAT_IDS = _csv_to_int_set(os.getenv("ALLOWED_CHAT_IDS", ""))


def config_info() -> dict:
    return {
        "OPENAI_MODEL": OPENAI_MODEL,
        "OPENAI_MODEL_FULL": OPENAI_MODEL_FULL,
        "OPENAI_MAX_OUTPUT_TOKENS": OPENAI_MAX_OUTPUT_TOKENS,
        "OPENAI_MAX_OUTPUT_TOKENS_FULL": OPENAI_MAX_OUTPUT_TOKENS_FULL,
        "MAX_PROMPT_CHARS": MAX_PROMPT_CHARS,
        "MAX_REPLY_CHARS": MAX_REPLY_CHARS,
        "CONTEXT_TURNS": CONTEXT_TURNS,
        "COOLDOWN_SECONDS": COOLDOWN_SECONDS,
        "ALLOWED_CHAT_IDS_COUNT": len(ALLOWED_CHAT_IDS),
        "LOG_LEVEL": LOG_LEVEL,
        "USE_WEBHOOK": USE_WEBHOOK,
        "WEBHOOK_URL_set": bool(WEBHOOK_URL),
        "WEBHOOK_SECRET_set": bool(WEBHOOK_SECRET),
        "PORT": PORT,
    }

