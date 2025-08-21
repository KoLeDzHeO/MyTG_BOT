import os
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.environ["TELEGRAM_TOKEN"]

# (опционально) ограничить бота одной группой:
ALLOWED_CHAT_IDS = set()  # пример: {-1001234567890}

def allowed(chat_id: int) -> bool:
    return not ALLOWED_CHAT_IDS or chat_id in ALLOWED_CHAT_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    await update.message.reply_text("Привет! Я ваш бот. Напиши /help")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    await update.message.reply_text(
        "/id — показать ID чата\n"
        "/coin — орёл или решка\n"
        "/8ball <вопрос> — мудрый ответ 🔮\n"
        "/ban [@user|текст] — фейковый бан 😅"
    )

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
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("coin", coin))
    app.add_handler(CommandHandler("8ball", eightball))
    app.add_handler(CommandHandler("ban", fake_ban))
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling(drop_pending_updates=True)
