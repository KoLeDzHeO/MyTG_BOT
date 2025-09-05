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


def _norm_title(title: str) -> str:
    text = title.lower()
    text = text.replace("-", " ")
    text = re.sub(r'["\'«»“”„]', "", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    if len(tokens) >= 2 and tokens[-2] in PART_KEYWORDS:
        last = tokens[-1]
        if last.isdigit() or last.upper() in ROMAN_MAP:
            tokens = tokens[:-2]
    return " ".join(tokens)


class YearError(Exception):
    pass


def _parse(args: list[str]) -> tuple[str, int, Optional[int]]:
    tokens = [a.strip() for a in args if a.strip()]
    if not tokens:
        raise ValueError
    if not tokens[-1].isdigit() or len(tokens[-1]) != 4:
        raise YearError
    year = int(tokens[-1])
    if year < 1888 or year > 2100:
        raise YearError
    tokens = tokens[:-1]
    part_hint: Optional[int] = None
    if len(tokens) >= 2:
        prev = tokens[-2].lower()
        token = tokens[-1]
        if prev in PART_KEYWORDS:
            if token.isdigit():
                part_hint = int(token)
                tokens = tokens[:-2]
            elif token.upper() in ROMAN_MAP:
                part_hint = ROMAN_MAP[token.upper()]
                tokens = tokens[:-2]
    title = " ".join(tokens).strip()
    if len(title) < 2:
        raise ValueError
    return title, year, part_hint


def _cleanup_expired() -> None:
    now = time.time
    for key, value in list(_pending.items()):
        if value["expires_at"] <= now():
            _pending.pop(key, None)


async def _timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    key = context.job.data["key"]
    pending = _pending.pop(key, None)
    if not pending:
        return
    chat_id, _, msg_id = key
    lang = pending["lang"]
    query = pending["query"]
    try:
        await context.bot.delete_message(chat_id, msg_id)
    except Exception:
        logging.warning("/add cleanup delete_denied msg_id=%s", msg_id)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=t("timeout", lang=lang, query=query),
                reply_markup=None,
            )
        except Exception:
            logging.warning("/add cleanup edit_failed msg_id=%s", msg_id)
    await context.bot.send_message(
        chat_id,
        t("timeout", lang=lang, query=query),
    )
    logging.info("/add cleanup reason=timeout msg_id=%s", msg_id)


