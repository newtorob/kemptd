# SPDX-License-Identifier: GPL-3.0-or-later
"""Runtime configuration.

Kept deliberately small and explicit: settings come from the environment (or are
passed directly in tests), never read implicitly at import time.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["Settings"]

_TMDB_API_KEY = "KEMPTD_TMDB_API_KEY"
_TVDB_API_KEY = "KEMPTD_TVDB_API_KEY"
_TVDB_PIN = "KEMPTD_TVDB_PIN"
_PLEX_URL = "KEMPTD_PLEX_URL"
_PLEX_TOKEN = "KEMPTD_PLEX_TOKEN"
_JELLYFIN_URL = "KEMPTD_JELLYFIN_URL"
_JELLYFIN_API_KEY = "KEMPTD_JELLYFIN_API_KEY"


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved configuration for a kemptd run."""

    tmdb_api_key: str | None = None
    tvdb_api_key: str | None = None
    tvdb_pin: str | None = None
    plex_url: str | None = None
    plex_token: str | None = None
    jellyfin_url: str | None = None
    jellyfin_api_key: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables (defaults to ``os.environ``)."""
        source = os.environ if env is None else env
        return cls(
            tmdb_api_key=source.get(_TMDB_API_KEY),
            tvdb_api_key=source.get(_TVDB_API_KEY),
            tvdb_pin=source.get(_TVDB_PIN),
            plex_url=source.get(_PLEX_URL),
            plex_token=source.get(_PLEX_TOKEN),
            jellyfin_url=source.get(_JELLYFIN_URL),
            jellyfin_api_key=source.get(_JELLYFIN_API_KEY),
        )
