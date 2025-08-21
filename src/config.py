import os
from typing import Set

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
