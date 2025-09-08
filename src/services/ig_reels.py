"""Загрузка роликов Instagram."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL

from src.core.config import config


async def download_instagram_video(url: str) -> Optional[str]:
    """Скачивает видео Instagram и возвращает путь к mp4 или None."""

    def _download() -> Optional[str]:
        tmpdir = tempfile.mkdtemp(prefix="ig_")
        out = str(Path(tmpdir) / "%(id)s.%(ext)s")
        ydl_opts = {
            "format": "mp4/bestvideo*+bestaudio/best",
            "outtmpl": out,
            "quiet": True,
            "noplaylist": True,
        }
        if config.INSTAGRAM_COOKIES_FILE:
            ydl_opts["cookiefile"] = config.INSTAGRAM_COOKIES_FILE
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        except Exception:
            logging.exception("insta download failed")
            return None

    return await asyncio.to_thread(_download)


def is_file_too_large(path: str, max_mb: int) -> bool:
    """Проверяет, превышает ли файл заданный размер."""
    try:
        size = Path(path).stat().st_size
    except OSError:
        # Если файл недоступен, считаем его слишком большим
        return True
    return size > max_mb * 1024 * 1024

