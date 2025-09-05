from __future__ import annotations

from .config import config

MESSAGES = {
    "ru": {
        "series_prompt": "Похоже, это серия “{base_title}”. Уточните часть:",
        "year_prompt": "Не нашёл точное совпадение по году {user_year}. Возможные варианты:",
        "duplicate": "Этот фильм уже в списке: #{short_id} — “{title}” ({year}).",
        "cancelled": "Отменено.",
        "timeout": "Время выбора истекло — попробуйте снова: /add {query}.",
        "old_cancelled": "Старая попытка отменена.",
        "cancel_btn": "Отмена",
        "year_unknown": "год неизвестен",
        "list_empty": "Список пока пуст.",
        "list_archive": "Полный архив: {url}",
        "add_success": "➕ Добавлено {short_id}\n🎥 “{title}” ({year}) — {genres}",
        "add_duplicate_simple": "Этот фильм уже в списке (найдён по TMDb).",
        "format_error": "Формат: /add Название 2014",
        "year_error": "Год обязателен: 1888–2100. Пример: /add Интерстеллар 2014",
        "not_found": "Не нашёл такой фильм в базе TMDb. Попробуй другое написание.",
        "auth_error": "Проблема авторизации TMDb. Проверьте TMDB_KEY.",
        "rate_error": "TMDb ограничил частоту запросов. Попробуйте чуть позже.",
        "tmdb_unavailable": "Сервис TMDb временно недоступен, попробуйте позже.",
        "tech_error": "⚠️ Сервис временно недоступен (id={rid})",
        "same_title_prompt": "Нашлось несколько релизов “{title}”. Выберите год:",
        "help_text": (
            "🎬 Команды:\n\n"
            "/add Название Год — добавить фильм\n"
            "/list — показать список фильмов\n"
            "/done ID — отметить как просмотренный\n"
            "/del ID — удалить фильм\n\n"
            "ℹ️ Фильмы ищутся через TMDb.\n"
            "This product uses the TMDb API but is not endorsed or certified by TMDb."
        ),
        "done_need_id": "Укажи ID фильма, например: /done 1a2b3c",
        "done_prefix_too_short": "Укажи хотя бы 4 символа ID.",
        "done_not_found": "Не нашёл фильм с таким ID.",
        "done_ambiguous": "Несколько совпадений: {sample}",
        "done_deleted": "Фильм {short_id} — “{title}” удалён.",
        "done_already": "Фильм {short_id} — “{title}” уже отмечен.",
        "done_ok": "✅ Просмотрено {short_id}\n🎬 “{title}”",
        "del_need_id": "Укажи ID фильма, например: /del 1a2b3c",
        "del_prefix_too_short": "Укажи хотя бы 4 символа ID.",
        "del_not_found": "Фильм с таким ID не найден.",
        "del_ambiguous": "Несколько совпадений: {sample}",
        "del_already": "Фильм {short_id} — “{title}” уже удалён.",
        "del_ok": "🗑 Удалено {short_id}\n🎬 “{title}”",
    },
    "en": {
        "series_prompt": "Looks like it's a series '{base_title}'. Choose a part:",
        "year_prompt": "No exact match for year {user_year}. Possible options:",
        "duplicate": "This movie is already in the list: #{short_id} — '{title}' ({year}).",
        "cancelled": "Cancelled.",
        "timeout": "Timeout — try again: /add {query}.",
        "old_cancelled": "Previous attempt cancelled.",
        "cancel_btn": "Cancel",
        "year_unknown": "year unknown",
        "list_empty": "List is empty.",
        "list_archive": "Full archive: {url}",
        "add_success": "➕ Added {short_id}\n🎥 '{title}' ({year}) — {genres}",
        "add_duplicate_simple": "This movie is already in the list (matched via TMDb).",
        "format_error": "Format: /add Title 2014",
        "year_error": "Year is required: 1888–2100. Example: /add Interstellar 2014",
        "not_found": "Couldn't find this movie in TMDb. Try different spelling.",
        "auth_error": "TMDb authorization problem. Check TMDB_KEY.",
        "rate_error": "TMDb rate limit exceeded. Try again later.",
        "tmdb_unavailable": "TMDb service is temporarily unavailable, try later.",
        "tech_error": "⚠️ Service temporarily unavailable (id={rid})",
        "same_title_prompt": "Found multiple releases of '{title}'. Pick a year:",
        "done_need_id": "Specify movie ID, e.g., /done 1a2b3c",
        "done_prefix_too_short": "Provide at least 4 characters of the ID.",
        "done_not_found": "Movie not found for this ID.",
        "done_ambiguous": "Multiple matches: {sample}",
        "done_deleted": "Movie {short_id} — '{title}' is deleted.",
        "done_already": "Movie {short_id} — '{title}' already marked as watched.",
        "done_ok": "✅ Marked as watched {short_id}\n🎬 '{title}'",
        "del_need_id": "Specify movie ID, e.g., /del 1a2b3c",
        "del_prefix_too_short": "Provide at least 4 characters of the ID.",
        "del_not_found": "Movie not found for this ID.",
        "del_ambiguous": "Multiple matches: {sample}",
        "del_already": "Movie {short_id} — '{title}' already deleted.",
        "del_ok": "🗑 Deleted {short_id}\n🎬 '{title}'",
    },
}


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = lang or config.LANG_FALLBACKS[0]
    table = MESSAGES.get(lang) or MESSAGES["en"]
    text = table.get(key) or MESSAGES["en"].get(key, "")
    return text.format(**kwargs)
