# SPDX-License-Identifier: GPL-3.0-or-later
"""Metadata providers (TMDb, TVDB, AniDB, …) behind a common interface."""

from __future__ import annotations

from .base import MetadataProvider
from .tmdb import TmdbProvider

__all__ = ["MetadataProvider", "TmdbProvider"]
