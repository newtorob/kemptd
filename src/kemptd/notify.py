# SPDX-License-Identifier: GPL-3.0-or-later
"""Media-server rescan hooks.

After an apply moves files into place, the media server still needs to notice.
These notifiers trigger a library refresh so Plex and Jellyfin re-index (and,
with NFO sidecars, re-match) the freshly-organized files automatically. The
HTTP client is injectable, so the whole module is testable without a server.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import httpx

from .config import Settings
from .errors import ConfigError, KemptdError

__all__ = [
    "JellyfinNotifier",
    "NotifyError",
    "PlexNotifier",
    "ServerNotifier",
    "build_notifiers",
]

_TIMEOUT = 15.0


class NotifyError(KemptdError):
    """A media server could not be asked to rescan."""


@runtime_checkable
class ServerNotifier(Protocol):
    """A media server that can be told to rescan its libraries."""

    name: str

    def refresh(self) -> None: ...


class PlexNotifier:
    """Trigger a full-library scan on a Plex Media Server."""

    name = "plex"

    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=_TIMEOUT)

    def refresh(self) -> None:
        try:
            response = self._client.get(
                "/library/sections/all/refresh", params={"X-Plex-Token": self._token}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotifyError(f"Plex refresh failed: {exc}") from exc


class JellyfinNotifier:
    """Trigger a library scan on a Jellyfin server."""

    name = "jellyfin"

    def __init__(self, base_url: str, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=_TIMEOUT)

    def refresh(self) -> None:
        try:
            response = self._client.post(
                "/Library/Refresh",
                headers={"Authorization": f'MediaBrowser Token="{self._api_key}"'},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotifyError(f"Jellyfin refresh failed: {exc}") from exc


def build_notifiers(names: Iterable[str], settings: Settings) -> list[ServerNotifier]:
    """Construct the requested notifiers, raising :class:`ConfigError` if unconfigured."""
    notifiers: list[ServerNotifier] = []
    for raw in names:
        name = raw.strip().lower()
        if name == "plex":
            if not (settings.plex_url and settings.plex_token):
                raise ConfigError("Plex rescan needs KEMPTD_PLEX_URL and KEMPTD_PLEX_TOKEN")
            notifiers.append(PlexNotifier(settings.plex_url, settings.plex_token))
        elif name == "jellyfin":
            if not (settings.jellyfin_url and settings.jellyfin_api_key):
                raise ConfigError(
                    "Jellyfin rescan needs KEMPTD_JELLYFIN_URL and KEMPTD_JELLYFIN_API_KEY"
                )
            notifiers.append(JellyfinNotifier(settings.jellyfin_url, settings.jellyfin_api_key))
        elif name:
            raise ConfigError(f"unknown rescan target {raw!r} (expected 'plex' or 'jellyfin')")
    return notifiers
