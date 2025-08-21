import os
from dataclasses import dataclass


@dataclass
class Config:
    TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
    OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
    WEBHOOK_URL: str | None = os.environ.get("WEBHOOK_URL")
    WEBHOOK_SECRET: str | None = os.environ.get("WEBHOOK_SECRET")
    PORT: int = int(os.environ.get("PORT", 8080))
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MODEL_FULL: str = os.environ.get("OPENAI_MODEL_FULL", "gpt-4o")
    OPENAI_MAX_OUTPUT_TOKENS: int = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", 400))
    OPENAI_MAX_OUTPUT_TOKENS_FULL: int = int(
        os.environ.get("OPENAI_MAX_OUTPUT_TOKENS_FULL", 600)
    )
    MAX_PROMPT_CHARS: int = int(os.environ.get("MAX_PROMPT_CHARS", 8000))
    MAX_REPLY_CHARS: int = int(os.environ.get("MAX_REPLY_CHARS", 3500))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")


config = Config()