async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    try:
        raw = update.message.text or ""
        logging.info("/add raw=%r", raw)
        lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
        try:
            query_title, user_year, part_hint = _parse(context.args)
        except YearError:
            logging.warning("/add year_error")
            await update.message.reply_text(t("year_error", lang=lang))
            return
        except ValueError:
            logging.warning("/add format_error")
            await update.message.reply_text(t("format_error", lang=lang))
            return

        _cleanup_expired()
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        for key in list(_pending.keys()):
            if key[0] == chat_id and key[1] == user_id:
                pending_old = _pending.pop(key, None)
                msg_id = key[2]
                try:
                    await context.bot.delete_message(chat_id, msg_id)
                except Exception:
                    logging.warning("/add cleanup delete_denied msg_id=%s", msg_id)
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=t("cancelled", lang=pending_old.get("lang", lang)),
                            reply_markup=None,
                        )
                    except Exception:
                        logging.warning("/add cleanup edit_failed msg_id=%s", msg_id)
                await update.message.reply_text(t("old_cancelled", lang=lang))
                break

        try:
            candidates = await tmdb_client.search_candidates(query_title, user_year)
            used_year_results = bool(candidates)
            if not candidates:
                candidates = await tmdb_client.search_candidates(query_title, None)
                used_year_results = False
            if not candidates:
                logging.warning("/add not_found title=%s year=%s", query_title, user_year)
                await update.message.reply_text(t("not_found", lang=lang))
                return
            candidates = tmdb_client.score_candidates(candidates, user_year, part_hint, query_title)
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

        unique: dict[int, Candidate] = {}
        for c in candidates:
            prev = unique.get(c.tmdb_id)
            if not prev or prev.score < c.score:
                unique[c.tmdb_id] = c
        candidates = sorted(unique.values(), key=lambda c: c.score, reverse=True)
        candidates = [c for c in candidates if c.media_type == "movie"]
        if not candidates:
            logging.warning("/add not_found title=%s year=%s", query_title, user_year)
            await update.message.reply_text(t("not_found", lang=lang))
            return

        q_norm = _norm_title(query_title)
        for c in candidates:
            c.part_num = _extract_part_from_title(c.title_localized) or _extract_part_from_title(c.original_title)
            c.norm_local = _norm_title(c.title_localized)
            c.norm_orig = _norm_title(c.original_title)

        top1 = candidates[0]
        top2_score = candidates[1].score if len(candidates) > 1 else None
        year_matches = [c for c in candidates if c.release_year == user_year]

        if (
            used_year_results
            and year_matches
            and top1.release_year == user_year
            and (top2_score is None or top1.score >= 1.2 * top2_score)
        ):
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
                "/add strict year mode=auto tmdb_id=%s year=%s id=%s",
                details.tmdb_id,
                details.year,
                new_id,
            )
            try:
                await schedule_export(context.job_queue)
            except Exception:
                logging.exception("export schedule failed")
            return

        reason = "close_scores"
        options: list[Candidate] = []

        if year_matches:
            options = year_matches[:5]
            text = t("year_prompt", lang=lang, user_year=user_year)
            reason = "close_scores"
        else:
            if top1.belongs_to_collection_id:
                try:
                    parts = await tmdb_client.fetch_collection_parts(top1.belongs_to_collection_id)
                except TMDbError:
                    parts = []
                parts = tmdb_client.score_candidates(parts, user_year, part_hint, query_title)
                unique_parts: dict[int, Candidate] = {}
                for p in parts:
                    prev = unique_parts.get(p.tmdb_id)
                    if not prev or prev.score < p.score:
                        unique_parts[p.tmdb_id] = p
                parts = sorted(
                    unique_parts.values(),
                    key=lambda c: (
                        c.release_year is None,
                        abs((c.release_year or 0) - user_year),
                        -c.score,
                    ),
                )
                options = parts[:5]
                text = t("series_prompt", lang=lang, base_title=q_norm)
                reason = "collection"
            else:
                options = sorted(
                    candidates,
                    key=lambda c: (
                        c.release_year is None,
                        abs((c.release_year or 0) - user_year),
                        -c.score,
                    ),
                )[:5]
                text = t("year_prompt", lang=lang, user_year=user_year)
                reason = "no_exact_year"

        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    f"{c.title_localized} ({c.release_year if c.release_year is not None else t('year_unknown', lang=lang)})",
                    callback_data=f"ADD_PICK:{c.tmdb_id}",
                )
            ]
            for c in options
        ]
        keyboard_buttons.append(
            [InlineKeyboardButton(t("cancel_btn", lang=lang), callback_data="ADD_CANCEL")]
        )
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        msg = await update.message.reply_text(text, reply_markup=keyboard)
        key = (chat_id, user_id, msg.message_id)
        _pending[key] = {
            "query": query_title,
            "user_year": user_year,
            "options": {c.tmdb_id: c for c in options},
            "top1_tmdb_id": top1.tmdb_id,
            "expires_at": time.time() + PENDING_TTL,
            "lang": lang,
            "confirm_year": reason == "no_exact_year",
        }
        if context.job_queue:
            context.job_queue.run_once(
                _timeout_job,
                PENDING_TTL,
                data={"key": key},
            )
        else:
            logging.warning("/add no job_queue: timeout job skipped")
        logging.warning(
            "/add ambiguous -> dialog reason=%s count=%s",
            reason,
            len(options),
        )
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add unexpected_error id=%s", rid)
        await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
