import logging
import time
import uuid
import re
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src import db
from src.config import config
from src.db import DuplicateTmdbError
from src.tmdb_client import (
    TMDbAuthError,
    TMDbError,
    TMDbRateLimitError,
    TMDbUnavailableError,
    tmdb_client,
    Candidate,
)
from src.exporter import schedule_export
from src.i18n import t
from src.utils.ids import to_short_id

NO_DATE = "В TMDb нет корректной даты релиза по этому фильму, добавление отменено."

PENDING_TTL = 120
_pending: dict[tuple[int, int, int], dict] = {}

PART_KEYWORDS = {
    "part",
    "chapter",
    "volume",
    "season",
    "сезон",
    "фильм",
    "film",
}

ROMAN_MAP = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
    "XVI": 16,
    "XVII": 17,
    "XVIII": 18,
    "XIX": 19,
    "XX": 20,
}

EMOJI_NUM = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
    10: "🔟",
}


def _extract_part_from_title(title: str) -> Optional[int]:
    pattern = r"(?i)(?:part|chapter|volume|season|сезон|фильм|film)\s*([ivxlcdm]+|\d+)\b"
    m = re.search(pattern, title)
    if not m:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    return ROMAN_MAP.get(token.upper())


def _part_emoji(num: Optional[int]) -> str:
    return EMOJI_NUM.get(num or 0, "")


class YearFormatError(Exception):
    pass


def _parse(args: list[str]) -> tuple[str, int, Optional[int]]:
    if len(args) < 2:
        raise ValueError
    year_str = args[-1].strip()
    if not year_str.isdigit() or len(year_str) != 4:
        raise YearFormatError
    year = int(year_str)
    if year < 1888 or year > 2100:
        raise YearFormatError
    title_parts = [a.strip() for a in args[:-1] if a.strip()]
    if not title_parts:
        raise ValueError
    part_hint: Optional[int] = None
    if len(title_parts) >= 2:
        prev = title_parts[-2].lower()
        token = title_parts[-1]
        if prev in PART_KEYWORDS:
            if token.isdigit():
                part_hint = int(token)
                title_parts = title_parts[:-2]
            elif token.upper() in ROMAN_MAP:
                part_hint = ROMAN_MAP[token.upper()]
                title_parts = title_parts[:-2]
    title = " ".join(title_parts).strip()
    if len(title) < 2:
        raise ValueError
    return title, year, part_hint


def _cleanup_expired() -> None:
    now = time.time()
    for key, value in list(_pending.items()):
        if value["expires_at"] <= now:
            _pending.pop(key, None)


async def _timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    key = data["key"]
    pending = _pending.pop(key, None)
    if pending:
        logging.warning("/add timeout")
        await context.bot.send_message(
            data["chat_id"],
            t("timeout", lang=pending["lang"], query=pending["query"]),
        )


