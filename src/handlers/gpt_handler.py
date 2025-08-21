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
    OPENAI_MODEL,
    OPENAI_MODEL_FULL,
    OPENAI_MAX_OUTPUT_TOKENS,
    OPENAI_MAX_OUTPUT_TOKENS_FULL,
    OPENAI_API_KEY,
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
    text = (
        "Использование GPT:\n"
        " .<вопрос> — быстрый ответ (gpt-4o-mini, до 400 токенов)\n"
        " ..<вопрос> — подробный ответ (gpt-4o, до 600 токенов)\n"
        " /ask <вопрос> — то же, что '.'; если текст начинается с '..', то полный режим\n"
        "\nПрочее:\n"
        " /coin — орёл/решка\n"
        " /8ball — магический шар\n"
        " /ban — фейк-бан"
    )
    await update.message.reply_text(text)


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command."""
    if not _allowed(update.effective_chat.id):
        return
    text = " ".join(ctx.args).strip()
    if not text:
        await update.message.reply_text("Использование: /ask <вопрос>")
        return
    model = OPENAI_MODEL
    max_tokens = OPENAI_MAX_OUTPUT_TOKENS
    if text.startswith(".."):
        model = OPENAI_MODEL_FULL
        max_tokens = OPENAI_MAX_OUTPUT_TOKENS_FULL
        text = text[2:].lstrip()
    update.message.text = text
    await ask(update, ctx, model, max_tokens)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id):
        return
    text = update.message.text or ""
    model = max_tokens = None
    cleaned = ""
    if text.startswith(".."):
        model = OPENAI_MODEL_FULL
        max_tokens = OPENAI_MAX_OUTPUT_TOKENS_FULL
        cleaned = text[2:]
    elif text.startswith('.'):
        model = OPENAI_MODEL
        max_tokens = OPENAI_MAX_OUTPUT_TOKENS
        cleaned = text[1:]
    else:
        return
    update.message.text = cleaned.lstrip()
    await ask(update, ctx, model, max_tokens)

async def ask(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    model: str,
    max_tokens: int,
):
    chat_id = update.effective_chat.id
    if not _allowed(chat_id):
        return
    now = time.time()
    if now - _chat_cooldown[chat_id] < COOLDOWN_SECONDS:
        return  # антиспам

    user_q = (update.message.text or "").strip()
    if not user_q:
        await update.message.reply_text("Напиши что-то после точки.")
        return
    if len(user_q) > MAX_PROMPT_CHARS:
        user_q = user_q[:MAX_PROMPT_CHARS]

    history = "\n".join(_chat_context[chat_id])
    prompt = (history + "\n" if history else "") + user_q
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[-MAX_PROMPT_CHARS:]

    log.info("model=%s input_len=%d max_tokens=%d", model, len(user_q), max_tokens)
    msg = await update.message.reply_text("Думаю… ⏳")
    try:
        answer = await ask_gpt(prompt, model=model, max_tokens=max_tokens)
        log.info("response_len=%d", len(answer))
        _chat_context[chat_id].append(f"Q: {user_q}")
        _chat_context[chat_id].append(f"A: {answer[:500]}")
        for chunk in split_message(answer, MAX_REPLY_CHARS):
            await ctx.bot.send_message(chat_id=chat_id, text=chunk)
    except Exception as e:
        err_msg = str(e)
        if OPENAI_API_KEY:
            err_msg = err_msg.replace(OPENAI_API_KEY, "[TOKEN]")
        log.exception("OpenAI error: %s", err_msg)
        await update.message.reply_text(f"❗ GPT ошибка: {err_msg}")
    finally:
        _chat_cooldown[chat_id] = time.time()
        await msg.delete()

def get_handlers():
    return [
        CommandHandler("help", cmd_help),
        CommandHandler("ask", cmd_ask),
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message),
    ]
