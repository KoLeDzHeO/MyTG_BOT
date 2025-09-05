from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


@dataclass
class Config:
    # 🔐 Токен Telegram-бота (обязательно). Меняется в переменных окружения: TELEGRAM_TOKEN
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")

    # 🔑 Ключ TMDb API. Переменная окружения: TMDB_KEY
    TMDB_KEY: str = os.getenv("TMDB_KEY", "")

    # 🌐 Порядок языков по умолчанию (первый — основной). Меняй список при необходимости
    LANG_FALLBACKS: List[str] = field(default_factory=lambda: ["ru", "en"])

    # ✉️ Требовать префикс перед командами в чатах (true/false). ENV: REQUIRE_PREFIX
    REQUIRE_PREFIX: bool = _get_bool("REQUIRE_PREFIX", False)

    # 🧾 Формат логов: "text" или "json". ENV: LOG_FORMAT
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")

    # 📦 Ссылка на полный архив (например, MEGA). ENV: MEGA_URL; оставь пустым, если не используешь
    MEGA_URL: Optional[str] = os.getenv("MEGA_URL") or None

    # 🕒 Время авто-удаления сообщений /list (в секундах). ENV: LIST_TTL_SECONDS; по умолчанию 300 (5 минут)
    LIST_TTL_SECONDS: int = _get_int("LIST_TTL_SECONDS", 300)


config = Config()

