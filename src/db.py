import logging
import secrets
from typing import Optional

import asyncpg

from .config import config
from .movies.constants import STATUS


class DuplicateTmdbError(Exception):
    """Raised when tmdb_id is already present in DB."""


pool: asyncpg.Pool | None = None
TMDB_CONSTRAINTS = {"uniq_movies_tmdb_id", "movies_tmdb_id_key"}


async def init() -> None:
    global pool
    try:
        pool = await asyncpg.create_pool(dsn=config.DATABASE_URL)
        logging.info("DB connected")
        await _create_indexes()
    except Exception as e:  # connection/config errors
        logging.error("db init failed: %s", e)
        raise SystemExit("Не удалось подключиться к БД. Проверьте переменную окружения.")


async def close() -> None:
    if pool:
        await pool.close()


def _gen_id() -> str:
    return secrets.token_hex(3)


async def movie_exists_by_tmdb_id(tmdb_id: int) -> bool:
    assert pool is not None
    row = await pool.fetchrow("SELECT 1 FROM movies WHERE tmdb_id=$1", tmdb_id)
    return row is not None


async def get_movie_by_tmdb_id(tmdb_id: int) -> Optional[tuple[str, str, int]]:
    """Return (id, title, year) if movie exists."""
    assert pool is not None
    row = await pool.fetchrow(
        "SELECT id, title, year FROM movies WHERE tmdb_id=$1",
        tmdb_id,
    )
    if row:
        return row["id"], row["title"], row["year"]
    return None


async def insert_movie(*, title: str, year: int, genres: Optional[str], tmdb_id: int) -> str:
    """Insert movie and return internal id."""
    assert pool is not None
    for _ in range(10):
        movie_id = _gen_id()
        try:
            await pool.execute(
                """
                INSERT INTO movies (id, title, year, genres, status, tmdb_id, source)
                VALUES ($1, $2, $3, $4, $5, $6, 'tmdb')
                """,
                movie_id,
                title,
                year,
                genres,
                STATUS["TO_WATCH"],
                tmdb_id,
            )
            return movie_id
        except asyncpg.exceptions.UniqueViolationError as e:
            cname = getattr(e, "constraint_name", "") or ""
            logging.warning("unique violation constraint=%s", cname)
            if cname in TMDB_CONSTRAINTS:
                raise DuplicateTmdbError from e
            if cname == "movies_pkey":
                logging.warning("id collision: %s", movie_id)
                continue
            logging.error("unknown unique constraint=%s", cname)
            raise
    raise RuntimeError("Unable to generate unique id")


async def get_last_movies(limit: int = 30) -> tuple[int, list[tuple[str, str, int, str]]]:
    """Return total count and last `limit` movies ordered by created_at ASC."""
    assert pool is not None
    total = await pool.fetchval("SELECT COUNT(*) FROM movies")
    rows = await pool.fetch(
        "SELECT id, title, year, status FROM movies ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return total, [
        (r["id"], r["title"], r["year"], r["status"]) for r in reversed(list(rows))
    ]


async def fetch_all_movies_for_export() -> list[dict]:
    """Return all movies for exporter."""
    assert pool is not None
    rows = await pool.fetch(
        "SELECT id, tmdb_id, title, year, status FROM movies ORDER BY created_at"
    )
    return [dict(r) for r in rows]


async def _create_indexes() -> None:
    assert pool is not None
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_movies_created_at ON movies (created_at DESC)"
    )
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_movies_status_watched_at ON movies (status, watched_at DESC)"
    )
    await pool.execute(
        "CREATE INDEX IF NOT EXISTS idx_movies_status_deleted_at ON movies (status, deleted_at DESC)"
    )
    logging.info("db indexes ok")
