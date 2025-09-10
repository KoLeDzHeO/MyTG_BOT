"""Авторазворачивание ссылок Instagram."""

import gc
import logging
import os
import re
import resource
import shutil
import tracemalloc

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
        # Удаляем файл и временную директорию, чтобы не копить мусор
        _cleanup_tmp(path)
        if config.MEM_DEBUG:
            _log_mem_debug()
        return
    try:
        with open(path, "rb") as fh:
            await context.bot.send_video(
                chat_id=message.chat_id, video=fh, supports_streaming=True
            )
    finally:
        _cleanup_tmp(path)
        if config.MEM_DEBUG:
            # При включённом MEM_DEBUG выводим статистику по памяти
            _log_mem_debug()


def _cleanup_tmp(path: str) -> None:
    """Удаляет файл и его временную директорию при совпадении префикса."""
    try:
        os.remove(path)
    except OSError:
        pass
    tmpdir = os.path.dirname(path)
    if os.path.basename(tmpdir).startswith(config.INSTAGRAM_TMP_PREFIX):
        shutil.rmtree(tmpdir, ignore_errors=True)


def _log_mem_debug() -> None:
    """Логирует статистику по памяти."""
    collected = gc.collect()
    current, peak = (
        tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (0, 0)
    )
    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux: ru_maxrss в КБ, macOS: в байтах
    import sys

    factor = 1 if sys.platform == "darwin" else 1024
    rss_mb = rss_raw / factor / 1024
    logging.info(
        "mem_debug: gc=%d current_bytes=%d peak_bytes=%d rss_mb=%.1f",
        collected,
        current,
        peak,
        rss_mb,
    )

