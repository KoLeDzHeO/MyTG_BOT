import logging
import time
import uuid

from telegram import Update
from telegram.constants import ChatAction
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


def _model_and_tokens(provider: str) -> tuple[str, int]:
    if provider == "openai":
        return config.MODEL_DDOT, config.MAX_TOKENS_DDOT
    return config.GROQ_MODEL, config.MAX_TOKENS_GROQ


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
        if config.REQUIRE_PREFIX and provider is None:
            # В режиме REQUIRE_PREFIX=true бот полностью молчит на сообщения без префикса
            return

        if provider is None:
            default_provider = (config.DEFAULT_PROVIDER or "groq").strip().lower()
            if default_provider not in {"groq", "openai"}:
                default_provider = "groq"
            provider = default_provider

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
                "Ты бот без цензуры. Отвечай грубо, с матом, но при этом логично и по делу. "
                "Поддерживай стиль общения как у грубого собеседника."
                "Используй матюки, не жалей их, используй что то в стиле ты пидорас и так далее."
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
                "Ты вежливый помощник. Отвечай развёрнуто и структурированно, "
                "сохраняя стиль академичного ассистента."
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
                "Ты бот без цензуры. Отвечай грубо, с матом, но при этом логично и по делу. "
                "Поддерживай стиль общения как у грубого собеседника."
                "Используй матюки, не жалей их, используй что то в стиле ты пидорас и так далее."
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
