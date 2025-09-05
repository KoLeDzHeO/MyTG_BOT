import logging
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from src.core import db
from src.core.config import config
from src.core.i18n import t
from src.domain.movies.constants import STATUS
from src.utils.ids import to_short_id
from src.services.exporter import schedule_export


def _normalize_id(raw: str) -> str:
    """
    Нормализует ID фильма:
    - убирает пробелы и ведущий '#'
    - приводит к нижнему регистру
    """
    raw = (raw or "").strip().lstrip("#").strip()
    return raw.lower()


async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отмечает фильм как «просмотренный».
    Формат: /done <id|prefix> — принимает полный id или префикс (>=4 символов).
    """
    rid = uuid.uuid4().hex[:8].upper()
    lang = config.LANG_FALLBACKS[0]

    try:
        # В PTB v20+ аргументы команды приходят в context.args (list)
        args = " ".join(context.args).strip() if getattr(context, "args", None) else ""
        if not args:
            await update.message.reply_text(
                t("done_need_id", lang=lang)  # "Укажи ID фильма, например: /done 1a2b3c"
            )
            return

        prefix = _normalize_id(args)

        if len(prefix) < 4:
            await update.message.reply_text(
                t("done_prefix_too_short", lang=lang)  # "Укажи хотя бы 4 символа ID."
            )
            return

        # Ищем по префиксу (без учёта регистра), исключая удалённые
        candidates = await db.find_movies_by_id_prefix(prefix, limit=5)

        if not candidates:
            await update.message.reply_text(t("done_not_found", lang=lang))
            return

        if len(candidates) > 1:
            # Несколько совпадений — просим уточнить
            sample = ", ".join(to_short_id(m["id"]) for m in candidates[:5])
            await update.message.reply_text(
                t("done_ambiguous", lang=lang, sample=sample)
            )
            return

        movie = candidates[0]
        mid = movie["id"]
        title = movie.get("title") or "Без названия"
        status = movie.get("status")

        if status == STATUS["DELETED"]:
            await update.message.reply_text(
                t("done_deleted", lang=lang, title=title, short_id=to_short_id(mid))
            )
            return

        if status == STATUS["WATCHED"]:
            await update.message.reply_text(
                t("done_already", lang=lang, title=title, short_id=to_short_id(mid))
            )
            return

        # Отмечаем как просмотренный
        updated = await db.mark_movie_watched(mid)
        short_id = to_short_id(updated["id"])
        await update.message.reply_text(
            t("done_ok", lang=lang, title=updated.get("title") or title, short_id=short_id)
        )

        # Планируем экспорт (дебаунс внутри schedule_export)
        try:
            await schedule_export(context.job_queue)
        except Exception:
            logging.exception("export schedule failed (/done)")

    except Exception as e:
        logging.exception("/done rid=%s: %s", rid, e)
        try:
            await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
            log_chat_id = getattr(config, "LOG_CHAT_ID", None)
            if log_chat_id:
                await context.bot.send_message(log_chat_id, f"❌ Error {rid}: {e}")
        except Exception:
            pass
