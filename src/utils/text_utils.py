from src.config import config


def chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def mask(text: str) -> str:
    for secret in (config.TELEGRAM_TOKEN, config.OPENAI_API_KEY):
        if secret:
            text = text.replace(secret, "***")
    return text
