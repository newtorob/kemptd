# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnose metadata mismatches in an existing Jellyfin library.

Read-only. For every movie/series already in the library, kemptd re-derives the
*correct* identity from the file on disk (its real name is ground truth, unlike
the server's possibly-wrong match) and flags where the server's provider id
disagrees. It changes nothing — it just produces the list a later fix would act
on. The Jellyfin HTTP client is injectable, so this is fully testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import httpx

from .errors import ProviderError, ServerError
from .matching import best_match
from .models import Candidate, Confidence, MediaKind, MovieCandidate, SeriesCandidate
from .parse import parse_path
from .providers.base import MetadataProvider

__all__ = ["JellyfinLibrary", "LibraryItem", "Mismatch", "diagnose_library"]

_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class LibraryItem:
    """A movie or series as the server currently sees it."""

    id: str
    name: str
    is_movie: bool
    path: str | None
    year: int | None
    provider_ids: dict[str, str]


@dataclass(frozen=True, slots=True)
class Mismatch:
    """A library item whose server identity disagrees with kemptd's."""

    path: str
    is_movie: bool
    current_name: str
    current_year: int | None
    current_id: str | None
    proposed_title: str
    proposed_year: int | None
    proposed_id: str
    confidence: Confidence
    rationale: str


class JellyfinLibrary:
    """Read the movie/series catalog from a Jellyfin server via its API."""

    def __init__(self, base_url: str, api_key: str, *, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ServerError("Jellyfin API key is required")
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=_TIMEOUT)

    def items(self) -> list[LibraryItem]:
        payload = self._get(
            "/Items",
            {
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "ProviderIds,Path,ProductionYear",
            },
        )
        items: list[LibraryItem] = []
        for raw in payload.get("Items") or []:
            kind = raw.get("Type")
            if kind not in ("Movie", "Series"):
                continue
            provider_ids = {
                str(k): str(v) for k, v in (raw.get("ProviderIds") or {}).items() if v is not None
            }
            items.append(
                LibraryItem(
                    id=str(raw.get("Id", "")),
                    name=str(raw.get("Name", "")),
                    is_movie=kind == "Movie",
                    path=raw.get("Path"),
                    year=raw.get("ProductionYear"),
                    provider_ids=provider_ids,
                )
            )
        return items

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(
                path,
                params=params,
                headers={"Authorization": f'MediaBrowser Token="{self._api_key}"'},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ServerError(f"Jellyfin {path} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ServerError(f"Jellyfin {path} request failed: {exc}") from exc
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JellyfinLibrary:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _candidate_id(candidate: Candidate) -> tuple[str, int] | None:
    """Return the ``(jellyfin_provider_key, id)`` to compare against, if any."""
    if isinstance(candidate, MovieCandidate) and candidate.tmdb_id is not None:
        return ("Tmdb", candidate.tmdb_id)
    if isinstance(candidate, SeriesCandidate):
        if candidate.tmdb_id is not None:
            return ("Tmdb", candidate.tmdb_id)
        if candidate.tvdb_id is not None:
            return ("Tvdb", candidate.tvdb_id)
    return None


def _diagnose_item(item: LibraryItem, provider: MetadataProvider) -> Mismatch | None:
    """Return a mismatch for *item* if kemptd confidently disagrees with the server."""
    if not item.path:
        return None
    parsed = parse_path(item.path)
    title = parsed.title or item.name
    if not title:
        return None

    wanted = MediaKind.MOVIE if item.is_movie else MediaKind.EPISODE
    probe = replace(parsed, kind=wanted, title=title)
    try:
        if item.is_movie:
            candidates: list[Candidate] = list(
                provider.search_movie(title, year=probe.year or item.year)
            )
        else:
            candidates = list(provider.search_series(title, year=probe.year or item.year))
    except ProviderError:
        return None

    result = best_match(probe, candidates)
    if result.candidate is None or result.confidence is not Confidence.HIGH:
        return None
    identity = _candidate_id(result.candidate)
    if identity is None:
        return None

    key, proposed = identity
    current = item.provider_ids.get(key)
    if current is not None and current.isdigit() and int(current) == proposed:
        return None  # server already agrees

    return Mismatch(
        path=item.path,
        is_movie=item.is_movie,
        current_name=item.name,
        current_year=item.year,
        current_id=f"{key.lower()}:{current}" if current else None,
        proposed_title=result.candidate.title,
        proposed_year=result.candidate.year,
        proposed_id=f"{key.lower()}:{proposed}",
        confidence=result.confidence,
        rationale=result.rationale,
    )


def diagnose_library(
    library: JellyfinLibrary, provider: MetadataProvider, *, limit: int | None = None
) -> list[Mismatch]:
    """Return the confidently-detected metadata mismatches in *library*."""
    mismatches: list[Mismatch] = []
    for index, item in enumerate(library.items()):
        if limit is not None and index >= limit:
            break
        mismatch = _diagnose_item(item, provider)
        if mismatch is not None:
            mismatches.append(mismatch)
    return mismatches
