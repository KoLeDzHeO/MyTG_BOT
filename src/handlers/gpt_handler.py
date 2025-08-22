import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from src.config import config
from src.gpt_client import ask_gpt
from src.utils.text_utils import chunk_text
from src.utils.ratelimit import WindowRateLimiter
from src.utils.format import as_html

_rate_limiter = WindowRateLimiter(config.RATE_LIMIT_PER_CHAT, config.RATE_LIMIT_INTERVAL)

PREFIX_MAP = {
    "..": ("ddot", "Полный"),
    ".":  ("dot",  "Короткий"),
}

def _pick_mode(text: str) -> tuple[str | None, str]:
    s = text.lstrip()
    for p, (mode, _) in PREFIX_MAP.items():
        if s.startswith(p):
            return mode, s[len(p):].strip()
    return None, s  # нет префикса

def _model_and_tokens(mode: str) -> tuple[str, int]:
    if mode == "ddot":
        return config.MODEL_DDOT, config.MAX_TOKENS_DDOT
    return config.MODEL_DOT, config.MAX_TOKENS_DOT

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет!\n"
        "Короткий режим: `. вопрос` (быстрее/дешевле).\n"
        "Полный режим: `.. вопрос` (умнее/длиннее).\n"
        "Команды: /start /id\n",
    )

async def id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(str(update.effective_chat.id))

async def gpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        if not text:
            return

        # Требуем префикс, если так указано в конфиге
        mode, clean_text = _pick_mode(text)
        if config.REQUIRE_PREFIX and mode is None:
            return  # игнор без ответа

        # Если префикс не обязателен и его нет — делаем короткий режим
        if mode is None:
            mode = "dot"

        if not _rate_limiter.allow(chat_id):
            await update.message.reply_text("Слишком часто. Попробуй через минутку 🙏")
            return

        if not clean_text:
            await update.message.reply_text("Добавь текст после префикса `. или ..`")
            return

        if len(clean_text) > config.MAX_PROMPT_CHARS:
            await update.message.reply_text(f"Сократи сообщение (>{config.MAX_PROMPT_CHARS} символов).")
            return

        model, max_tokens = _model_and_tokens(mode)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        system = (
            "Отвечай кратко и по делу. "
            "Сохраняй язык пользователя (русский/польский). "
            "Если вопрос двусмысленный — уточняй лаконично."
        )

        answer = await ask_gpt(
            api_key=config.OPENAI_API_KEY,
            model=model,
            system=system,
            prompt=clean_text,
            max_tokens=max_tokens,
            timeout=30,  # <= вернули 30 сек
        )

        if not answer:
            await update.message.reply_text("Сервис занят или тишина от модели. Попробуй ещё раз позже.")
            return

        chunks = chunk_text(answer, config.MAX_REPLY_CHARS)
        msg = await update.message.reply_text(as_html(chunks[0]), parse_mode="HTML")
        for ch in chunks[1:]:
            try:
                await msg.edit_text(as_html(ch), parse_mode="HTML")
            except Exception:
                await update.message.reply_text(as_html(ch), parse_mode="HTML")

    except Exception as e:
        logging.exception("gpt_handler error: %s", e)
        try:
            await update.message.reply_text("⚠️ Произошла ошибка. Попробуй ещё раз, я уже смотрю логи.")
        except Exception:
            pass
