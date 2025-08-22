import os
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    TELEGRAM_TOKEN: str = Field(..., min_length=10)
    OPENAI_API_KEY: str = Field(..., min_length=10)

    # Network / webhook
    PORT: int = int(os.getenv("PORT", 8080))
    WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL") or None
    WEBHOOK_SECRET: str | None = os.getenv("WEBHOOK_SECRET") or None

    # Models / limits
    MODEL_DOT: str = os.getenv("MODEL_DOT", "gpt-4o-mini")
    MODEL_DDOT: str = os.getenv("MODEL_DDOT", "gpt-4o")
    MAX_TOKENS_DOT: int = int(os.getenv("MAX_TOKENS_DOT", 400))
    MAX_TOKENS_DDOT: int = int(os.getenv("MAX_TOKENS_DDOT", 600))

    # Behavior
    REQUIRE_PREFIX: bool = os.getenv("REQUIRE_PREFIX", "true").lower() in ("1", "true", "yes")

    # Logging
    LOG_CHAT_ID: int | None = int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "plain")  # plain|json

    # Budget / abuse protection
    RATE_LIMIT_PER_CHAT: int = int(os.getenv("RATE_LIMIT_PER_CHAT", 5))   # N запросов
    RATE_LIMIT_INTERVAL: int = int(os.getenv("RATE_LIMIT_INTERVAL", 60))  # окно секунд
    MAX_PROMPT_CHARS: int = int(os.getenv("MAX_PROMPT_CHARS", 4000))      # макс. длина входа
    MAX_REPLY_CHARS: int = int(os.getenv("MAX_REPLY_CHARS", 3500))        # макс. длина ответа в сообщении

try:
    # минимальная валидация диапазонов
    config = Settings()
    assert config.RATE_LIMIT_PER_CHAT > 0
    assert config.RATE_LIMIT_INTERVAL > 0
    assert config.MAX_PROMPT_CHARS > 0
    assert 1000 <= config.MAX_REPLY_CHARS <= 4000  # телеграм ~4096, с запасом под html
except (ValidationError, AssertionError) as e:
    raise SystemExit(f"Invalid config: {e}")
