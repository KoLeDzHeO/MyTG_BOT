import logging
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from src.config import TELEGRAM_TOKEN, ALLOWED_CHAT_IDS
from src.handlers import make_handlers

logging.basicConfig(level=logging.INFO)


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

def build_app():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("8ball", eightball))
    app.add_handler(CommandHandler("ban", fake_ban))
    for h in make_handlers():
        app.add_handler(h)
    return app


if __name__ == "__main__":
    app = build_app()
    app.run_polling(drop_pending_updates=True)
