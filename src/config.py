import logging
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


def _first_nonempty(*names: str) -> str | None:
    """Верни первое непустое значение env (обрезая пробелы). Поддержи алиасы."""
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return None


# Критичные ключи читаем ДО инициализации pydantic-модели
_raw_telegram = _first_nonempty("TELEGRAM_TOKEN", "BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
_raw_openai = _first_nonempty("OPENAI_API_KEY", "OPENAI_KEY")
_raw_groq = _first_nonempty("GROQ_API_KEY", "GROQ_KEY")


class Settings(BaseModel):
    # ВАЖНО: подставь значения env прямо в Field(...)
    TELEGRAM_TOKEN: str = Field(_raw_telegram or ..., min_length=10)
    OPENAI_API_KEY: str | None = Field(_raw_openai, min_length=10)
    GROQ_API_KEY: str | None = Field(_raw_groq, min_length=10)

    # Network / webhook
    PORT: int = int(os.getenv("PORT", 8080))
    WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL") or None
    WEBHOOK_SECRET: str | None = os.getenv("WEBHOOK_SECRET") or None

    # Models / limits
    MODEL_DDOT: str = os.getenv("MODEL_DDOT", "gpt-4o")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    MAX_TOKENS_GROQ: int = int(os.getenv("MAX_TOKENS_GROQ", 400))
    MAX_TOKENS_DDOT: int = int(os.getenv("MAX_TOKENS_DDOT", 600))

    # Behavior
    REQUIRE_PREFIX: bool = Field(
        os.getenv("REQUIRE_PREFIX", "false").lower()
        in (
            "1",
            "true",
            "yes",
        ),
        description="Если true, пользователю нужен префикс '.' или '..'",
    )
    DEFAULT_PROVIDER: str = Field(
        os.getenv("DEFAULT_PROVIDER", "groq"),
        description="Провайдер по умолчанию без префикса: 'groq' или 'openai'",
    )
    DIALOG_HISTORY_LEN: int = int(os.getenv("DIALOG_HISTORY_LEN", 5))

    # Logging
    LOG_CHAT_ID: int | None = (
        int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
    )
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "plain")  # plain|json

    # Limits
    MAX_PROMPT_CHARS: int = int(os.getenv("MAX_PROMPT_CHARS", 4000))
    MAX_REPLY_CHARS: int = int(os.getenv("MAX_REPLY_CHARS", 3500))

    # Movies / external services
    DATABASE_URL: str = Field(
        os.getenv("DATABASE_URL") or ..., description="PostgreSQL connection URL"
    )
    TMDB_KEY: str = Field(
        os.getenv("TMDB_KEY") or ..., description="TMDb API key", min_length=10
    )
    MEGA_URL: str | None = os.getenv("MEGA_URL") or None
    LANG_FALLBACKS: list[str] = Field(
        default_factory=lambda: [
            s.strip()
            for s in os.getenv("LANG_FALLBACKS", "ru,en").split(",")
            if s.strip()
        ]
    )

    ADD_CONFIRMATION_MODE: str = os.getenv("ADD_CONFIRMATION_MODE", "strict")


try:
    # Мини-валидация диапазонов + понятная диагностика
    config = Settings()
    assert config.MAX_PROMPT_CHARS > 0
    assert (
        1000 <= config.MAX_REPLY_CHARS <= 4000
    )  # телега ~4096, оставляем запас под HTML
    assert config.DIALOG_HISTORY_LEN > 0
except (ValidationError, AssertionError) as e:
    missing = []
    if not _raw_telegram:
        missing.append("BOT_TOKEN")
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if not os.getenv("TMDB_KEY"):
        missing.append("TMDB_KEY")
    if missing:
        logging.error("Отсутствуют переменные окружения: %s", ", ".join(missing))
        logging.error("   • Railway: Settings → Variables (значения БЕЗ кавычек).")
        logging.error("   • Локально: .env рядом с main.py (НЕ .env.example).")
    raise SystemExit(f"Invalid config: {e}")
