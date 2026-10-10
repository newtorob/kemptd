# SPDX-License-Identifier: GPL-3.0-or-later
"""Library scanning: walk files, parse, match against a provider, build a plan.

This is the orchestration seam between the pure core and the outside world. It
takes any :class:`~kemptd.providers.base.MetadataProvider`, so tests drive it
with a fake and never hit the network.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

from .matching import best_match
from .models import Candidate, Confidence, MatchResult, MediaKind, SeriesCandidate
from .parse import parse_path
from .plan import Plan, build_plan
from .providers.base import AbsoluteResolver, MetadataProvider

__all__ = ["VIDEO_SUFFIXES", "iter_videos", "match_media", "scan_library"]

VIDEO_SUFFIXES = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts", ".wmv"})
_MIN_SIZE_BYTES = 50 * 1024 * 1024  # ignore samples/extras


def iter_videos(root: Path, *, min_size: int = _MIN_SIZE_BYTES) -> Iterator[Path]:
    """Yield video files under *root* (recursively), skipping tiny samples."""
    if root.is_file():
        if root.suffix.lower() in VIDEO_SUFFIXES:
            yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
            try:
                if path.stat().st_size >= min_size:
                    yield path
            except OSError:
                continue


def match_media(parsed_source: Path, provider: MetadataProvider) -> MatchResult:
    """Parse one file and match it against *provider*, never raising on failure."""
    parsed = parse_path(parsed_source)
    if parsed.title is None:
        return MatchResult(parsed, None, 0.0, Confidence.NONE, "unparsable filename")

    from .errors import ProviderError  # local import keeps the core import-light

    candidates: Sequence[Candidate]
    try:
        if parsed.kind is MediaKind.MOVIE:
            candidates = provider.search_movie(parsed.title, year=parsed.year)
        else:
            candidates = provider.search_series(parsed.title, year=parsed.year)
    except ProviderError as exc:
        return MatchResult(parsed, None, 0.0, Confidence.NONE, f"provider error: {exc}")

    result = best_match(parsed, list(candidates))
    return _resolve_absolute(result, provider)


def _resolve_absolute(result: MatchResult, provider: MetadataProvider) -> MatchResult:
    """Rewrite an absolute-numbered anime match into aired season/episode form.

    Absolute-numbered files can't be templated (no season), so this upgrades them
    in place when the provider can resolve the ordering. Anything we can't resolve
    cleanly (unknown episode, or a pack spanning seasons) is left untouched, so it
    surfaces as an honest skip rather than a wrong guess.
    """
    if not (result.parsed.is_absolute_numbered and isinstance(result.candidate, SeriesCandidate)):
        return result
    if not isinstance(provider, AbsoluteResolver):
        return result

    from .errors import ProviderError

    resolved = []
    for absolute in result.parsed.absolute_episodes:
        try:
            episode = provider.resolve_absolute(result.candidate, absolute)
        except ProviderError:
            return result
        if episode is None:
            return result
        resolved.append(episode)

    seasons = {ep.season for ep in resolved}
    if len(seasons) != 1:
        return result  # a pack straddling seasons — don't invent a layout

    new_parsed = replace(
        result.parsed,
        season=seasons.pop(),
        episodes=tuple(ep.episode for ep in resolved),
        absolute_episodes=(),
    )
    return replace(result, parsed=new_parsed)


def scan_library(root: Path, provider: MetadataProvider, *, limit: int | None = None) -> Plan:
    """Scan *root*, match every video, and return a plan rooted at *root*.

    Destinations live under the same library directory (and thus the same
    filesystem) as the sources, so applying the plan uses fast atomic renames.
    """
    entries: list[tuple[Path, MatchResult]] = []
    for index, video in enumerate(iter_videos(root)):
        if limit is not None and index >= limit:
            break
        entries.append((video, match_media(video, provider)))
    return build_plan(entries, root=root)
