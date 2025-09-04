from __future__ import annotations

from .config import config

MESSAGES = {
    "ru": {
        "series_prompt": "Похоже, это серия “{base_title}”. Уточните часть:",
        "year_prompt": "Не нашёл точное совпадение по году {user_year}. Возможные варианты:",
        "added": "Ок, добавляю: “{title}” ({year}). Жанры: {genres}.",
        "duplicate": "Этот фильм уже в списке: #{short_id} — “{title}” ({year}).",
        "cancelled": "Отменено.",
        "timeout": "Время выбора истекло — попробуйте снова: /add {query}.",
        "old_cancelled": "Старая попытка отменена.",
        "add_found_btn": "Добавить найденный",
        "cancel_btn": "Отмена",
        "year_unknown": "год неизвестен",
    },
    "en": {
        "series_prompt": "Looks like it's a series '{base_title}'. Choose a part:",
        "year_prompt": "No exact match for year {user_year}. Possible options:",
        "added": "Ok, adding: '{title}' ({year}). Genres: {genres}.",
        "duplicate": "This movie is already in the list: #{short_id} — '{title}' ({year}).",
        "cancelled": "Cancelled.",
        "timeout": "Timeout — try again: /add {query}.",
        "old_cancelled": "Previous attempt cancelled.",
        "add_found_btn": "Add found",
        "cancel_btn": "Cancel",
        "year_unknown": "year unknown",
    },
}


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = lang or config.LANG_FALLBACKS[0]
    table = MESSAGES.get(lang) or MESSAGES["en"]
    text = table.get(key) or MESSAGES["en"].get(key, "")
    return text.format(**kwargs)
