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


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved configuration for a kemptd run."""

    tmdb_api_key: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables (defaults to ``os.environ``)."""
        source = os.environ if env is None else env
        return cls(tmdb_api_key=source.get(_TMDB_API_KEY))
