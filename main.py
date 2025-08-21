import logging
import os
import sys
import platform
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from src.config import (
    TELEGRAM_TOKEN, ALLOWED_CHAT_IDS, OPENAI_API_KEY, LOG_LEVEL,
    USE_WEBHOOK, WEBHOOK_URL, WEBHOOK_SECRET, PORT
)
from src.handlers import get_handlers
from src.gpt_client import client_diagnostics
from src.handlers.gpt_handler import gpt_handler_info
from src.handlers.trigger_handler import triggers_info

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


def allowed(chat_id: int) -> bool:
    return not ALLOWED_CHAT_IDS or chat_id in ALLOWED_CHAT_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id):
        return
    await update.message.reply_text("Я здесь. Используй:\n· `.вопрос` — быстрый ответ\n· `..вопрос` — подробный ответ\n/help — справка")


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id):
        return
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")


async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id):
        return
    await update.message.reply_text("🪙 Орёл" if random.random() < 0.5 else "🪙 Решка")


async def eightball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id):
        return
    answers = [
        "Да", "Нет", "Скорее да", "Скорее нет",
        "Спроси позже", "Шансы малы", "Определённо да", "Туманно, но похоже на нет"
    ]
    await update.message.reply_text(f"🔮 {random.choice(answers)}")


async def fake_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id):
        return
    if update.message.reply_to_message:
        name = update.message.reply_to_message.from_user.first_name or "Этот гражданин"
    elif context.args:
        name = " ".join(context.args)
    else:
        name = "Неустановленный элемент"
    await update.message.reply_text(f"🚫 {name} отправлен(а) в объятия модерации... шутка 😉")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = str(context.error)
    if TELEGRAM_TOKEN:
        err = err.replace(TELEGRAM_TOKEN, "[TOKEN]")
    if OPENAI_API_KEY:
        err = err.replace(OPENAI_API_KEY, "[KEY]")
    logging.exception("Unhandled exception: %s", err, exc_info=context.error)


async def _post_init(app):
    # Чистим вебхук всегда; при USE_WEBHOOK поставим заново
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logging.getLogger("startup").info("Webhook cleared (drop_pending_updates=True)")
    except Exception as e:
        logging.getLogger("startup").warning("Failed to clear webhook: %s", e)
    if USE_WEBHOOK:
        if not WEBHOOK_URL or not WEBHOOK_SECRET:
            logging.getLogger("startup").error("USE_WEBHOOK=true, но WEBHOOK_URL/WEBHOOK_SECRET не заданы")
        else:
            try:
                await app.bot.set_webhook(
                    url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET}",
                    secret_token=WEBHOOK_SECRET,
                    drop_pending_updates=True,
                    allowed_updates=None,
                )
                logging.getLogger("startup").info("Webhook set to %s/<secret>", WEBHOOK_URL)
            except Exception as e:
                logging.getLogger("startup").error("Failed to set webhook: %s", e)


def startup_diagnostics():
    import telegram
    log = logging.getLogger("startup")
    log.info("=== Startup diagnostics ===")
    log.info("Python=%s PTB=%s OpenAI=%s",
             sys.version.split()[0], getattr(telegram, "__version__", "unknown"),
             client_diagnostics().get("openai_version"))
    ci = client_diagnostics()
    log.info("Models mini=%s(%s) full=%s(%s)",
             ci.get("model_mini"), os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "400"),
             ci.get("model_full"), os.getenv("OPENAI_MAX_OUTPUT_TOKENS_FULL", "600"))
    gi = gpt_handler_info()
    log.info("GPT handler: %s", {"context_turns": gi["context_turns"], "cooldown_seconds": gi["cooldown_seconds"]})
    ti = triggers_info()
    log.info("Triggers loaded: %d", ti.get("count", 0))
    log.info("Allowed chats: %s", "all" if not ALLOWED_CHAT_IDS else list(ALLOWED_CHAT_IDS))
    log.info("Config: {OPENAI_MODEL=%s, OPENAI_MODEL_FULL=%s, CONTEXT_TURNS=%s, COOLDOWN_SECONDS=%s, LOG_LEVEL=%s}",
             ci.get("model_mini"), ci.get("model_full"), gi["context_turns"], gi["cooldown_seconds"], LOG_LEVEL)
    log.info("USE_WEBHOOK=%s PORT=%s URL_set=%s SECRET_set=%s",
             USE_WEBHOOK, PORT, bool(WEBHOOK_URL), bool(WEBHOOK_SECRET))
    log.info("=== End diagnostics ===")


def build_app():
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("8ball", eightball))
    app.add_handler(CommandHandler("ban", fake_ban))
    for h in get_handlers():
        app.add_handler(h)
    app.add_error_handler(on_error)
    return app


if __name__ == "__main__":
    app = build_app()
    startup_diagnostics()
    if USE_WEBHOOK and WEBHOOK_URL and WEBHOOK_SECRET:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(PORT),
            url_path=WEBHOOK_SECRET,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True,
            allowed_updates=None,
        )
    else:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=None
        )

