import logging
import random
import platform
import telegram
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from src.config import (
    TELEGRAM_TOKEN,
    ALLOWED_CHAT_IDS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_MODEL_FULL,
    OPENAI_MAX_OUTPUT_TOKENS,
    OPENAI_MAX_OUTPUT_TOKENS_FULL,
    LOG_LEVEL,
)
from src.config import config_info
from src.handlers import get_handlers
from src.handlers.gpt_handler import gpt_handler_info
from src.handlers.trigger_handler import triggers_info
from src.gpt_client import client_diagnostics


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


def allowed(chat_id: int) -> bool:
    return not ALLOWED_CHAT_IDS or chat_id in ALLOWED_CHAT_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    await update.message.reply_text("Привет! Я ваш бот. Напиши /help")

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    await update.message.reply_text(f"🪙 {random.choice(['орёл', 'решка'])}")

async def eightball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    answers = [
        "Да", "Нет", "Скорее да", "Скорее нет",
        "Спроси позже", "Шансы малы", "Определённо да", "Туманно, но похоже на нет"
    ]
    await update.message.reply_text(f"🔮 {random.choice(answers)}")

async def fake_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    if update.message.reply_to_message:
        name = update.message.reply_to_message.from_user.first_name or "Этот гражданин"
    elif context.args:
        name = " ".join(context.args)
    else:
        name = "Неустановленный элемент"
    await update.message.reply_text(f"🚫 {name} отправлен(а) в объятия модерации... шутка 😉")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    def _mask(value: str | None) -> str:
        return value[:4] + "…" + value[-4:] if value else ""

    err = str(context.error)
    if TELEGRAM_TOKEN:
        err = err.replace(TELEGRAM_TOKEN, _mask(TELEGRAM_TOKEN))
    if OPENAI_API_KEY:
        err = err.replace(OPENAI_API_KEY, _mask(OPENAI_API_KEY))
    # Sanitize stack trace as well
    import traceback

    tb = "".join(
        traceback.format_exception(
            type(context.error), context.error, context.error.__traceback__
        )
    )
    if TELEGRAM_TOKEN:
        tb = tb.replace(TELEGRAM_TOKEN, _mask(TELEGRAM_TOKEN))
    if OPENAI_API_KEY:
        tb = tb.replace(OPENAI_API_KEY, _mask(OPENAI_API_KEY))
    logging.error("Unhandled exception: %s\n%s", err, tb)

def build_app():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("8ball", eightball))
    app.add_handler(CommandHandler("ban", fake_ban))
    for h in get_handlers():
        app.add_handler(h)
    app.add_error_handler(on_error)
    return app


def startup_diagnostics() -> None:
    log = logging.getLogger("startup")
    log.info(
        "Python=%s PTB=%s OpenAI=%s",
        platform.python_version(),
        telegram.__version__,
        openai.__version__,
    )
    log.info(
        "Models mini=%s(%d) full=%s(%d)",
        OPENAI_MODEL,
        OPENAI_MAX_OUTPUT_TOKENS,
        OPENAI_MODEL_FULL,
        OPENAI_MAX_OUTPUT_TOKENS_FULL,
    )
    log.info("Allowed chats: %s", ALLOWED_CHAT_IDS or "all")
    log.info("Triggers loaded: %d", triggers_info())
    log.info("GPT handler: %s", gpt_handler_info())
    log.info("Config: %s", config_info())
    client_diagnostics()


if __name__ == "__main__":
    app = build_app()
    startup_diagnostics()
    # Если получаете ошибку "Conflict: terminated by other",
    # убедитесь, что запущен только один инстанс бота.
    app.run_polling(drop_pending_updates=True)
