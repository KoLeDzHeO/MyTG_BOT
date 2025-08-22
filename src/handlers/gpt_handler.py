import logging
import time
import uuid

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.config import config
from src.gpt_client import ask_gpt
from src.utils.format import as_html
from src.utils.text_utils import chunk_text

_dialogs: dict[int, list[tuple[str, str]]] = {}

PREFIX_MAP = {
    "..": ("ddot", "Полный"),
    ".": ("dot", "Короткий"),
}


def _pick_mode(text: str) -> tuple[str | None, str]:
    s = text.lstrip()
    for p, (mode, _) in PREFIX_MAP.items():
        if s.startswith(p):
            return mode, s[len(p) :].strip()
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

        if not clean_text:
            await update.message.reply_text("Добавь текст после префикса `. или ..`")
            return

        if len(clean_text) > config.MAX_PROMPT_CHARS:
            await update.message.reply_text(
                f"Сократи сообщение (>{config.MAX_PROMPT_CHARS} символов)."
            )
            return

        model, max_tokens = _model_and_tokens(mode)

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

        # Короткий system без истории
        system = (
            "Ты — помощник. Отвечай кратко и по делу. "
            "Сохраняй язык пользователя (русский/польский). "
            "Если вопрос двусмысленный — уточняй лаконично."
        )

        logging.info("rid=%s start model=%s prompt_len=%d", rid, model, len(prompt))
        answer = await ask_gpt(
            api_key=config.OPENAI_API_KEY,
            model=model,
            system=system,
            prompt=prompt,  # <= используем собранный prompt с историей
            max_tokens=max_tokens,
            timeout=30,  # <= вернули 30 сек
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
            await update.message.reply_text(
                "⚠️ Произошла ошибка. Попробуй ещё раз, я уже смотрю логи."
            )
        except Exception:
            pass
