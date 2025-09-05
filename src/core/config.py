from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _get_bool(name: str, default: bool = False) -> bool:
    """Считывает булеву переменную окружения."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    """Считывает целочисленную переменную окружения."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # --- Ключи и токены ---
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")  # токен бота (обязательно для запуска)
    TMDB_KEY: str = os.getenv("TMDB_KEY", "")  # ключ TMDb для поиска фильмов
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY") or None  # ключ OpenAI (для режимов диалога)
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY") or None  # ключ Groq (для режимов диалога)

    # --- Провайдеры и модели диалога ---
    USE_GROQ: bool = _get_bool("USE_GROQ", False)  # если true — использовать Groq как провайдер диалога по умолчанию
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "openai")  # "groq" или "openai" — провайдер по умолчанию
    MODEL_OPENAI: str = os.getenv("MODEL_OPENAI", "gpt-4o")  # модель OpenAI по умолчанию (например, "gpt-4o")
    MODEL_GROQ: str = os.getenv("MODEL_GROQ", "llama-3.3-70b-versatile")  # модель Groq по умолчанию
    MAX_TOKENS_OPENAI: int = _get_int("MAX_TOKENS_OPENAI", 600)  # лимит токенов для OpenAI-ответа
    MAX_TOKENS_GROQ: int = _get_int("MAX_TOKENS_GROQ", 400)  # лимит токенов для Groq-ответа
    MAX_PROMPT_CHARS: int = _get_int("MAX_PROMPT_CHARS", 2000)  # макс. длина входного текста пользователя
    MAX_REPLY_CHARS: int = _get_int("MAX_REPLY_CHARS", 3500)  # макс. длина ответа, символов
    DIALOG_HISTORY_LEN: int = _get_int("DIALOG_HISTORY_LEN", 5)  # сколько последних сообщений хранить в истории
    GPT_HTTP_TIMEOUT: int = _get_int(
        "GPT_HTTP_TIMEOUT", 30
    )  # таймаут HTTP-запросов к GPT, сек
    GPT_MAX_RETRIES: int = _get_int(
        "GPT_MAX_RETRIES", 3
    )  # макс. попыток запроса к GPT
    GPT_RETRY_BACKOFF_BASE: int = _get_int(
        "GPT_RETRY_BACKOFF_BASE", 1
    )  # базовая задержка между повторными запросами, сек

    # --- Вебхук/поллинг ---
    USE_WEBHOOK: bool = _get_bool("USE_WEBHOOK", False)  # режим вебхука: true — вебхук, false — polling
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL") or None  # публичный URL вебхука (если включён)
    WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET") or None  # секрет для проверок вебхука (если нужен)
    PORT: int = _get_int("PORT", 8080)  # порт для вебхука/сервера

    # --- База данных и архив ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")  # строка подключения к Postgres (может быть пустой локально)
    MEGA_URL: Optional[str] = os.getenv("MEGA_URL") or None  # ссылка на архив (опционально)

    # --- Локализация и логи ---
    LANG_FALLBACKS: list[str] = field(
        default_factory=lambda: [s for s in os.getenv("LANG_FALLBACKS", "ru,en").split(",") if s]
    )  # порядок языков по умолчанию, первый — основной
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")  # "text" или "json" (по умолчанию "text")
    LOG_CHAT_ID: Optional[int] = (
        _get_int("LOG_CHAT_ID", 0) if os.getenv("LOG_CHAT_ID") is not None else None
    )  # чат для ошибок/логов (если задан)

    # --- Поведение команд ---
    REQUIRE_PREFIX: bool = _get_bool("REQUIRE_PREFIX", False)  # требовать префикс для обычных сообщений
    TELEGRAM_MESSAGE_LIMIT: int = _get_int(
        "TELEGRAM_MESSAGE_LIMIT", 4000
    )  # макс. длина текста сообщения Telegram, символы

    # --- Параметры бота фильмов ---
    LIST_TTL_SECONDS: int = _get_int("LIST_TTL_SECONDS", 300)  # авто-удаление сообщений /list, сек
    LIST_PAGE_SIZE: int = _get_int(
        "LIST_PAGE_SIZE", 30
    )  # сколько последних фильмов показывать командой /list

    # --- Параметры команд ---
    ADD_PENDING_TTL: int = _get_int("ADD_PENDING_TTL", 120)  # TTL выбора фильма, сек
    ADD_YEAR_MIN: int = _get_int("ADD_YEAR_MIN", 1888)       # минимальный год релиза
    ADD_YEAR_MAX: int = _get_int("ADD_YEAR_MAX", 2100)       # максимальный год релиза
    EXPORT_DEBOUNCE_SECONDS: int = _get_int("EXPORT_DEBOUNCE_SECONDS", 3)   # задержка экспорта, сек
    EXPORT_WARN_INTERVAL: int = _get_int("EXPORT_WARN_INTERVAL", 600)       # интервал предупреждений, сек


config = Config()
