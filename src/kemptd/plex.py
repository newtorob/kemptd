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

from typing import Any

import httpx

from .diagnose import LibraryItem
from .errors import ServerError

__all__ = ["PlexServer"]

_TIMEOUT = 30.0
_GUID_KEYS = {"tmdb": "Tmdb", "tvdb": "Tvdb", "imdb": "Imdb"}


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

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(
                path,
                params={**params, "X-Plex-Token": self._token},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ServerError(f"Plex {path} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ServerError(f"Plex {path} request failed: {exc}") from exc
        payload = response.json()
        container = payload.get("MediaContainer") if isinstance(payload, dict) else None
        return container if isinstance(container, dict) else {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PlexServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
