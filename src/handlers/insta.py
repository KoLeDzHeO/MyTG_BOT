import re

from aiogram import Dispatcher, types
from aiogram.filters import Command

from src.core import db

# SQL-запрос для вставки или обновления привязки
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
INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

# Подсказка по использованию команды /link
USAGE = (
    "Использование: /link <имя> <insta>\n"
    "Примеры: /link Иван Петров @ivan.petrov | /link Аня anyaaa"
)


def normalize_instagram(s: str) -> str | None:
    """Нормализует и проверяет логин Instagram."""
    username = s.strip().lstrip("@").lower()
    return username if INSTAGRAM_RE.fullmatch(username) else None


async def link_handler(message: types.Message) -> None:
    """Обрабатывает команду /link."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(USAGE)
        return
    tokens = parts[1].split()
    if len(tokens) < 2:
        await message.answer(USAGE)
        return
    raw_instagram = tokens[-1]
    name = " ".join(tokens[:-1]).strip()
    instagram = normalize_instagram(raw_instagram)
    if not name or instagram is None:
        await message.answer(USAGE)
        return
    pool = db.pool
    if pool is None:
        await message.answer("База данных недоступна, попробуйте позже.")
        return
    await pool.execute(
        UPSERT_LINK,
        message.chat.id,
        message.from_user.id,
        name,
        instagram,
    )
    await message.answer(f"Готово! Привязал: {name} — @{instagram}")


async def insta_handler(message: types.Message) -> None:
    """Обрабатывает команду /insta."""
    pool = db.pool
    if pool is None:
        await message.answer("База данных недоступна, попробуйте позже.")
        return
    rows = await pool.fetch(SELECT_LINKS, message.chat.id)
    if not rows:
        await message.answer(
            "В этом чате пока нет привязок. Используйте /link <имя> <insta>"
        )
        return
    lines = [
        f"+ {r['display_name']} — @{r['instagram_username']}" for r in rows
    ]
    text = "Привязанные Instagram:\n" + "\n".join(lines)
    await message.answer(text)


def register(dp: Dispatcher) -> None:
    """Регистрирует хендлеры в диспетчере."""
    dp.message.register(link_handler, Command("link"))
    dp.message.register(insta_handler, Command("insta"))
