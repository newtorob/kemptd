# SPDX-License-Identifier: GPL-3.0-or-later
"""Core domain value objects.

Everything here is immutable and free of IO so the parsing, matching, and
planning layers stay pure and trivially testable. Side effects (filesystem,
network) live at the edges in :mod:`kemptd.providers` and the apply layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MediaKind(str, Enum):
    """What a parsed filename appears to be."""

    MOVIE = "movie"
    EPISODE = "episode"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    """How much we trust a match, ordered worst-to-best."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ParsedMedia:
    """Structured facts extracted from a single media filename.

    This is the normalized output of :func:`kemptd.parse.parse_filename`; it
    deliberately mirrors only what we can know from the name itself, never from
    a metadata provider.
    """

    raw: str
    kind: MediaKind
    title: str | None
    year: int | None = None
    season: int | None = None
    episodes: tuple[int, ...] = ()
    absolute_episodes: tuple[int, ...] = ()
    container: str | None = None

    @property
    def is_absolute_numbered(self) -> bool:
        """True for anime-style absolute numbering with no season context."""
        return self.season is None and bool(self.absolute_episodes)

    @property
    def is_multi_episode(self) -> bool:
        return len(self.episodes) > 1


@dataclass(frozen=True, slots=True)
class SeriesCandidate:
    """A TV series as returned by a metadata provider."""

    title: str
    year: int | None = None
    tvdb_id: int | None = None
    tmdb_id: int | None = None


@dataclass(frozen=True, slots=True)
class MovieCandidate:
    """A movie as returned by a metadata provider."""

    title: str
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None


Candidate = SeriesCandidate | MovieCandidate


@dataclass(frozen=True, slots=True)
class MatchResult:
    """The outcome of scoring a :class:`ParsedMedia` against candidates."""

    parsed: ParsedMedia
    candidate: Candidate | None
    score: float
    confidence: Confidence
    rationale: str

    @property
    def is_actionable(self) -> bool:
        """Whether this match is safe to turn into a plan without review."""
        return self.candidate is not None and self.confidence is Confidence.HIGH


@dataclass(frozen=True, slots=True)
class EpisodeNumber:
    """An aired season/episode coordinate.

    The result of resolving an anime-style absolute number (e.g. "episode 91")
    against a provider's episode ordering.
    """

    season: int
    episode: int


@dataclass(frozen=True, slots=True)
class MediaMeta:
    """The confirmed provider identity of a matched file.

    Carried on a plan item so the apply layer can emit ``.nfo`` sidecars with a
    stable provider id — long after the live provider/match objects are gone
    (e.g. when applying a plan loaded back from JSON).
    """

    is_series: bool
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
