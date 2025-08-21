import time
import logging
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler

from ..config import (
    MAX_REPLY_CHARS,
    MAX_PROMPT_CHARS,
    CONTEXT_TURNS,
    COOLDOWN_SECONDS,
    ALLOWED_CHAT_IDS,
)
from ..utils.text_utils import split_message
from ..gpt_client import ask_gpt

log = logging.getLogger(__name__)

_chat_cooldown = defaultdict(lambda: 0.0)  # chat_id -> timestamp
_chat_context = defaultdict(lambda: deque(maxlen=CONTEXT_TURNS * 2))  # Q/A pairs

def _allowed(chat_id: int) -> bool:
    return (not ALLOWED_CHAT_IDS) or (chat_id in ALLOWED_CHAT_IDS)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id):
        return
    text = ".<вопрос> — спросить GPT\n/coin — орёл/решка\n/8ball — магический шар\n/ban — фейк-бан"
    await update.message.reply_text(text)

async def ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not _allowed(chat_id):
        return
    now = time.time()
    if now - _chat_cooldown[chat_id] < COOLDOWN_SECONDS:
        return  # антиспам

    text = update.message.text or ""
    if not text.startswith('.'):
        return
    user_q = text[1:].strip()
    if not user_q:
        await update.message.reply_text("Напиши что-то после точки.")
        return
    if len(user_q) > MAX_PROMPT_CHARS:
        user_q = user_q[:MAX_PROMPT_CHARS]

    history = "\n".join(list(_chat_context[chat_id]))
    prompt = (history + "\n" if history else "") + user_q
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[-MAX_PROMPT_CHARS:]  # хвост диалога

    msg = await update.message.reply_text("Думаю… ⏳")
    try:
        answer = ask_gpt(prompt)
    except Exception as e:
        log.exception("OpenAI error")
        answer = f"Упс. Ошибка запроса к модели: {e}"

    _chat_context[chat_id].append(f"Q: {user_q}")
    _chat_context[chat_id].append(f"A: {answer[:500]}")

    for chunk in split_message(answer, MAX_REPLY_CHARS):
        await ctx.bot.send_message(chat_id=chat_id, text=chunk)

    await msg.delete()
    _chat_cooldown[chat_id] = time.time()

def get_handlers():
    return [
        CommandHandler("help", cmd_help),
        MessageHandler(filters.TEXT & (~filters.COMMAND), ask),
    ]
