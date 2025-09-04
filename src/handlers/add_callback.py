import logging
import time
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from src import db
from src.db import DuplicateTmdbError, get_movie_by_tmdb_id
from src.tmdb_client import tmdb_client, TMDbError
from src.config import config
from src.i18n import t
from src.exporter import schedule_export
from src.utils.ids import to_short_id
from .add import _pending, NO_DATE


async def add_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    data = query.data or ""
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
    key = (chat_id, user_id, query.message.message_id)
    pending = _pending.get(key)
    if not pending:
        await query.answer()
        return
    lang = pending.get("lang", lang)
    if pending["expires_at"] <= time.time():
        _pending.pop(key, None)
        await query.message.reply_text(t("timeout", lang=lang, query=pending["query"]))
        await query.answer()
        return

    if data == "ADD_CANCEL":
        _pending.pop(key, None)
        logging.warning("/add cancelled")
        await query.message.reply_text(t("cancelled", lang=lang))
        await query.answer()
        return

    if data == "ADD_TOP1":
        tmdb_id = pending["top1_tmdb_id"]
    elif data.startswith("ADD_PICK:"):
        try:
            tmdb_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer()
            return
        if tmdb_id not in pending["options"]:
            await query.answer()
            return
    else:
        await query.answer()
        return

    try:
        details = await tmdb_client.get_movie_details(tmdb_id)
        if not details:
            await query.message.reply_text(NO_DATE)
            _pending.pop(key, None)
            await query.answer()
            return
    except TMDbError:
        rid = uuid.uuid4().hex[:8].upper()
        logging.error("/add callback tmdb_error id=%s", rid)
        await query.message.reply_text(t("tech_error", lang=lang, rid=rid))
        _pending.pop(key, None)
        await query.answer()
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add callback unexpected_tmdb_error id=%s", rid)
        await query.message.reply_text(t("tech_error", lang=lang, rid=rid))
        _pending.pop(key, None)
        await query.answer()
        return

    existing = await get_movie_by_tmdb_id(tmdb_id)
    if existing:
        short_id, title, year = existing
        await query.message.reply_text(t("duplicate", lang=lang, short_id=short_id, title=title, year=year))
        _pending.pop(key, None)
        await query.answer()
        return

    try:
        new_id = await db.insert_movie(
            title=details.title,
            year=details.year,
            genres=details.genres,
            tmdb_id=details.tmdb_id,
        )
    except DuplicateTmdbError:
        existing = await get_movie_by_tmdb_id(tmdb_id)
        if existing:
            short_id, title, year = existing
            await query.message.reply_text(
                t("duplicate", lang=lang, short_id=short_id, title=title, year=year)
            )
        else:
            await query.message.reply_text(
                t("duplicate", lang=lang, short_id="", title=details.title, year=details.year)
            )
        _pending.pop(key, None)
        await query.answer()
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add callback db_error id=%s", rid)
        await query.message.reply_text(t("tech_error", lang=lang, rid=rid))
        _pending.pop(key, None)
        await query.answer()
        return

    genres_text = details.genres if details.genres else "жанры не указаны"
    if details.genres and details.genres_lang and details.genres_lang != config.LANG_FALLBACKS[0]:
        genres_text = f"{genres_text} ({details.genres_lang})"
    short_id = to_short_id(new_id)
    await query.message.reply_text(
        t(
            "add_success",
            lang=lang,
            short_id=short_id,
            title=details.title,
            year=details.year,
            genres=genres_text,
        )
    )
    mode = "confirm_year" if pending.get("confirm_year") else "confirm"
    logging.info(
        "/add mode=%s tmdb_id=%s year=%s id=%s",
        mode,
        details.tmdb_id,
        details.year,
        new_id,
    )
    _pending.pop(key, None)
    try:
        await schedule_export(context.job_queue)
    except Exception:
        logging.exception("export schedule failed")
    await query.answer()
