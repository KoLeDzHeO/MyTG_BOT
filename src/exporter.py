"""Stub exporter. Real implementation will upload movies to cloud."""

import logging


async def export_movie(record: dict) -> None:
    """Export movie record after successful addition.

    Placeholder for future integration.
    """
    logging.info(
        "export stub id=%s tmdb_id=%s title=%s year=%s",
        record.get("id"),
        record.get("tmdb_id"),
        record.get("title"),
        record.get("year"),
    )

