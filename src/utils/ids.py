"""Utilities for working with internal movie identifiers."""


def to_short_id(mid: str) -> str:
    """Return movie id in short format with leading '#'."""
    mid = mid or ""
    if len(mid) == 6 and all(c in "0123456789abcdef" for c in mid.lower()):
        return f"#{mid}"
    return f"#{mid[:6]}"

