import re

from telegram import Update
from telegram.ext import ContextTypes

from src.core import db

# SQL-запрос для вставки или обновления привязки
# ВНИМАНИЕ: updated_at НЕ трогать (оно обновляется триггером)
UPSERT_LINK = """
INSERT INTO tg_insta_links (chat_id, telegram_user_id, display_name, instagram_username)
VALUES ($1, $2, $3, $4)
ON CONFLICT (chat_id, telegram_user_id) DO UPDATE
SET display_name = EXCLUDED.display_name,
    instagram_username = EXCLUDED.instagram_username
"""

# SQL-запрос для получения всех привязок чата
SELECT_LINKS = """
SELECT display_name, instagram_username
FROM tg_insta_links
WHERE chat_id = $1
ORDER BY updated_at DESC, display_name ASC
"""

# Регэкс для валидации имени Instagram
INSTAGRAM_RE = r'^[A-Za-z0-9._]{1,30}$'

# Подсказка по использованию команды /link
USAGE = (
    "Использование: /link <имя> <insta>\n"
    "Примеры: /link Иван Петров @ivan.petrov | /link Аня anyaaa"
)


def normalize_instagram(s: str) -> str | None:
    """Нормализует и проверяет логин Instagram."""
    s = s.strip().lstrip("@").lower()
    return s if re.fullmatch(INSTAGRAM_RE, s) else None


async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /link."""
    message = update.message
    if not message:
        chat = update.effective_chat
        if chat:
            await chat.send_message(USAGE)
        return
    if not message.text:
        await message.reply_text(USAGE)
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply_text(USAGE)
        return
    tokens = parts[1].split()
    if len(tokens) < 2:
        await message.reply_text(USAGE)
        return
    raw_instagram = tokens[-1]
    name = " ".join(tokens[:-1]).strip()
    instagram = normalize_instagram(raw_instagram)
    if not name or instagram is None:
        await message.reply_text(USAGE)
        return
    pool = db.pool
    if pool is None:
        await message.reply_text("База данных недоступна, попробуйте позже.")
        return
    await pool.execute(
        UPSERT_LINK,
        message.chat.id,
        message.from_user.id,
        name,
        instagram,
    )
    await message.reply_text(f"Готово! Привязал: {name} — @{instagram}")


async def insta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /insta."""
    message = update.message
    chat = update.effective_chat
    if message:
        send = message.reply_text
    elif chat:
        send = chat.send_message
    else:
        return
    pool = db.pool
    if pool is None:
        await send("База данных недоступна, попробуйте позже.")
        return
    rows = await pool.fetch(SELECT_LINKS, chat.id if chat else message.chat.id)
    if not rows:
        await send("В этом чате пока нет привязок. Используйте /link <имя> <insta>")
        return
    lines = [f"+ {r['display_name']} — @{r['instagram_username']}" for r in rows]
    text = "Привязанные Instagram:\n" + "\n".join(lines)
    await send(text)
