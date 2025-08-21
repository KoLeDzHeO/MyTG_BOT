from typing import List


def split_message(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        chunk = remaining[:limit]
        cut = max(chunk.rfind("\n"), chunk.rfind(" "))
        if cut <= 0:
            cut = limit  # жесткий фолбэк
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n ")
    return parts
