import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, List

import httpx

from src.core.config import config


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


@dataclass
class Candidate:
    tmdb_id: int
    title_localized: str
    original_title: str
    release_year: int | None
    popularity: float
    media_type: str
    belongs_to_collection_id: int | None = None
    score: float = 0.0
    lang: str | None = None


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

    async def search_candidates(self, query: str, user_year: int | None) -> List[Candidate]:
        """Return list of movie candidates for given query."""
        results: list[dict] = []
        for lang in self.languages:
            params = {"query": query, "language": lang}
            if user_year:
                params["year"] = user_year
                data = await self._get("/search/movie", params)
                results = data.get("results") or []
                if results:
                    break
                params.pop("year")
            data = await self._get("/search/movie", params)
            results = data.get("results") or []
            if results:
                break

        candidates: list[Candidate] = []
        for r in results[:10]:
            media_type = "movie"  # search/movie returns movies only
            if media_type != "movie":
                continue
            release_date = r.get("release_date") or ""
            release_year = None
            if len(release_date) >= 4:
                try:
                    release_year = int(release_date[:4])
                except ValueError:
                    release_year = None
            cand = Candidate(
                tmdb_id=r.get("id"),
                title_localized=r.get("title") or r.get("original_title") or "",
                original_title=r.get("original_title") or r.get("title") or "",
                release_year=release_year,
                popularity=r.get("popularity", 0.0),
                media_type=media_type,
                lang=lang,
            )
            candidates.append(cand)

        # enrich with collection ids for top results
        for cand in candidates[:5]:
            try:
                data = await self._get(f"/movie/{cand.tmdb_id}", {"language": self.languages[0]})
            except TMDbError:
                data = {}
            belongs = data.get("belongs_to_collection") or {}
            cand.belongs_to_collection_id = belongs.get("id")

        return candidates

    async def fetch_collection_parts(self, collection_id: int) -> List[Candidate]:
        data = await self._get(
            f"/collection/{collection_id}", {"language": self.languages[0]}
        )
        parts = data.get("parts") or []
        candidates: list[Candidate] = []
        for p in parts:
            release_date = p.get("release_date") or ""
            release_year = None
            if len(release_date) >= 4:
                try:
                    release_year = int(release_date[:4])
                except ValueError:
                    release_year = None
            candidates.append(
                Candidate(
                    tmdb_id=p.get("id"),
                    title_localized=p.get("title") or p.get("name") or "",
                    original_title=p.get("original_title") or p.get("title") or "",
                    release_year=release_year,
                    popularity=p.get("popularity", 0.0),
                    media_type="movie",
                    belongs_to_collection_id=collection_id,
                )
            )
        return candidates

    def score_candidates(
        self,
        cands: List[Candidate],
        user_year: int | None,
        part_hint: int | None,
        query: str | None,
    ) -> List[Candidate]:
        """Apply heuristic scoring and return sorted list."""

        def _has_part(title: str, part: int) -> bool:
            title_lower = title.lower()
            arabic = str(part)
            romans = [
                "i",
                "ii",
                "iii",
                "iv",
                "v",
                "vi",
                "vii",
                "viii",
                "ix",
                "x",
            ]
            roman = romans[part - 1] if 0 < part <= len(romans) else ""
            patterns = [
                arabic,
                roman,
                f"part {arabic}",
                f"part {roman}",
                f"chapter {arabic}",
                f"chapter {roman}",
                f"volume {arabic}",
                f"volume {roman}",
            ]
            return any(p in title_lower for p in patterns if p)

        for cand in cands:
            score = cand.popularity
            if user_year and cand.release_year == user_year:
                score *= 1.1
            if part_hint and (
                _has_part(cand.title_localized, part_hint)
                or _has_part(cand.original_title, part_hint)
            ):
                score *= 1.2
            if query and (
                cand.title_localized.lower() == query.lower()
                or cand.original_title.lower() == query.lower()
            ):
                score *= 1.1
            cand.score = score
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands

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
