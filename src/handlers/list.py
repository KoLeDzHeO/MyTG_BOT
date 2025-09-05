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

# ⏱ TTL берём из конфига: config.LIST_TTL_SECONDS (секунды авто-удаления /list)
TTL_SECONDS = config.LIST_TTL_SECONDS


async def _delete_messages_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет ранее отправленные сообщения /list по истечении TTL."""
    try:
        job = context.job  # type: ignore[attr-defined]
        data = getattr(job, "data", {}) or {}
        chat_id = data.get("chat_id")
        ids: list[int] = data.get("message_ids") or []
        if not chat_id or not ids:
            return
        for mid in ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception as e:
                logging.debug("list TTL delete failed chat=%s msg=%s err=%s", chat_id, mid, e)
    except Exception as e:
        logging.debug("list TTL job error: %s", e)


async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    rid = str(uuid.uuid4())[:8]
    chat_id = update.effective_chat.id
    try:
        lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
        total, rows = await db.get_last_movies(30)
        if total == 0:
            msg = await update.message.reply_text(t("list_empty", lang=lang))
            logging.info("/list count_total=0 shown=0")
            return

        lines = [
            f"{icon(status)} {to_short_id(mid)} — {title} ({year})"
            for (mid, title, year, status, _genres) in rows
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

        sent_ids: list[int] = []
        for ch in chunks:
            m = await update.message.reply_text(ch)
            sent_ids.append(m.message_id)

        if total > 30:
            if config.MEGA_URL:
                m = await update.message.reply_text(
                    t("list_archive", lang=lang, url=config.MEGA_URL)
                )
                sent_ids.append(m.message_id)
            else:
                logging.warning("/list archive_link_missing total=%d", total)

        # Планируем авто-удаление всех отправленных сообщений через TTL_SECONDS
        # 🗑 Через config.LIST_TTL_SECONDS можно регулировать интервал удаления (см. src/config.py)
        context.job_queue.run_once(
            _delete_messages_job,
            when=TTL_SECONDS,
            data={"chat_id": chat_id, "message_ids": sent_ids},
            name=f"list_ttl_{chat_id}_{rid}",
        )

        logging.info("/list count_total=%d shown=%d", total, len(rows))
    except Exception as e:
        logging.exception("/list rid=%s: %s", rid, mask(str(e)))
        try:
            await update.message.reply_text(
                f"⚠️ Ошибка (id={rid}). Попробуй ещё раз."
            )
            log_chat_id = getattr(config, "LOG_CHAT_ID", None)
            if log_chat_id:
                await context.bot.send_message(
                    log_chat_id, f"❌ Error {rid}: {mask(str(e))}"
                )
        except Exception:
            pass

