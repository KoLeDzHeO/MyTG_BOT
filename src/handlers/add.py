import logging
import uuid
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src import db
from src.config import config
from src.db import DuplicateTmdbError
from src.tmdb_client import (
    TMDbAuthError,
    TMDbRateLimitError,
    TMDbUnavailableError,
    TMDbError,
    tmdb_client,
)
from src.exporter import export_movie

FORMAT_ERROR = "Формат: /add Название 2014"
YEAR_ERROR = "Формат: /add Название 2014 (год должен быть от 1888 до 2100)"
NOT_FOUND = "Не нашёл такой фильм в базе TMDb. Попробуй другое написание."
NO_DATE = "В TMDb нет корректной даты релиза по этому фильму, добавление отменено."
DUPLICATE = "Этот фильм уже в списке (найдён по TMDb)."
AUTH_ERROR = "Проблема авторизации TMDb. Проверьте TMDB_KEY."
RATE_ERROR = "TMDb ограничил частоту запросов. Попробуйте чуть позже."
TMDB_UNAVAILABLE = "Сервис TMDb временно недоступен, попробуйте позже."
TECH_ERROR_TEMPLATE = "⚠️ Сервис временно недоступен (id={})"


class YearFormatError(Exception):
    pass


def _parse(args: list[str]) -> tuple[str, int]:
    if len(args) < 2:
        raise ValueError
    year_str = args[-1].strip()
    if not year_str.isdigit() or len(year_str) != 4:
        raise YearFormatError
    year = int(year_str)
    if year < 1888 or year > 2100:
        raise YearFormatError
    title = " ".join(a.strip() for a in args[:-1]).strip()
    if len(title) < 2:
        raise ValueError
    return title, year


async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    try:
        raw = update.message.text or ""
        logging.info("/add raw=%r", raw)
        try:
            query_title, user_year = _parse(context.args)
        except YearFormatError:
            logging.warning("/add year_format_error")
            await update.message.reply_text(YEAR_ERROR)
            return
        except ValueError:
            logging.warning("/add format_error")
            await update.message.reply_text(FORMAT_ERROR)
            return
        logging.info("/add normalized title=%s year=%s", query_title, user_year)

        try:
            movie_id = await tmdb_client.search_movie(query_title, user_year)
            if not movie_id:
                logging.warning("/add not_found title=%s year=%s", query_title, user_year)
                await update.message.reply_text(NOT_FOUND)
                return
            details = await tmdb_client.get_movie_details(movie_id)
            if not details:
                logging.warning("/add tmdb_id=%s no_date", movie_id)
                await update.message.reply_text(NO_DATE)
                return
        except TMDbAuthError:
            logging.error("/add tmdb_auth_error")
            await update.message.reply_text(AUTH_ERROR)
            return
        except TMDbRateLimitError:
            logging.warning("/add tmdb_rate_limit")
            await update.message.reply_text(RATE_ERROR)
            return
        except TMDbUnavailableError:
            logging.error("/add tmdb_unavailable")
            await update.message.reply_text(TMDB_UNAVAILABLE)
            return
        except TMDbError:
            rid = uuid.uuid4().hex[:8].upper()
            logging.error("/add tmdb_error id=%s", rid)
            await update.message.reply_text(TECH_ERROR_TEMPLATE.format(rid))
            return
        except Exception:
            rid = uuid.uuid4().hex[:8].upper()
            logging.exception("/add unexpected_tmdb_error id=%s", rid)
            await update.message.reply_text(TECH_ERROR_TEMPLATE.format(rid))
            return

        try:
            if await db.movie_exists_by_tmdb_id(details.tmdb_id):
                logging.warning("/add tmdb_id=%s duplicate_precheck", details.tmdb_id)
                await update.message.reply_text(DUPLICATE)
                return
            new_id = await db.insert_movie(
                title=details.title,
                year=details.year,
                genres=details.genres,
                tmdb_id=details.tmdb_id,
            )
        except DuplicateTmdbError:
            logging.warning("/add tmdb_id=%s duplicate_race", details.tmdb_id)
            await update.message.reply_text(DUPLICATE)
            return
        except Exception:
            rid = uuid.uuid4().hex[:8].upper()
            logging.exception("/add db_error id=%s", rid)
            await update.message.reply_text(TECH_ERROR_TEMPLATE.format(rid))
            return

        genres_text = details.genres if details.genres else "жанры не указаны"
        if details.genres and details.genres_lang and details.genres_lang != config.LANG_FALLBACKS[0]:
            genres_text = f"{genres_text} ({details.genres_lang})"
        await update.message.reply_text(
            f"➕ Добавлено #{new_id}\n🎥 «{details.title}» ({details.year}) — {genres_text}"
        )
        logging.info(
            "/add success title=%s tmdb_id=%s year=%s id=%s genres=%s",
            query_title,
            details.tmdb_id,
            details.year,
            new_id,
            details.genres,
        )
        try:
            await export_movie(
                {
                    "id": new_id,
                    "tmdb_id": details.tmdb_id,
                    "title": details.title,
                    "year": details.year,
                }
            )
        except Exception:
            logging.exception("export_movie failed")
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add unexpected_error id=%s", rid)
        await update.message.reply_text(TECH_ERROR_TEMPLATE.format(rid))

