import json
import logging
import re
from pathlib import Path
from typing import List, Tuple

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

log = logging.getLogger(__name__)

_TRIGGER_PATTERNS: List[Tuple[re.Pattern[str], str]] = []

def _load_triggers() -> None:
    global _TRIGGER_PATTERNS
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "triggers.json"
    if not cfg_path.exists():
        _TRIGGER_PATTERNS = []
        return
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to read triggers config")
        _TRIGGER_PATTERNS = []
        return
    if not isinstance(data, dict):
        _TRIGGER_PATTERNS = []
        return
    patterns: List[Tuple[re.Pattern[str], str]] = []
    for phrase, reply in data.items():
        if not isinstance(phrase, str) or not isinstance(reply, str):
            continue
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", flags=re.IGNORECASE)
        patterns.append((pattern, reply))
    _TRIGGER_PATTERNS = patterns
    logging.info("Loaded %d triggers", len(_TRIGGER_PATTERNS))

_load_triggers()

async def trigger_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _TRIGGER_PATTERNS:
        return
    text = update.message.text or ""
    if not text or text.startswith('.'):
        return
    for pattern, reply in _TRIGGER_PATTERNS:
        if pattern.search(text):
            await update.message.reply_text(reply)
            break

def get_handlers():
    return [
        MessageHandler(filters.TEXT & (~filters.COMMAND), trigger_reply)
    ]
