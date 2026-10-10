# SPDX-License-Identifier: GPL-3.0-or-later
"""Filename parsing.

Thin, deterministic adapter over :mod:`guessit` that normalizes its loosely
typed output into a :class:`~kemptd.models.ParsedMedia`. Pure: no IO, no
network, safe to call on untrusted strings.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any

from guessit import guessit

from .models import MediaKind, ParsedMedia

__all__ = ["parse_filename", "parse_path"]


def _first(value: Any) -> Any:
    """guessit returns a scalar *or* a list for multi-valued fields; take one."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _int_tuple(value: Any) -> tuple[int, ...]:
    """Coerce a guessit int/list-of-ints field into a sorted tuple of ints."""
    if value is None:
        return ()
    items = value if isinstance(value, list) else [value]
    return tuple(sorted(int(i) for i in items if isinstance(i, int)))


def _kind(raw_type: Any) -> MediaKind:
    match raw_type:
        case "movie":
            return MediaKind.MOVIE
        case "episode":
            return MediaKind.EPISODE
        case _:
            return MediaKind.UNKNOWN


def parse_filename(name: str, *, kind_hint: MediaKind | None = None) -> ParsedMedia:
    """Parse a single media *name* (file or release name) into structured facts.

    Args:
        name: The filename or release string, e.g. ``"The.Show.S01E02.1080p.mkv"``.
        kind_hint: Optional expectation (``MOVIE``/``EPISODE``) passed to guessit
            to disambiguate titles that could read either way.

    Returns:
        A :class:`ParsedMedia`. ``title`` may be ``None`` if nothing usable was found.
    """
    options: dict[str, Any] = {}
    if kind_hint in (MediaKind.MOVIE, MediaKind.EPISODE):
        options["type"] = kind_hint.value

    info: dict[str, Any] = dict(guessit(name, options))

    title = _first(info.get("title"))
    season = _first(info.get("season"))
    episodes = _int_tuple(info.get("episode"))
    absolute = _int_tuple(info.get("absolute_episode"))

    # Anime packs frequently yield absolute numbering with no season; guessit may
    # also surface absolute numbers in the ``episode`` field when no season exists.
    if (
        season is None
        and not absolute
        and episodes
        and _kind(info.get("type")) is MediaKind.EPISODE
    ):
        absolute, episodes = episodes, ()

    return ParsedMedia(
        raw=name,
        kind=_kind(info.get("type")),
        title=str(title) if title is not None else None,
        year=_first(info.get("year")),
        season=int(season) if isinstance(season, int) else None,
        episodes=episodes,
        absolute_episodes=absolute,
        container=_first(info.get("container")),
    )


def parse_path(path: str | PurePath, *, kind_hint: MediaKind | None = None) -> ParsedMedia:
    """Parse using both the parent folder and filename for extra context.

    Release info often lives on the folder (e.g. ``Show.S01.Pack/ep01.mkv``), so
    we feed guessit ``"<parent>/<name>"`` which it handles natively.
    """
    p = PurePath(path)
    hint = p.parent.name
    composed = f"{hint}/{p.name}" if hint and hint not in (".", "/") else p.name
    return parse_filename(composed, kind_hint=kind_hint)
