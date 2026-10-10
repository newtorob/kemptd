# SPDX-License-Identifier: GPL-3.0-or-later
"""Metadata providers (TMDb, TVDB, AniDB, …) behind a common interface."""

from __future__ import annotations

from .base import AbsoluteResolver, MetadataProvider
from .tmdb import TmdbProvider
from .tvdb import TvdbProvider

__all__ = ["AbsoluteResolver", "MetadataProvider", "TmdbProvider", "TvdbProvider"]
