# SPDX-License-Identifier: GPL-3.0-or-later
"""TheTVDB (v4) metadata provider with anime absolute-number resolution.

Implements :class:`~kemptd.providers.base.MetadataProvider` *and*
:class:`~kemptd.providers.base.AbsoluteResolver`: beyond series/movie search it
can map an anime absolute episode number (e.g. "091") to its aired season and
episode, which is what the planner needs to file absolute-numbered packs.

The HTTP client is injectable, so the whole thing — including the login
handshake and episode pagination — is exercised offline in ``tests/test_tvdb.py``
with ``httpx.MockTransport``. Logins and per-series episode maps are memoized.
"""

from __future__ import annotations

from typing import Any

import httpx

from kemptd.errors import ProviderError
from kemptd.models import EpisodeNumber, MovieCandidate, SeriesCandidate

__all__ = ["TvdbProvider"]

_BASE_URL = "https://api4.thetvdb.com/v4"
_TIMEOUT = 10.0
_MAX_PAGES = 100  # safety bound on episode pagination


def _int_or_none(value: Any) -> int | None:
    """TVDB returns ids/years as strings; coerce the numeric ones to ``int``."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


class TvdbProvider:
    """Look up series/movies and resolve anime absolute numbering via TVDB v4."""

    name = "tvdb"

    def __init__(
        self, api_key: str, *, pin: str | None = None, client: httpx.Client | None = None
    ) -> None:
        if not api_key:
            raise ProviderError("TVDB API key is required")
        self._api_key = api_key
        self._pin = pin
        self._client = client or httpx.Client(base_url=_BASE_URL, timeout=_TIMEOUT)
        self._token: str | None = None
        self._series_cache: dict[tuple[str, int | None], list[SeriesCandidate]] = {}
        self._movie_cache: dict[tuple[str, int | None], list[MovieCandidate]] = {}
        self._episode_maps: dict[int, dict[int, EpisodeNumber]] = {}

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        key = (title.casefold(), year)
        if key not in self._series_cache:
            params: dict[str, Any] = {"query": title, "type": "series"}
            if year is not None:
                params["year"] = year
            data = self._get("/search", params).get("data") or []
            self._series_cache[key] = [
                SeriesCandidate(
                    title=r["name"],
                    year=_int_or_none(r.get("year")),
                    tvdb_id=_int_or_none(r.get("tvdb_id")),
                )
                for r in data
                if r.get("name")
            ]
        return self._series_cache[key]

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        key = (title.casefold(), year)
        if key not in self._movie_cache:
            params: dict[str, Any] = {"query": title, "type": "movie"}
            if year is not None:
                params["year"] = year
            data = self._get("/search", params).get("data") or []
            self._movie_cache[key] = [
                MovieCandidate(title=r["name"], year=_int_or_none(r.get("year")))
                for r in data
                if r.get("name")
            ]
        return self._movie_cache[key]

    def resolve_absolute(
        self, series: SeriesCandidate, absolute_number: int
    ) -> EpisodeNumber | None:
        if series.tvdb_id is None:
            return None
        return self._episode_map(series.tvdb_id).get(absolute_number)

    def _episode_map(self, series_id: int) -> dict[int, EpisodeNumber]:
        """Fetch and memoize ``{absolute_number: EpisodeNumber}`` for a series."""
        if series_id not in self._episode_maps:
            mapping: dict[int, EpisodeNumber] = {}
            path: str | None = f"/series/{series_id}/episodes/default"
            params: dict[str, Any] | None = {"page": 0}
            pages = 0
            while path is not None and pages < _MAX_PAGES:
                payload = self._get(path, params)
                data = payload.get("data") or {}
                for ep in data.get("episodes") or []:
                    absolute = ep.get("absoluteNumber")
                    season = ep.get("seasonNumber")
                    number = ep.get("number")
                    if (
                        isinstance(absolute, int)
                        and isinstance(season, int)
                        and isinstance(number, int)
                    ):
                        mapping[absolute] = EpisodeNumber(season, number)
                path = (payload.get("links") or {}).get("next")
                params = None  # the "next" link already carries the page cursor
                pages += 1
            self._episode_maps[series_id] = mapping
        return self._episode_maps[series_id]

    def _ensure_token(self) -> None:
        if self._token is not None:
            return
        body: dict[str, str] = {"apikey": self._api_key}
        if self._pin:
            body["pin"] = self._pin
        try:
            response = self._client.post("/login", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"TVDB login returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"TVDB login request failed: {exc}") from exc
        token = (response.json().get("data") or {}).get("token")
        if not token:
            raise ProviderError("TVDB login returned no token")
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self._ensure_token()
        try:
            response = self._client.get(path, params=params or {})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"TVDB {path} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"TVDB {path} request failed: {exc}") from exc
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TvdbProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
