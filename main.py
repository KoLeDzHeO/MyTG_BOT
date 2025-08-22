import logging
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
            await app.bot.set_webhook(
                url=f"{config.WEBHOOK_URL}/{config.WEBHOOK_SECRET}",
                secret_token=config.WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
            logging.info("set webhook")
            app.bot_data["webhook_ok"] = True
        except Exception as e:
            logging.error("webhook err %s", mask(str(e)))

def main() -> None:
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("id", id_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_handler))
    if config.WEBHOOK_URL and config.WEBHOOK_SECRET and app.bot_data.get("webhook_ok"):
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
