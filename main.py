import asyncio
import json
import logging
import uuid

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import config
from src.handlers.gpt_handler import gpt_handler, id_handler, start_handler
from src.handlers.add import add_handler
from src import db
from src.tmdb_client import TMDbAuthError, TMDbError, tmdb_client
from src.utils.text_utils import mask

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
    asyncio.run(db.init())
    try:
        asyncio.run(tmdb_client.check_key())
    except TMDbAuthError:
        logging.error("TMDb key invalid")
        raise SystemExit("TMDb key invalid")
    except TMDbError:
        logging.error("TMDb check failed")
        raise SystemExit("TMDb check failed")
    logging.info(
        "Bot started v%s languages=%s DB=ok TMDb=ok",
        VERSION,
        ",".join(config.LANG_FALLBACKS),
    )
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("id", id_handler))
    app.add_handler(CommandHandler("add", add_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_handler))

    app.add_error_handler(on_error)

    logging.info("config ok: webhook=False require_prefix=%s", config.REQUIRE_PREFIX)
    logging.info("polling")
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        asyncio.run(db.close())
        asyncio.run(tmdb_client.aclose())


if __name__ == "__main__":
    main()
