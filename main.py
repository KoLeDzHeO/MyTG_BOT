import logging
import uuid
import json
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import config
from src.handlers.gpt_handler import gpt_handler, id_handler, start_handler
from src.utils.text_utils import mask


async def _post_init(app: Application) -> None:
    logging.info("delete webhook")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning("webhook clear err %s", mask(str(e)))
    app.bot_data["webhook_ok"] = False
    if config.WEBHOOK_URL and config.WEBHOOK_SECRET:
        try:
            url = f"{config.WEBHOOK_URL.rstrip('/')}/{config.WEBHOOK_SECRET}"
            await app.bot.set_webhook(
                url=url,
                secret_token=config.WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
            app.bot_data["webhook_ok"] = True
            logging.info("webhook set ok")
        except Exception as e:
            logging.error("webhook set err %s", mask(str(e)))


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
    logging.exception("Unhandled error [%s]: %s", rid, context.error)
    try:
        if update and getattr(update, "effective_chat", None):
            await context.bot.send_message(update.effective_chat.id, f"⚠️ Ошибка (id={rid}). Попробуй ещё раз.")
        if config.LOG_CHAT_ID:
            await context.bot.send_message(config.LOG_CHAT_ID, f"❌ Error {rid}: {context.error}")
    except Exception:
        pass


def main() -> None:
    _make_logger()
    app = Application.builder().token(config.TELEGRAM_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("id", id_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_handler))

    app.add_error_handler(on_error)

    logging.info("config ok: webhook=%s require_prefix=%s", 
                 bool(config.WEBHOOK_URL and config.WEBHOOK_SECRET), config.REQUIRE_PREFIX)

    if config.WEBHOOK_URL and config.WEBHOOK_SECRET and app.bot_data.get("webhook_ok") is True:
        logging.info("webhook mode")
        app.run_webhook(
            listen="0.0.0.0",
            port=config.PORT,
            url_path=config.WEBHOOK_SECRET,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
    else:
        logging.info("polling")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

