import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.config import config
from src.handlers.gpt_handler import gpt_handler, id_handler, start_handler
from src.utils.text_utils import mask


async def run() -> None:
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("id", id_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_handler))

    await app.bot.delete_webhook(drop_pending_updates=True)
    if config.WEBHOOK_URL and config.WEBHOOK_SECRET:
        try:
            await app.bot.set_webhook(
                url=f"{config.WEBHOOK_URL}/{config.WEBHOOK_SECRET}",
                secret_token=config.WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
            logging.info("webhook set")
            await app.run_webhook(
                listen="0.0.0.0",
                port=config.PORT,
                url_path=config.WEBHOOK_SECRET,
                secret_token=config.WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
            return
        except Exception as e:
            logging.error("webhook err %s", mask(str(e)))
    logging.info("polling")
    await app.run_polling(drop_pending_updates=True)


def main() -> None:
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    asyncio.run(run())


if __name__ == "__main__":
    main()
