# SPDX-License-Identifier: GPL-3.0-or-later
"""Metadata provider interface.

Concrete providers (TMDb, TVDB, AniDB) implement :class:`MetadataProvider` and
live behind this boundary so the pure core never imports a network client. This
keeps matching/planning deterministic and lets tests inject fakes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kemptd.models import MovieCandidate, SeriesCandidate

__all__ = ["MetadataProvider"]


@runtime_checkable
class MetadataProvider(Protocol):
    """A source of canonical series/movie metadata.

    Implementations are expected to be cached and rate-limited internally; the
    core calls them a lot during a scan.
    """

    name: str

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        """Return series candidates ranked by the provider's own relevance."""
        ...

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        """Return movie candidates ranked by the provider's own relevance."""
        ...
