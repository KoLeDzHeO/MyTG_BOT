from textwrap import wrap
from src.core.config import config


def chunk_text(text: str, size: int) -> list[str]:
    # используем встроенный textwrap
    return wrap(text, size)


def mask(text: str) -> str:
    for secret in (
        config.TELEGRAM_TOKEN,
        getattr(config, "OPENAI_API_KEY", None),
    ):
        if secret:
            text = text.replace(secret, "***")
    return text
