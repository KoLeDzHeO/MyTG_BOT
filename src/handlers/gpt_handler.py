import logging
import uuid
import time
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from telegram.error import BadRequest

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
    rid = str(uuid.uuid4())[:8]
    t0 = time.time()
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

        logging.info("rid=%s start model=%s prompt_len=%d", rid, model, len(clean_text))
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
        if not chunks:
            chunks = [answer or ""]  # страховка
        try:
            msg = await update.message.reply_text(as_html(chunks[0]), parse_mode="HTML")
        except BadRequest:
            msg = await update.message.reply_text(chunks[0])  # plain-text fallback
        except Exception:
            try:
                msg = await update.message.reply_text(chunks[0])
            except Exception:
                msg = None

        for ch in chunks[1:]:
            if msg is None:
                # если первое сообщение не отправилось — сразу шлём новые чанки
                await update.message.reply_text(ch)
                continue
            try:
                await msg.edit_text(as_html(ch), parse_mode="HTML")
            except BadRequest:
                await update.message.reply_text(ch)  # plain-text fallback
            except Exception:
                try:
                    await update.message.reply_text(ch)
                except Exception:
                    pass
        logging.info(
            "rid=%s done in=%.2fs answer_len=%d chunks=%d",
            rid,
            time.time() - t0,
            len(answer),
            len(chunks),
        )

    except Exception as e:
        logging.exception("rid=%s gpt_handler error: %s", rid, e)
        try:
            await update.message.reply_text("⚠️ Произошла ошибка. Попробуй ещё раз, я уже смотрю логи.")
        except Exception:
            pass
