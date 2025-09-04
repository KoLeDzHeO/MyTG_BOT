import logging
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from src import db
from src.config import config
from src.i18n import t
from src.utils.text_utils import mask
from src.utils.ids import to_short_id
from src.movies.constants import icon

TELEGRAM_LIMIT = 4000


async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    rid = str(uuid.uuid4())[:8]
    try:
        lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
        total, rows = await db.get_last_movies(30)
        if total == 0:
            await update.message.reply_text(t("list_empty", lang=lang))
            logging.info("/list count_total=0 shown=0")
            return

        lines = [
            f"{icon(status)} {to_short_id(mid)} — {title} ({year})"
            for mid, title, year, status in rows
        ]

        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = line if not current else f"{current}\n{line}"
            if len(candidate) > TELEGRAM_LIMIT:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

        for ch in chunks:
            await update.message.reply_text(ch)

        if total > 30:
            if config.MEGA_URL:
                await update.message.reply_text(
                    t("list_archive", lang=lang, url=config.MEGA_URL)
                )
            else:
                logging.warning("/list archive_link_missing total=%d", total)

        logging.info("/list count_total=%d shown=%d", total, len(rows))
    except Exception as e:
        logging.exception("/list rid=%s: %s", rid, mask(str(e)))
        try:
            await update.message.reply_text(
                f"⚠️ Ошибка (id={rid}). Попробуй ещё раз."
            )
            if config.LOG_CHAT_ID:
                await context.bot.send_message(
                    config.LOG_CHAT_ID, f"❌ Error {rid}: {mask(str(e))}"
                )
        except Exception:
            pass
