import html


def as_html(text: str) -> str:
    """Escape text for safe HTML parse_mode and preserve line breaks."""
    return html.escape(text).replace("\n", "<br>")

