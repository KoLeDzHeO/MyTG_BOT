import html


def as_html(text: str) -> str:
    """
    Экранируем текст для parse_mode="HTML".
    Telegram НЕ поддерживает <br>, поэтому сохраняем переносы как '\n'.
    """
    if text is None:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(text)

