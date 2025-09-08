"""Авторазворачивание ссылок Instagram."""

import os
import re

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from src.core.config import config
from src.services.ig_reels import download_instagram_video, is_file_too_large

# Регулярка для поиска ссылок на Instagram
INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/(?:reel|reels|p)/\S+", re.IGNORECASE)


async def insta_unfurl_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Находит ссылку Instagram, скачивает и отправляет видео."""
    message = update.message
    if not message or not message.text:
        return
    if not config.INSTAGRAM_ENABLE_UNFURL:
        return
    if any(e.type == "bot_command" for e in (message.entities or [])):
        return
    m = INSTAGRAM_RE.search(message.text)
    if not m:
        return
    url = m.group(0)
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO)
    path = await download_instagram_video(url)
    if path is None:
        await message.reply_text(
            f"⚠️ Не удалось загрузить видео с Instagram. Попробуйте позже.\n📎 Ссылка: {url}"
        )
        return
    if is_file_too_large(path, config.INSTAGRAM_MAX_VIDEO_MB):
        await message.reply_text(
            f"⚠️ Видео слишком большое для отправки ботом (лимит: {config.INSTAGRAM_MAX_VIDEO_MB} МБ). Оставляю ссылку: {url}"
        )
        return
    try:
        with open(path, "rb") as fh:
            await message.reply_video(fh, caption=url, supports_streaming=True)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