async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    try:
        raw = update.message.text or ""
        logging.info("/add raw=%r", raw)
        lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
        try:
            query_title, user_year, part_hint = _parse(context.args)
        except YearFormatError:
            logging.warning("/add year_format_error")
            await update.message.reply_text(t("year_error", lang=lang))
            return
        except ValueError:
            logging.warning("/add format_error")
            await update.message.reply_text(t("format_error", lang=lang))
            return
        logging.info(
            "/add normalized title=%s year=%s part=%s", query_title, user_year, part_hint
        )

        _cleanup_expired()
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        for key in list(_pending.keys()):
            if key[0] == chat_id and key[1] == user_id:
                _pending.pop(key, None)
                await update.message.reply_text(t("old_cancelled", lang=lang))

        try:
            candidates = await tmdb_client.search_candidates(query_title, user_year)
            if not candidates:
                logging.warning(
                    "/add not_found title=%s year=%s", query_title, user_year
                )
                await update.message.reply_text(t("not_found", lang=lang))
                return
            if candidates[0].belongs_to_collection_id:
                try:
                    coll = await tmdb_client.fetch_collection_parts(
                        candidates[0].belongs_to_collection_id
                    )
                    candidates.extend(coll)
                except TMDbError:
                    pass
            candidates = tmdb_client.score_candidates(
                candidates, user_year, part_hint, query_title
            )
        except TMDbAuthError:
            logging.error("/add tmdb_auth_error")
            await update.message.reply_text(t("auth_error", lang=lang))
            return
        except TMDbRateLimitError:
            logging.warning("/add tmdb_rate_limit")
            await update.message.reply_text(t("rate_error", lang=lang))
            return
        except TMDbUnavailableError:
            logging.error("/add tmdb_unavailable")
            await update.message.reply_text(t("tmdb_unavailable", lang=lang))
            return
        except TMDbError:
            rid = uuid.uuid4().hex[:8].upper()
            logging.error("/add tmdb_error id=%s", rid)
            await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
            return
        except Exception:
            rid = uuid.uuid4().hex[:8].upper()
            logging.exception("/add unexpected_tmdb_error id=%s", rid)
            await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
            return

        # dedupe
        unique: dict[int, Candidate] = {}
        for c in candidates:
            prev = unique.get(c.tmdb_id)
            if not prev or prev.score < c.score:
                unique[c.tmdb_id] = c
        candidates = sorted(unique.values(), key=lambda c: c.score, reverse=True)
        candidates = [c for c in candidates if c.media_type == "movie"]

        top1 = candidates[0]
        top2 = candidates[1] if len(candidates) > 1 else None
        top3 = candidates[2] if len(candidates) > 2 else None
        year_mismatch = top1.release_year is not None and top1.release_year != user_year
        if config.ADD_CONFIRMATION_MODE.lower() != "relaxed":
            confirm_year = year_mismatch
        else:
            confirm_year = False
        gap_close = False
        if top2 and top1.score < top2.score * 1.2:
            gap_close = True
        if top3 and top1.score < top3.score * 1.2:
            gap_close = True
        collection_trigger = top1.belongs_to_collection_id is not None and part_hint is None
        unknown_year = top1.release_year is None
        confirm = confirm_year or gap_close or collection_trigger or unknown_year

        if not confirm:
            try:
                details = await tmdb_client.get_movie_details(top1.tmdb_id)
                if not details:
                    await update.message.reply_text(NO_DATE)
                    return
            except TMDbError:
                rid = uuid.uuid4().hex[:8].upper()
                logging.error("/add tmdb_error id=%s", rid)
                await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
                return
            except Exception:
                rid = uuid.uuid4().hex[:8].upper()
                logging.exception("/add unexpected_tmdb_error id=%s", rid)
                await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
                return

            try:
                if await db.movie_exists_by_tmdb_id(details.tmdb_id):
                    logging.warning("/add tmdb_id=%s duplicate_precheck", details.tmdb_id)
                    await update.message.reply_text(t("add_duplicate_simple", lang=lang))
                    return
                new_id = await db.insert_movie(
                    title=details.title,
                    year=details.year,
                    genres=details.genres,
                    tmdb_id=details.tmdb_id,
                )
            except DuplicateTmdbError:
                logging.warning("/add tmdb_id=%s duplicate_race", details.tmdb_id)
                await update.message.reply_text(t("add_duplicate_simple", lang=lang))
                return
            except Exception:
                rid = uuid.uuid4().hex[:8].upper()
                logging.exception("/add db_error id=%s", rid)
                await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
                return

            genres_text = details.genres if details.genres else "жанры не указаны"
            if (
                details.genres
                and details.genres_lang
                and details.genres_lang != config.LANG_FALLBACKS[0]
            ):
                genres_text = f"{genres_text} ({details.genres_lang})"
            short_id = to_short_id(new_id)
            await update.message.reply_text(
                t(
                    "add_success",
                    lang=lang,
                    short_id=short_id,
                    title=details.title,
                    year=details.year,
                    genres=genres_text,
                )
            )
            logging.info(
                "/add auto tmdb_id=%s year=%s id=%s", details.tmdb_id, details.year, new_id
            )
            try:
                await schedule_export(context.job_queue)
            except Exception:
                logging.exception("export schedule failed")
            return

        # confirmation dialog
        reasons = []
        if confirm_year:
            reasons.append("ambiguous_year")
        if gap_close:
            reasons.append("close_scores")
        if collection_trigger:
            reasons.append("collection")
        if unknown_year:
            reasons.append("unknown_year")
        logging.warning(
            "/add ambiguous -> dialog reason=[%s] top1_id=%s top1_score=%.2f top2_score=%.2f top3_score=%.2f",
            "|".join(reasons),
            top1.tmdb_id,
            top1.score,
            top2.score if top2 else 0,
            top3.score if top3 else 0,
        )
        options = candidates[:5]
        keyboard_buttons = []
        for c in options:
            part_num = _extract_part_from_title(c.title_localized) or _extract_part_from_title(c.original_title)
            year_text = c.release_year if c.release_year is not None else t("year_unknown", lang=lang)
            prefix = f"{_part_emoji(part_num)} " if part_num else ""
            btn = InlineKeyboardButton(
                f"{prefix}{c.title_localized} ({year_text})",
                callback_data=f"ADD_PICK:{c.tmdb_id}",
            )
            keyboard_buttons.append([btn])
        keyboard_buttons.append(
            [
                InlineKeyboardButton(t("add_found_btn", lang=lang), callback_data="ADD_TOP1"),
                InlineKeyboardButton(t("cancel_btn", lang=lang), callback_data="ADD_CANCEL"),
            ]
        )
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        if collection_trigger:
            text = t("series_prompt", lang=lang, base_title=top1.title_localized)
        elif confirm_year:
            text = t("year_prompt", lang=lang, user_year=user_year)
        else:
            text = t("year_prompt", lang=lang, user_year=user_year)
        msg = await update.message.reply_text(text, reply_markup=keyboard)
        key = (chat_id, user_id, msg.message_id)
        _pending[key] = {
            "query": query_title,
            "user_year": user_year,
            "options": {c.tmdb_id: c for c in options},
            "top1_tmdb_id": top1.tmdb_id,
            "expires_at": time.time() + PENDING_TTL,
            "lang": lang,
        }
        if context.job_queue:
            context.job_queue.run_once(
                _timeout_job,
                PENDING_TTL,
                data={"key": key, "chat_id": chat_id, "lang": lang},
            )
        else:
            logging.warning("/add no job_queue: timeout job skipped")
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add unexpected_error id=%s", rid)
        await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
