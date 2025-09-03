import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import config


class TMDbError(Exception):
    pass


class TMDbAuthError(TMDbError):
    pass


class TMDbRateLimitError(TMDbError):
    pass


class TMDbUnavailableError(TMDbError):
    pass


@dataclass
class MovieDetails:
    tmdb_id: int
    title: str
    year: int
    genres: Optional[str]
    genres_lang: Optional[str] = None


class TMDbClient:
    def __init__(self, api_key: str, languages: list[str]):
        self.api_key = api_key
        self.languages = languages or ["ru", "en"]
        self._client = httpx.AsyncClient(
            base_url="https://api.themoviedb.org/3", timeout=10
        )
        self._search_cache: dict[tuple[str, Optional[int]], tuple[float, Optional[int]]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict, retries: int = 2) -> dict:
        params = {**params, "api_key": self.api_key}
        delay = 1
        for attempt in range(retries):
            try:
                r = await self._client.get(path, params=params)
            except httpx.RequestError as e:
                logging.error("tmdb network error: %s", e)
                if attempt == retries - 1:
                    raise TMDbUnavailableError from e
                await asyncio.sleep(delay)
                delay *= 2
                continue
            text = r.text[:100].replace("\n", " ")
            logging.debug("tmdb %s %s", r.status_code, text)
            if r.status_code == 401:
                logging.error("tmdb 401: %s", text)
                raise TMDbAuthError
            if r.status_code == 429:
                logging.warning("tmdb 429: %s", text)
                raise TMDbRateLimitError
            if r.status_code >= 500:
                logging.error("tmdb %s: %s", r.status_code, text)
                if attempt == retries - 1:
                    raise TMDbUnavailableError
                await asyncio.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        raise TMDbUnavailableError

    async def search_movie(self, query: str, year: Optional[int]) -> Optional[int]:
        key = (query.lower(), year)
        cached = self._search_cache.get(key)
        now = time.time()
        if cached and now - cached[0] < 60:
            return cached[1]

        result_id: Optional[int] = None
        for lang in self.languages:
            params = {"query": query, "language": lang}
            if year:
                params["year"] = year
                data = await self._get("/search/movie", params)
                results = data.get("results") or []
                if results:
                    break
                params.pop("year")
            data = await self._get("/search/movie", params)
            results = data.get("results") or []
            if results:
                break
        if results:
            results.sort(
                key=lambda r: (r.get("popularity", 0), r.get("vote_count", 0)),
                reverse=True,
            )
            result_id = results[0]["id"]
        self._search_cache[key] = (now, result_id)
        return result_id

    async def get_movie_details(self, movie_id: int) -> Optional[MovieDetails]:
        first_details: MovieDetails | None = None
        for lang in self.languages:
            data = await self._get(f"/movie/{movie_id}", {"language": lang})
            if not data:
                continue
            title = data.get("title") or data.get("original_title")
            release_date = data.get("release_date") or ""
            if len(release_date) < 4:
                return None
            try:
                year = int(release_date[:4])
            except ValueError:
                return None
            genres = ", ".join(g.get("name") for g in data.get("genres") or []) or None
            if not first_details:
                first_details = MovieDetails(
                    tmdb_id=data["id"],
                    title=title,
                    year=year,
                    genres=genres,
                    genres_lang=lang if genres else None,
                )
                if genres:
                    return first_details
            if genres and not first_details.genres:
                first_details.genres = genres
                first_details.genres_lang = lang
                return first_details
        return first_details

    async def check_key(self) -> None:
        await self._get("/configuration", {})


tmdb_client = TMDbClient(config.TMDB_KEY, config.LANG_FALLBACKS)
