def split_message(text: str, max_chars: int) -> list[str]:
    """Split text into chunks under max_chars, prefer splitting on newlines."""
    if len(text) <= max_chars:
        return [text]
    parts = []
    while text:
        if len(text) <= max_chars:
            parts.append(text)
            break
        # ищем последнюю границу строки в лимите
        cut = text.rfind("\n", 0, max_chars)
        if cut == -1 or cut < max_chars // 2:
            cut = max_chars
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts

