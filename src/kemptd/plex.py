# SPDX-License-Identifier: GPL-3.0-or-later
"""Plex Media Server integration.

Reads a Plex library catalog for :mod:`kemptd.diagnose` (Plex exposes the
``tmdb://`` / ``tvdb://`` ids it matched, and the real file path, so no NFO or
path-mapping is needed — Plex is usually native). Correcting a wrong match on
Plex uses Plex's own ``/match`` API (Plex ignores ``.nfo`` sidecars), which is
why this is a separate path from the Jellyfin NFO flow.

The HTTP client is injectable, so the whole thing is testable offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from .diagnose import LibraryItem, Mismatch
from .errors import ServerError

__all__ = ["PlexFixReport", "PlexMatch", "PlexServer", "apply_plex_fixes"]

_TIMEOUT = 30.0
_GUID_KEYS = {"tmdb": "Tmdb", "tvdb": "Tvdb", "imdb": "Imdb"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.lower()).strip()


@dataclass(frozen=True, slots=True)
class PlexMatch:
    """A manual-match candidate returned by Plex."""

    name: str
    year: int | None
    guid: str


@dataclass(slots=True)
class PlexFixReport:
    applied: int = 0
    skipped: int = 0


def _provider_ids(guids: list[dict[str, Any]]) -> dict[str, str]:
    """Map Plex ``Guid`` entries (``tmdb://584``) to kemptd's id dict."""
    ids: dict[str, str] = {}
    for guid in guids or []:
        raw = str(guid.get("id", ""))
        scheme, _, value = raw.partition("://")
        key = _GUID_KEYS.get(scheme)
        if key and value:
            ids[key] = value
    return ids


def _item_path(meta: dict[str, Any], is_movie: bool) -> str | None:
    """Movie → the media file; show → its library folder."""
    if is_movie:
        try:
            return str(meta["Media"][0]["Part"][0]["file"])
        except (KeyError, IndexError, TypeError):
            return None
    locations = meta.get("Location") or []
    return str(locations[0]["path"]) if locations else None


class PlexServer:
    """Read a Plex catalog and (later) correct matches via the Plex API."""

    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None) -> None:
        if not token:
            raise ServerError("Plex token is required")
        self._token = token
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=_TIMEOUT)

    def items(self) -> list[LibraryItem]:
        items: list[LibraryItem] = []
        for key, is_movie in self._sections():
            container = self._get(
                f"/library/sections/{key}/all",
                {"includeGuids": "1", "includeLocations": "1"},
            )
            for meta in container.get("Metadata") or []:
                items.append(
                    LibraryItem(
                        id=str(meta.get("ratingKey", "")),
                        name=str(meta.get("title", "")),
                        is_movie=is_movie,
                        path=_item_path(meta, is_movie),
                        year=meta.get("year"),
                        provider_ids=_provider_ids(meta.get("Guid", [])),
                    )
                )
        return items

    def _sections(self) -> list[tuple[str, bool]]:
        container = self._get("/library/sections", {})
        sections: list[tuple[str, bool]] = []
        for directory in container.get("Directory") or []:
            kind = directory.get("type")
            if kind in ("movie", "show"):
                sections.append((str(directory["key"]), kind == "movie"))
        return sections

    def match_candidates(
        self, rating_key: str, *, title: str | None = None, year: int | None = None
    ) -> list[PlexMatch]:
        """Return Plex's manual-match candidates for an item."""
        params: dict[str, Any] = {"manual": "1"}
        if title:
            params["title"] = title
        if year is not None:
            params["year"] = str(year)
        container = self._get(f"/library/metadata/{rating_key}/matches", params)
        return [
            PlexMatch(name=str(r.get("name", "")), year=r.get("year"), guid=str(r.get("guid", "")))
            for r in container.get("SearchResult") or []
            if r.get("guid")
        ]

    def apply_match(self, rating_key: str, guid: str, name: str) -> None:
        """Lock an item to a chosen match (Plex re-pulls metadata for that guid)."""
        self._request("PUT", f"/library/metadata/{rating_key}/match", {"guid": guid, "name": name})

    def provider_ids(self, rating_key: str) -> dict[str, str]:
        """Current provider ids for an item — used to verify a fix landed."""
        container = self._get(f"/library/metadata/{rating_key}", {"includeGuids": "1"})
        metas = container.get("Metadata") or []
        return _provider_ids(metas[0].get("Guid", [])) if metas else {}

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._request("GET", path, params)
        payload = response.json()
        container = payload.get("MediaContainer") if isinstance(payload, dict) else None
        return container if isinstance(container, dict) else {}

    def _request(self, method: str, path: str, params: dict[str, Any]) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                path,
                params={**params, "X-Plex-Token": self._token},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ServerError(f"Plex {path} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ServerError(f"Plex {path} request failed: {exc}") from exc
        return response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PlexServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _pick_candidate(candidates: list[PlexMatch], title: str, year: int | None) -> PlexMatch | None:
    """Pick the one candidate that exactly matches *title* and *year*.

    Deliberately strict: if zero or more than one candidate matches, return None
    so the item is skipped rather than guessed — Plex correction must be safe.
    """
    want = _norm(title)
    hits = [c for c in candidates if _norm(c.name) == want and c.year == year]
    return hits[0] if len(hits) == 1 else None


def apply_plex_fixes(
    server: PlexServer, mismatches: list[Mismatch], *, dry_run: bool = False
) -> PlexFixReport:
    """Correct each mismatch on Plex via its match API (Plex ignores .nfo).

    Only applies when exactly one candidate matches the proposed title+year;
    anything ambiguous is skipped. Nothing is written in ``dry_run``.
    """
    report = PlexFixReport()
    for mismatch in mismatches:
        search = mismatch.proposed_title.replace('"', "")
        candidates = server.match_candidates(
            mismatch.item_id, title=search, year=mismatch.proposed_year
        )
        pick = _pick_candidate(candidates, mismatch.proposed_title, mismatch.proposed_year)
        if pick is None:
            report.skipped += 1
            continue
        if not dry_run:
            server.apply_match(mismatch.item_id, pick.guid, pick.name)
        report.applied += 1
    return report
