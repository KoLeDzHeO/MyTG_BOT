"""Загрузка роликов Instagram."""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL

from src.core.config import config


async def download_instagram_video(url: str) -> Optional[str]:
    """Скачивает видео Instagram и возвращает путь к mp4 или None."""

    def _download() -> Optional[str]:
        # создаём временную директорию для выгрузки ролика
        tmpdir = tempfile.mkdtemp(prefix=config.INSTAGRAM_TMP_PREFIX)
        outtmpl = str(Path(tmpdir) / "%(id)s.%(ext)s")
        ydl_opts = {
            # всегда получаем mp4
            "format": "mp4/bestvideo*+bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,  # не засорять вывод
            "noplaylist": True,  # одиночное видео
            "cachedir": False,  # не использовать кэш
            "nopart": True,  # без временных .part
            "final_ext": "mp4",
            "merge_output_format": "mp4",
            "prefer_ffmpeg": True,
        }
        if config.INSTAGRAM_COOKIES_FILE:
            ydl_opts["cookiefile"] = config.INSTAGRAM_COOKIES_FILE
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
                # возвращаем путь только если файл действительно создан
                if filename.exists():
                    return str(filename)
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None
        except Exception as exc:  # логируем лаконично и чистим директорию
            logging.error("Instagram download error: %s", exc)
            shutil.rmtree(tmpdir, ignore_errors=True)
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

