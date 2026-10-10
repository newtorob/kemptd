# SPDX-License-Identifier: GPL-3.0-or-later
"""The Movie Database (TMDb) metadata provider.

Implements :class:`~kemptd.providers.base.MetadataProvider` for movies and TV.
The HTTP client is injectable so the provider is fully testable offline (see
``tests/test_tmdb.py``, which drives it with ``httpx.MockTransport``). Search
results are memoized per instance — a 90-episode pack costs one lookup, not 90.
"""

from __future__ import annotations

from typing import Any

import httpx

from kemptd.errors import ProviderError
from kemptd.models import MovieCandidate, SeriesCandidate

__all__ = ["TmdbProvider"]

_BASE_URL = "https://api.themoviedb.org/3"
_TIMEOUT = 10.0


def _year(date: str | None) -> int | None:
    """TMDb dates look like ``"2022-04-01"``; pull the year if present."""
    if date and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


class TmdbProvider:
    """Look up canonical series/movie metadata via the TMDb v3 API."""

    name = "tmdb"

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ProviderError("TMDb API key is required")
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=_BASE_URL, timeout=_TIMEOUT)
        self._series_cache: dict[tuple[str, int | None], list[SeriesCandidate]] = {}
        self._movie_cache: dict[tuple[str, int | None], list[MovieCandidate]] = {}

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        key = (title.casefold(), year)
        if key not in self._series_cache:
            params: dict[str, Any] = {"query": title}
            if year is not None:
                params["first_air_date_year"] = year
            results = self._get("/search/tv", params)
            self._series_cache[key] = [
                SeriesCandidate(
                    title=r["name"],
                    year=_year(r.get("first_air_date")),
                    tmdb_id=r.get("id"),
                )
                for r in results
                if r.get("name")
            ]
        return self._series_cache[key]

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        key = (title.casefold(), year)
        if key not in self._movie_cache:
            params: dict[str, Any] = {"query": title}
            if year is not None:
                params["primary_release_year"] = year
            results = self._get("/search/movie", params)
            self._movie_cache[key] = [
                MovieCandidate(
                    title=r["title"],
                    year=_year(r.get("release_date")),
                    tmdb_id=r.get("id"),
                )
                for r in results
                if r.get("title")
            ]
        return self._movie_cache[key]

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """GET a TMDb search endpoint and return its ``results`` list."""
        try:
            response = self._client.get(path, params={**params, "api_key": self._api_key})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"TMDb {path} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:  # network/timeout/transport
            raise ProviderError(f"TMDb {path} request failed: {exc}") from exc

        payload = response.json()
        results = payload.get("results", [])
        return results if isinstance(results, list) else []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TmdbProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
