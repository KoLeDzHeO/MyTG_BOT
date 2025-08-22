import os
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

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
_raw_openai   = _first_nonempty("OPENAI_API_KEY", "OPENAI_KEY")

class Settings(BaseModel):
    # ВАЖНО: подставь значения env прямо в Field(...)
    TELEGRAM_TOKEN: str = Field(_raw_telegram or ..., min_length=10)
    OPENAI_API_KEY: str = Field(_raw_openai   or ..., min_length=10)

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
    DIALOG_HISTORY_LEN: int = int(os.getenv("DIALOG_HISTORY_LEN", 5))

    # Logging
    LOG_CHAT_ID: int | None = int(os.getenv("LOG_CHAT_ID")) if os.getenv("LOG_CHAT_ID") else None
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "plain")  # plain|json

    # Budget / abuse protection
    RATE_LIMIT_PER_CHAT: int = int(os.getenv("RATE_LIMIT_PER_CHAT", 5))
    RATE_LIMIT_INTERVAL: int = int(os.getenv("RATE_LIMIT_INTERVAL", 60))
    MAX_PROMPT_CHARS: int = int(os.getenv("MAX_PROMPT_CHARS", 4000))
    MAX_REPLY_CHARS: int = int(os.getenv("MAX_REPLY_CHARS", 3500))

try:
    # Мини-валидация диапазонов + понятная диагностика
    config = Settings()
    assert config.RATE_LIMIT_PER_CHAT > 0
    assert config.RATE_LIMIT_INTERVAL > 0
    assert config.MAX_PROMPT_CHARS > 0
    assert 1000 <= config.MAX_REPLY_CHARS <= 4000  # телега ~4096, оставляем запас под HTML
    assert config.DIALOG_HISTORY_LEN > 0
except (ValidationError, AssertionError) as e:
    missing = []
    if not _raw_telegram:
        missing.append("TELEGRAM_TOKEN (или BOT_TOKEN/TELEGRAM_BOT_TOKEN)")
    if not _raw_openai:
        missing.append("OPENAI_API_KEY (или OPENAI_KEY)")
    if missing:
        print("❌ Отсутствуют переменные окружения:", ", ".join(missing))
        print("   • Railway: Settings → Variables (значения БЕЗ кавычек).")
        print("   • Локально: .env рядом с main.py (НЕ .env.example).")
    raise SystemExit(f"Invalid config: {e}")
