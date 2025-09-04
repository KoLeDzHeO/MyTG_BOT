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
from .add import _pending, NO_DATE, _schedule_auto_delete


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
        try:
            await context.bot.delete_message(chat_id, query.message.message_id)
        except Exception:
            logging.warning(
                "/add cleanup delete_denied msg_id=%s", query.message.message_id
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=query.message.message_id,
                    text=t("timeout", lang=lang, query=pending["query"]),
                    reply_markup=None,
                )
            except Exception:
                logging.warning(
                    "/add cleanup edit_failed msg_id=%s", query.message.message_id
                )
        if config.CLEANUP_NOTICE_SECONDS > 0:
            notice = await context.bot.send_message(
                chat_id, t("timeout", lang=lang, query=pending["query"])
            )
            _schedule_auto_delete(
                context.job_queue, chat_id, notice.message_id
            )
        logging.info(
            "/add cleanup reason=timeout msg_id=%s", query.message.message_id
        )
        await query.answer()
        return

    if data == "ADD_CANCEL":
        _pending.pop(key, None)
        try:
            await context.bot.delete_message(chat_id, query.message.message_id)
        except Exception:
            logging.warning(
                "/add cleanup delete_denied msg_id=%s", query.message.message_id
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=query.message.message_id,
                    text=t("cancelled", lang=lang),
                    reply_markup=None,
                )
            except Exception:
                logging.warning(
                    "/add cleanup edit_failed msg_id=%s", query.message.message_id
                )
        logging.info(
            "/add cleanup reason=cancel msg_id=%s", query.message.message_id
        )
        if config.CLEANUP_NOTICE_SECONDS > 0:
            notice = await context.bot.send_message(chat_id, t("cancelled", lang=lang))
            _schedule_auto_delete(
                context.job_queue, chat_id, notice.message_id
            )
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

    _pending.pop(key, None)
    try:
        await context.bot.delete_message(chat_id, query.message.message_id)
    except Exception:
        logging.warning(
            "/add cleanup delete_denied msg_id=%s", query.message.message_id
        )
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=query.message.message_id,
                text=query.message.text,
                reply_markup=None,
            )
        except Exception:
            logging.warning(
                "/add cleanup edit_failed msg_id=%s", query.message.message_id
            )
    logging.info(
        "/add cleanup reason=picked msg_id=%s", query.message.message_id
    )

    try:
        details = await tmdb_client.get_movie_details(tmdb_id)
        if not details:
            await context.bot.send_message(chat_id, NO_DATE)
            await query.answer()
            return
    except TMDbError:
        rid = uuid.uuid4().hex[:8].upper()
        logging.error("/add callback tmdb_error id=%s", rid)
        await context.bot.send_message(chat_id, t("tech_error", lang=lang, rid=rid))
        await query.answer()
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add callback unexpected_tmdb_error id=%s", rid)
        await context.bot.send_message(chat_id, t("tech_error", lang=lang, rid=rid))
        await query.answer()
        return

    existing = await get_movie_by_tmdb_id(tmdb_id)
    if existing:
        short_id, title, year = existing
        await context.bot.send_message(
            chat_id,
            t("duplicate", lang=lang, short_id=short_id, title=title, year=year),
        )
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
            await context.bot.send_message(
                chat_id,
                t("duplicate", lang=lang, short_id=short_id, title=title, year=year),
            )
        else:
            await context.bot.send_message(
                chat_id,
                t(
                    "duplicate",
                    lang=lang,
                    short_id="",
                    title=details.title,
                    year=details.year,
                ),
            )
        await query.answer()
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add callback db_error id=%s", rid)
        await context.bot.send_message(
            chat_id, t("tech_error", lang=lang, rid=rid)
        )
        await query.answer()
        return

    genres_text = details.genres if details.genres else "жанры не указаны"
    if details.genres and details.genres_lang and details.genres_lang != config.LANG_FALLBACKS[0]:
        genres_text = f"{genres_text} ({details.genres_lang})"
    short_id = to_short_id(new_id)
    await context.bot.send_message(
        chat_id,
        t(
            "add_success",
            lang=lang,
            short_id=short_id,
            title=details.title,
            year=details.year,
            genres=genres_text,
        ),
    )
    mode = "confirm_year" if pending.get("confirm_year") else "confirm"
    logging.info(
        "/add strict year mode=%s tmdb_id=%s year=%s id=%s",
        mode,
        details.tmdb_id,
        details.year,
        new_id,
    )
    try:
        await schedule_export(context.job_queue)
    except Exception:
        logging.exception("export schedule failed")
    await query.answer()
