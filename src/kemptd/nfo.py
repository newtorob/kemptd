# SPDX-License-Identifier: GPL-3.0-or-later
"""NFO sidecar generation.

A ``.nfo`` file carrying a provider id lets Jellyfin, Plex, and Kodi match a
file *deterministically* — no fuzzy title guessing, so tricky names (parodies,
remakes, alternate cuts) land on the right entry. The builders here are pure
(they return XML strings); :func:`nfo_targets` maps a moved file to the sidecars
that should sit beside it, and the apply layer does the actual writing.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from .models import MediaMeta

__all__ = ["movie_nfo_xml", "nfo_targets", "series_nfo_xml"]

_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _uniqueid_lines(meta: MediaMeta) -> list[str]:
    """Emit ``<uniqueid>`` elements, marking the first provider id as default."""
    lines: list[str] = []
    ids = [("tmdb", meta.tmdb_id), ("tvdb", meta.tvdb_id)]
    default = True
    for source, value in ids:
        if value is None:
            continue
        flag = ' default="true"' if default else ""
        lines.append(f'  <uniqueid type="{source}"{flag}>{value}</uniqueid>')
        default = False
    return lines


def _nfo_xml(root: str, meta: MediaMeta) -> str:
    body = [f"<{root}>", f"  <title>{escape(meta.title)}</title>"]
    if meta.year is not None:
        body.append(f"  <year>{meta.year}</year>")
    body.extend(_uniqueid_lines(meta))
    body.append(f"</{root}>")
    return _HEADER + "\n" + "\n".join(body) + "\n"


def series_nfo_xml(meta: MediaMeta) -> str:
    """Build a ``tvshow.nfo`` document for a matched series."""
    return _nfo_xml("tvshow", meta)


def movie_nfo_xml(meta: MediaMeta) -> str:
    """Build a movie ``.nfo`` document."""
    return _nfo_xml("movie", meta)


def nfo_targets(destination: Path, meta: MediaMeta) -> list[tuple[Path, str]]:
    """Return ``(sidecar_path, xml)`` pairs to write for a file moved to *destination*.

    * Series: a single ``tvshow.nfo`` at the show-root folder (``Show (Year)/``),
      shared by every episode — the series id is what servers key on.
    * Movie: a ``<name>.nfo`` next to the movie file (Kodi/Jellyfin convention).
    """
    if meta.is_series:
        # destination is <root>/Show (Year)/Season NN/<file> → show root is two up.
        show_root = destination.parent.parent
        return [(show_root / "tvshow.nfo", series_nfo_xml(meta))]
    return [(destination.with_suffix(".nfo"), movie_nfo_xml(meta))]
