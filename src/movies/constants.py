STATUS = {
    "TO_WATCH": "to_watch",
    "WATCHED": "watched",
    "DELETED": "deleted",
}

STATUS_ICON = {
    "to_watch": "🎥",
    "watched": "✅",
    "deleted": "🗑️",
}


def icon(status: str) -> str:
    return STATUS_ICON.get(status, "🎥")
