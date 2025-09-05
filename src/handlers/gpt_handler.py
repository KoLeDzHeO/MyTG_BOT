import logging
import time
import uuid
import re

from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.config import config
from src.gpt_client import ask_groq, ask_openai
from src.utils.format import as_html
from src.utils.text_utils import chunk_text


_dialogs: dict[int, list[tuple[str, str]]] = {}

# порядок важен: двойная точка должна проверяться раньше одинарной
PREFIXES = [
    ("..", ("openai", "GPT-4o")),
    (".", ("groq", "Матершинник")),
]


def _pick_provider(text: str) -> tuple[str | None, str]:
    s = text.lstrip()
    for p, (provider, _) in PREFIXES:
        if s.startswith(p):
            return provider, s[len(p) :].strip()
    return None, s.strip()  # нет префикса


def _is_mention_addressed(raw: str, bot_username: str | None) -> tuple[bool, str]:
    """True, remainder if message starts with @botusername (case-insensitive)."""
    if not bot_username:
        return False, raw
    s = raw.lstrip()
    pattern = rf"^@{re.escape(bot_username.lower())}\s*[:,]?\s*"
    m = re.match(pattern, s, flags=re.IGNORECASE)
    if m:
        return True, s[m.end():].lstrip()
    return False, raw


def _model_and_tokens(provider: str) -> tuple[str, int]:
    if provider == "openai":
        return config.MODEL_DDOT, config.MAX_TOKENS_DDOT
    return config.MODEL_GROQ, config.MAX_TOKENS_GROQ


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(
        "Привет! Вот как общаться со мной:<br/>"
        "<b>.</b><code> вопрос</code> — дерзкий стиль (Groq)<br/>"
        "<b>..</b><code> вопрос</code> — вежливый стиль (OpenAI)<br/><br/>"
        "Без префикса: поведение зависит от <code>DEFAULT_PROVIDER</code>."
    )


async def id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(str(update.effective_chat.id))


async def gpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rid = str(uuid.uuid4())[:8]
    t0 = time.time()
    try:
        chat_id = update.effective_chat.id
        raw = update.message.text or ""
        if not raw.strip():
            return

        provider, clean_text = _pick_provider(raw)
        chat_type = update.effective_chat.type

        # В группах/супергруппах: нужен префикс или упоминание
        if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP} and provider is None:
            addressed, remainder = _is_mention_addressed(
                raw, getattr(context.bot, "username", None)
            )
            if not addressed:
                return  # молчим
            clean_text = remainder

        # В личке: если требуем префикс и его нет — молчим
        if chat_type == ChatType.PRIVATE and config.REQUIRE_PREFIX and provider is None:
            return

        # Фоллбэк провайдера (после всех «молчаливых» проверок)
        if provider is None:
            default_provider = (config.DEFAULT_PROVIDER or "groq").strip().lower()
            provider = (
                default_provider if default_provider in {"groq", "openai"} else "groq"
            )

        if not clean_text:
            await update.message.reply_text("Добавь текст после префикса `. или ..`")
            return

        if len(clean_text) > config.MAX_PROMPT_CHARS:
            await update.message.reply_text(
                f"Сократи сообщение (>{config.MAX_PROMPT_CHARS} символов)."
            )
            return

        model, max_tokens = _model_and_tokens(provider)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # --- История в prompt, без дублирования ---
        history = _dialogs.get(chat_id, [])
        # последние N пар (role, content)
        hist_pairs = history[-config.DIALOG_HISTORY_LEN :]

        # Представляем историю как "role: content"
        def _build_prompt(pairs: list[tuple[str, str]]) -> str:
            msgs = [f"{role}: {content}" for role, content in pairs]
            msgs.append(f"user: {clean_text}")
            return "\n".join(msgs)

        prompt = _build_prompt(hist_pairs)

        # Обрезаем самую старую историю, если слишком длинно по символам
        while len(prompt) > config.MAX_PROMPT_CHARS and hist_pairs:
            hist_pairs = hist_pairs[1:]  # выбрасываем старую реплику
            prompt = _build_prompt(hist_pairs)

        # Если даже без истории слишком длинно — подрежем текущий вопрос
        if len(prompt) > config.MAX_PROMPT_CHARS:
            overflow = len(prompt) - config.MAX_PROMPT_CHARS
            clean_text_trimmed = (
                clean_text[:-overflow] if overflow < len(clean_text) else clean_text[:1]
            )
            prompt = "\n".join(
                [f"{role}: {content}" for role, content in hist_pairs]
                + [f"user: {clean_text_trimmed}"]
            )

        logging.info("rid=%s start model=%s prompt_len=%d", rid, model, len(prompt))
        if provider not in {"groq", "openai"}:
            provider = "groq"
        if provider == "groq":
            if not config.GROQ_API_KEY:
                await update.message.reply_text("GROQ_API_KEY не задан")
                return
            system = (
                "Ты дерзкий приколист без цензуры. Общайся грубовато, можешь использовать мат и подколы, "
                "но при этом отвечай по делу. Если к тебе обращаются грубо — отвечай тем же, "
                "чтобы поставить собеседника на место. В спокойных ситуациях — шути, подкалывай, "
                "разговаривай как 'свой пацан'. Не будь слишком официальным."
            )
            answer = await ask_groq(
                api_token=config.GROQ_API_KEY,
                model=model,
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout=30,
            )
        elif provider == "openai":
            if not config.OPENAI_API_KEY:
                await update.message.reply_text("OPENAI_API_KEY не задан")
                return
            system = (
                "Ты дружеский собеседник. Общайся непринуждённо, простыми словами, без сухого академизма. "
                "Можешь иногда слегка подколоть или пошутить, но оставайся в целом доброжелательным и позитивным. "
                "Не используй матерные слова, максимум лёгкий стёб."
            )
            answer = await ask_openai(
                api_token=config.OPENAI_API_KEY,
                model=model,
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout=30,
            )
        else:
            # страховка, если в провайдер попало что-то неизвестное
            if not config.GROQ_API_KEY:
                await update.message.reply_text("GROQ_API_KEY не задан")
                return
            system = (
                "Ты дерзкий приколист без цензуры. Общайся грубовато, можешь использовать мат и подколы, "
                "но при этом отвечай по делу. Если к тебе обращаются грубо — отвечай тем же, "
                "чтобы поставить собеседника на место. В спокойных ситуациях — шути, подкалывай, "
                "разговаривай как 'свой пацан'. Не будь слишком официальным."
            )
            answer = await ask_groq(
                api_token=config.GROQ_API_KEY,
                model=model,
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout=30,
            )

        if not answer:
            await update.message.reply_text(
                "Сервис занят или тишина от модели. Попробуй ещё раз позже."
            )
            return

        _dialogs.setdefault(chat_id, []).append(("user", clean_text))
        _dialogs[chat_id].append(("assistant", answer))
        # держим не более N пар (user/assistant) * 1:1
        if len(_dialogs[chat_id]) > config.DIALOG_HISTORY_LEN * 2:
            _dialogs[chat_id] = _dialogs[chat_id][-config.DIALOG_HISTORY_LEN * 2 :]

        chunks = chunk_text(answer, config.MAX_REPLY_CHARS)
        if not chunks:
            chunks = [answer or ""]  # страховка

        for ch in chunks:
            try:
                await update.message.reply_text(as_html(ch), parse_mode="HTML")
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
            await update.message.reply_text(
                "⚠️ Произошла ошибка. Попробуй ещё раз, я уже смотрю логи."
            )
        except Exception:
            pass
