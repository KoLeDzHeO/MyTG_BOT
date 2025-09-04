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


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[n]


def _token_set_ratio(a: str, b: str) -> float:
    """Approximate token_set_ratio from fuzzywuzzy."""
    import difflib

    tokens_a = set(a.split())
    tokens_b = set(b.split())
    sa = " ".join(sorted(tokens_a))
    sb = " ".join(sorted(tokens_b))
    return difflib.SequenceMatcher(None, sa, sb).ratio()


def _parse(args: list[str]) -> tuple[str, Optional[int], Optional[int]]:
    tokens = [a.strip() for a in args if a.strip()]
    if not tokens:
        raise ValueError
    user_year: Optional[int] = None
    if tokens and tokens[-1].isdigit() and len(tokens[-1]) == 4:
        year = int(tokens[-1])
        if 1888 <= year <= 2100:
            user_year = year
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
    return title, user_year, part_hint


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
        except ValueError:
            logging.warning("/add format_error")
            await update.message.reply_text(t("format_error", lang=lang))
            return
        logging.info("/add no_year title=%s hint_year=%s part=%s", query_title, user_year, part_hint)

        _cleanup_expired()
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        for key in list(_pending.keys()):
            if key[0] == chat_id and key[1] == user_id:
                _pending.pop(key, None)
                await update.message.reply_text(t("old_cancelled", lang=lang))

        try:
            candidates = await tmdb_client.search_candidates(query_title, None)
            if not candidates:
                logging.warning(
                    "/add not_found title=%s", query_title
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

        q_norm = _norm_title(query_title)
        for c in candidates:
            c.part_num = _extract_part_from_title(c.title_localized) or _extract_part_from_title(c.original_title)
            c.norm_local = _norm_title(c.title_localized)
            c.norm_orig = _norm_title(c.original_title)
        exact_matches = [
            c
            for c in candidates
            if c.norm_local == q_norm or c.norm_orig == q_norm
        ]

        top1 = candidates[0]

        # part hint handling with exact matches
        if part_hint is not None and exact_matches:
            exact_matches.sort(key=lambda c: (c.part_num != part_hint, -c.score))
            options = exact_matches[:5]
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
            msg = await update.message.reply_text(
                t("series_prompt", lang=lang, base_title=q_norm), reply_markup=keyboard
            )
            key = (chat_id, user_id, msg.message_id)
            _pending[key] = {
                "query": query_title,
                "user_year": user_year,
                "options": {c.tmdb_id: c for c in options},
                "top1_tmdb_id": top1.tmdb_id,
                "expires_at": time.time() + PENDING_TTL,
                "lang": lang,
                "confirm_year": False,
            }
            if context.job_queue:
                context.job_queue.run_once(
                    _timeout_job,
                    PENDING_TTL,
                    data={"key": key, "chat_id": chat_id, "lang": lang},
                )
            else:
                logging.warning("/add no job_queue: timeout job skipped")
            logging.warning(
                "/add ambiguous -> dialog reason=part_hint_matches count=%s",
                len(options),
            )
            return

        if len(exact_matches) == 1 and part_hint is None:
            cand = exact_matches[0]
            if cand.release_year is not None and cand.tmdb_id == top1.tmdb_id:
                try:
                    details = await tmdb_client.get_movie_details(cand.tmdb_id)
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
                        logging.warning(
                            "/add tmdb_id=%s duplicate_precheck", details.tmdb_id
                        )
                        await update.message.reply_text(
                            t("add_duplicate_simple", lang=lang)
                        )
                        return
                    new_id = await db.insert_movie(
                        title=details.title,
                        year=details.year,
                        genres=details.genres,
                        tmdb_id=details.tmdb_id,
                    )
                except DuplicateTmdbError:
                    logging.warning(
                        "/add tmdb_id=%s duplicate_race", details.tmdb_id
                    )
                    await update.message.reply_text(
                        t("add_duplicate_simple", lang=lang)
                    )
                    return
                except Exception:
                    rid = uuid.uuid4().hex[:8].upper()
                    logging.exception("/add db_error id=%s", rid)
                    await update.message.reply_text(
                        t("tech_error", lang=lang, rid=rid)
                    )
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
                    "/add mode=auto tmdb_id=%s year=%s id=%s",
                    details.tmdb_id,
                    details.year,
                    new_id,
                )
                try:
                    await schedule_export(context.job_queue)
                except Exception:
                    logging.exception("export schedule failed")
                return

        if len(exact_matches) > 1:
            titles = {c.title_localized for c in exact_matches}
            if len(titles) == 1:
                group_years = {c.release_year for c in exact_matches if c.release_year is not None}
                if group_years:
                    options_by_year: dict[int, Candidate] = {}
                    for c in exact_matches:
                        if c.release_year is None:
                            continue
                        prev = options_by_year.get(c.release_year)
                        if not prev or c.popularity > prev.popularity:
                            options_by_year[c.release_year] = c
                    options = list(options_by_year.values())
                    options.sort(
                        key=lambda c: (c.popularity, c.release_year or 0), reverse=True
                    )
                    options = options[:5]
                    keyboard_buttons = [
                        [
                            InlineKeyboardButton(
                                f"{c.title_localized} ({c.release_year})",
                                callback_data=f"ADD_PICK:{c.tmdb_id}",
                            )
                        ]
                        for c in options
                    ]
                    keyboard_buttons.append(
                        [InlineKeyboardButton(t("cancel_btn", lang=lang), callback_data="ADD_CANCEL")]
                    )
                    keyboard = InlineKeyboardMarkup(keyboard_buttons)
                    msg = await update.message.reply_text(
                        t("same_title_prompt", lang=lang, title=options[0].title_localized),
                        reply_markup=keyboard,
                    )
                    key = (chat_id, user_id, msg.message_id)
                    _pending[key] = {
                        "query": query_title,
                        "user_year": user_year,
                        "options": {c.tmdb_id: c for c in options},
                        "top1_tmdb_id": top1.tmdb_id,
                        "expires_at": time.time() + PENDING_TTL,
                        "lang": lang,
                        "confirm_year": True,
                    }
                    if context.job_queue:
                        context.job_queue.run_once(
                            _timeout_job,
                            PENDING_TTL,
                            data={"key": key, "chat_id": chat_id, "lang": lang},
                        )
                    else:
                        logging.warning("/add no job_queue: timeout job skipped")
                    logging.warning(
                        "/add ambiguous -> dialog reason=same_title_multi_years count=%s years=%s",
                        len(exact_matches),
                        sorted(group_years),
                    )
                    return
                options = sorted(
                    exact_matches,
                    key=lambda c: (
                        (c.part_num != part_hint) if part_hint is not None else False,
                        -c.score,
                    ),
                )[:5]
                keyboard_buttons = []
                for c in options:
                    part_num = c.part_num
                    year_text = t("year_unknown", lang=lang)
                    prefix = f"{_part_emoji(part_num)} " if part_num else ""
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(
                                f"{prefix}{c.title_localized} ({year_text})",
                                callback_data=f"ADD_PICK:{c.tmdb_id}",
                            )
                        ]
                    )
                keyboard_buttons.append(
                    [InlineKeyboardButton(t("cancel_btn", lang=lang), callback_data="ADD_CANCEL")]
                )
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                text = (
                    t("series_prompt", lang=lang, base_title=q_norm)
                    if part_hint is not None
                    else t("similar_prompt", lang=lang)
                )
                msg = await update.message.reply_text(text, reply_markup=keyboard)
                key = (chat_id, user_id, msg.message_id)
                _pending[key] = {
                    "query": query_title,
                    "user_year": user_year,
                    "options": {c.tmdb_id: c for c in options},
                    "top1_tmdb_id": top1.tmdb_id,
                    "expires_at": time.time() + PENDING_TTL,
                    "lang": lang,
                    "confirm_year": False,
                }
                if context.job_queue:
                    context.job_queue.run_once(
                        _timeout_job,
                        PENDING_TTL,
                        data={"key": key, "chat_id": chat_id, "lang": lang},
                    )
                else:
                    logging.warning("/add no job_queue: timeout job skipped")
                logging.warning(
                    "/add ambiguous -> dialog reason=title_no_years count=%s",
                    len(exact_matches),
                )
                return

            exact_matches.sort(
                key=lambda c: (
                    (c.part_num != part_hint) if part_hint is not None else False,
                    -c.score,
                )
            )
            options = exact_matches[:5]
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
            msg = await update.message.reply_text(
                t("similar_prompt", lang=lang), reply_markup=keyboard
            )
            key = (chat_id, user_id, msg.message_id)
            _pending[key] = {
                "query": query_title,
                "user_year": user_year,
                "options": {c.tmdb_id: c for c in options},
                "top1_tmdb_id": top1.tmdb_id,
                "expires_at": time.time() + PENDING_TTL,
                "lang": lang,
                "confirm_year": False,
            }
            if context.job_queue:
                context.job_queue.run_once(
                    _timeout_job,
                    PENDING_TTL,
                    data={"key": key, "chat_id": chat_id, "lang": lang},
                )
            else:
                logging.warning("/add no job_queue: timeout job skipped")
            logging.warning(
                "/add ambiguous -> dialog reason=multiple_exact count=%s",
                len(options),
            )
            return

        # no exact matches -> similar dialog
        similar: list[tuple[Candidate, int]] = []
        for c in candidates:
            cand_norm = _norm_title(c.title_localized)
            if cand_norm == q_norm:
                continue
            dist = _levenshtein(q_norm, cand_norm)
            ratio = _token_set_ratio(q_norm, cand_norm)
            limit = 1 if len(q_norm) <= 5 else 2
            if dist <= limit or ratio >= 0.9:
                similar.append((c, dist))
        if not similar:
            similar = [(c, _levenshtein(q_norm, _norm_title(c.title_localized))) for c in candidates]
        similar.sort(
            key=lambda x: (
                (x[0].part_num != part_hint) if part_hint is not None else False,
                x[1],
                -x[0].score,
            )
        )
        options = [c for c, _ in similar[:5]]
        keyboard_buttons = []
        for c in options:
            part_num = _extract_part_from_title(c.title_localized) or _extract_part_from_title(c.original_title)
            year_text = c.release_year if c.release_year is not None else t("year_unknown", lang=lang)
            prefix = f"{_part_emoji(part_num)} " if part_num else ""
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        f"{prefix}{c.title_localized} ({year_text})",
                        callback_data=f"ADD_PICK:{c.tmdb_id}",
                    )
                ]
            )
        keyboard_buttons.append(
            [InlineKeyboardButton(t("cancel_btn", lang=lang), callback_data="ADD_CANCEL")]
        )
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        text = (
            t("year_prompt", lang=lang, user_year=user_year)
            if user_year
            else (
                t("series_prompt", lang=lang, base_title=q_norm)
                if part_hint is not None
                else t("similar_prompt", lang=lang)
            )
        )
        msg = await update.message.reply_text(text, reply_markup=keyboard)
        key = (chat_id, user_id, msg.message_id)
        _pending[key] = {
            "query": query_title,
            "user_year": user_year,
            "options": {c.tmdb_id: c for c in options},
            "top1_tmdb_id": top1.tmdb_id,
            "expires_at": time.time() + PENDING_TTL,
            "lang": lang,
            "confirm_year": False,
        }
        if context.job_queue:
            context.job_queue.run_once(
                _timeout_job,
                PENDING_TTL,
                data={"key": key, "chat_id": chat_id, "lang": lang},
            )
        else:
            logging.warning("/add no job_queue: timeout job skipped")
        logging.warning(
            "/add ambiguous -> dialog reason=title_mismatch query_norm=%s top1_norm=%s",
            q_norm,
            top1.norm_local,
        )
        return
    except Exception:
        rid = uuid.uuid4().hex[:8].upper()
        logging.exception("/add unexpected_error id=%s", rid)
        await update.message.reply_text(t("tech_error", lang=lang, rid=rid))
