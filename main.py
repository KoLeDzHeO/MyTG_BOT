import json
import logging
import uuid
from importlib import import_module

from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from src.core.config import config
from src.handlers.gpt import gpt_handler, id_handler, start_handler
from src.handlers.add import add_handler
from src.handlers.add_callback import add_callback_handler
from src.handlers.list import list_handler
from src.handlers.help import help_handler
from src.handlers.done import done_handler
from src.handlers.insta import link_handler, insta_handler
from src.handlers.insta_unfurl import insta_unfurl_handler
from src.core import db
del_handler = import_module("src.handlers.del").del_handler
from src.clients.tmdb import TMDbAuthError, TMDbError, tmdb_client
from src.utils.text import mask

VERSION = "1.0.0"


def _make_logger():
    if config.LOG_FORMAT == "json":

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "level": record.levelname,
                    "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "name": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_record["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(log_record, ensure_ascii=False)

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )


async def on_error(update, context):
    rid = str(uuid.uuid4())[:8]
    logging.exception("Unhandled error [%s]: %s", rid, mask(str(context.error)))
    try:
        if update and getattr(update, "effective_chat", None):
            await context.bot.send_message(
                update.effective_chat.id, f"⚠️ Ошибка (id={rid}). Попробуй ещё раз."
            )
        if config.LOG_CHAT_ID:
            await context.bot.send_message(
                config.LOG_CHAT_ID, f"❌ Error {rid}: {mask(str(context.error))}"
            )
    except Exception:
        pass


def main() -> None:
    _make_logger()
    async def on_startup(app):
        await db.init()
        try:
            await tmdb_client.check_key()
        except TMDbAuthError:
            logging.error("TMDb key invalid")
            raise SystemExit("TMDb key invalid")
        except TMDbError:
            logging.error("TMDb check failed")
            raise SystemExit("TMDb check failed")
        logging.info(
            "Bot started v%s languages=%s DB=ok TMDb=ok JobQueue=ok",
            VERSION,
            ",".join(config.LANG_FALLBACKS),
        )

    async def on_shutdown(app):
        db_status = "ok"
        tmdb_status = "ok"
        try:
            await db.close()
        except Exception as e:
            logging.error("Shutdown: closing DB failed: %s", e)
            db_status = "error"
        try:
            await tmdb_client.aclose()
        except Exception as e:
            logging.error("Shutdown: closing TMDb failed: %s", e)
            tmdb_status = "error"
        logging.info(
            "Shutdown: closing DB... %s; closing TMDb... %s", db_status, tmdb_status
        )

    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(on_startup)
        .post_stop(on_shutdown)
        .build()
    )
    app.job_queue.scheduler
    logging.info("JobQueue=ok")

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("id", id_handler))
    app.add_handler(CommandHandler("add", add_handler))
    app.add_handler(CommandHandler("list", list_handler))
    app.add_handler(CommandHandler("done", done_handler))
    app.add_handler(CommandHandler("del", del_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("link", link_handler))
    app.add_handler(CommandHandler("insta", insta_handler))
    app.add_handler(CallbackQueryHandler(add_callback_handler, pattern=r"^ADD_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Entity("url"), insta_unfurl_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_handler))

    app.add_error_handler(on_error)

    logging.info("config ok: webhook=False require_prefix=%s", config.REQUIRE_PREFIX)
    logging.info("polling")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
