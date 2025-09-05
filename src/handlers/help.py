from telegram import Update
from telegram.ext import ContextTypes

from src.core.config import config
from src.core.i18n import t


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    lang = update.effective_user.language_code or config.LANG_FALLBACKS[0]
    await update.message.reply_text(t("help_text", lang=lang))
