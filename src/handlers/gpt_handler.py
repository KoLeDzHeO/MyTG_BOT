import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.config import config
from src.gpt_client import ask_gpt
from src.utils.text_utils import chunk_text


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(". вопрос или .. вопрос")


async def id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(str(update.effective_chat.id))


async def gpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if text.startswith(".."):
        model = config.OPENAI_MODEL_FULL
        max_tokens = config.OPENAI_MAX_OUTPUT_TOKENS_FULL
        query = text[2:]
    elif text.startswith("."):
        model = config.OPENAI_MODEL
        max_tokens = config.OPENAI_MAX_OUTPUT_TOKENS
        query = text[1:]
    else:
        return
    query = query.strip()[: config.MAX_PROMPT_CHARS]
    thinking = await update.message.reply_text("Думаю…")
    answer = await ask_gpt(model, query, max_tokens)
    logging.info("model=%s in_len=%d out_len=%d", model, len(query), len(answer))
    if not answer.strip():
        parts = ["⚠️ GPT вернул пустой ответ."]
    else:
        parts = chunk_text(answer, config.MAX_REPLY_CHARS)
    for part in parts:
        await update.message.reply_text(part)
    try:
        await thinking.delete()
    except Exception:
        pass
