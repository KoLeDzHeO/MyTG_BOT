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


async def del_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Удаляет фильм из списка.
    Формат: /del <id|prefix> — принимает полный id или префикс (>=4 символов).
    """
    rid = uuid.uuid4().hex[:8].upper()
    lang = config.LANG_FALLBACKS[0]

    try:
        args = " ".join(context.args).strip()
        if not args:
            await update.message.reply_text(t("del_need_id", lang=lang))
            return

        prefix = _normalize_id(args)

        if len(prefix) < 4:
            await update.message.reply_text(t("del_prefix_too_short", lang=lang))
            return

        candidates = await db.find_movies_by_id_prefix(prefix, limit=5, include_deleted=True)

        if not candidates:
            await update.message.reply_text(t("del_not_found", lang=lang))
            return

        if len(candidates) > 1:
            sample = ", ".join(to_short_id(m["id"]) for m in candidates[:5])
            await update.message.reply_text(t("del_ambiguous", lang=lang, sample=sample))
            return

        movie = candidates[0]
        mid = movie["id"]
        title = movie.get("title") or "Без названия"
        status = movie.get("status")

        if status == STATUS["DELETED"]:
            await update.message.reply_text(
                t("del_already", lang=lang, short_id=to_short_id(mid), title=title)
            )
            return

        updated = await db.mark_movie_deleted(mid)
        short_id = to_short_id(updated["id"])
        await update.message.reply_text(
            t("del_ok", lang=lang, title=updated.get("title") or title, short_id=short_id)
        )

        try:
            await schedule_export(context.job_queue)
        except Exception:
            logging.exception("export schedule failed (/del)")

    except Exception as e:
        logging.exception("/del rid=%s: %s", rid, e)
        try:
            await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
            log_chat_id = getattr(config, "LOG_CHAT_ID", None)
            if log_chat_id:
                await context.bot.send_message(log_chat_id, f"❌ Error {rid}: {e}")
        except Exception:
            pass

