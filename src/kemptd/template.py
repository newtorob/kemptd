# SPDX-License-Identifier: GPL-3.0-or-later
"""Naming templates.

Turns a confirmed :class:`~kemptd.models.MatchResult` into a clean,
library-relative path following the Jellyfin/Plex/Kodi convention. Pure: no IO.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from .models import MatchResult, MovieCandidate

__all__ = ["TemplateError", "relative_path"]

_ILLEGAL = re.compile(r'[/\\:*?"<>|]')


class TemplateError(ValueError):
    """The match cannot be laid out deterministically (e.g. no season number)."""


def _sanitize(name: str) -> str:
    """Strip path-illegal characters and trailing dots/spaces (Windows-safe)."""
    return _ILLEGAL.sub("", name).strip().rstrip(". ")


def _stamped(title: str, year: int | None) -> str:
    base = _sanitize(title)
    return f"{base} ({year})" if year else base


def _episode_tag(episodes: tuple[int, ...]) -> str:
    return "E" + "-E".join(f"{e:02d}" for e in episodes)


def relative_path(match: MatchResult, suffix: str) -> PurePath:
    """Return the library-relative destination path for a confirmed *match*.

    Args:
        match: A match whose candidate is set (see :attr:`MatchResult.is_actionable`).
        suffix: The source file extension, with or without a leading dot.

    Raises:
        TemplateError: If there is no candidate, or an episode lacks the
            season/episode numbers needed for a deterministic layout (e.g.
            absolute-numbered anime, which is routed to manual review upstream).
    """
    candidate = match.candidate
    if candidate is None:
        raise TemplateError("match has no candidate")

    suffix = suffix if suffix.startswith(".") else f".{suffix}"

    if isinstance(candidate, MovieCandidate):
        folder = _stamped(candidate.title, candidate.year)
        return PurePath(folder, f"{folder}{suffix}")

    parsed = match.parsed
    if parsed.season is None or not parsed.episodes:
        raise TemplateError("episode lacks a season/episode number")

    show = _stamped(candidate.title, candidate.year)
    season = f"Season {parsed.season:02d}"
    filename = (
        f"{_sanitize(candidate.title)} - "
        f"S{parsed.season:02d}{_episode_tag(parsed.episodes)}{suffix}"
    )
    return PurePath(show, season, filename)
