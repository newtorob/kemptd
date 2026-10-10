# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan construction.

Turns (source file, match) pairs into an immutable, serializable plan of file
moves. Pure: no filesystem access — collision handling and execution live in
:mod:`kemptd.apply`. Only HIGH-confidence, templatable matches become moves;
everything else is an auditable skip with a reason.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .models import Confidence, MatchResult, MediaMeta, MovieCandidate, SeriesCandidate
from .template import TemplateError, relative_path

__all__ = ["Plan", "PlanAction", "PlanItem", "build_plan"]


class PlanAction(str, Enum):
    MOVE = "move"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class PlanItem:
    source: Path
    destination: Path | None
    action: PlanAction
    confidence: Confidence
    reason: str
    meta: MediaMeta | None = None


def _meta_from_match(match: MatchResult) -> MediaMeta | None:
    """Capture the provider identity of an actionable match for NFO sidecars."""
    candidate = match.candidate
    if isinstance(candidate, SeriesCandidate):
        return MediaMeta(
            True, candidate.title, candidate.year, candidate.tmdb_id, candidate.tvdb_id
        )
    if isinstance(candidate, MovieCandidate):
        return MediaMeta(False, candidate.title, candidate.year, candidate.tmdb_id)
    return None


@dataclass(frozen=True, slots=True)
class Plan:
    items: tuple[PlanItem, ...]

    @property
    def moves(self) -> tuple[PlanItem, ...]:
        return tuple(i for i in self.items if i.action is PlanAction.MOVE)

    @property
    def skips(self) -> tuple[PlanItem, ...]:
        return tuple(i for i in self.items if i.action is PlanAction.SKIP)


def build_plan(entries: Iterable[tuple[Path, MatchResult]], *, root: Path) -> Plan:
    """Compute intended moves under *root* for each ``(source, match)`` entry.

    Destinations are ``root / <templated relative path>``. A move is only emitted
    for an actionable match that templates cleanly and would actually change the
    path; anything else becomes a ``SKIP`` carrying the reason.
    """
    items: list[PlanItem] = []
    for source, match in entries:
        if not match.is_actionable:
            # Preserve the real cause (low score, provider error, unparsable, …).
            items.append(PlanItem(source, None, PlanAction.SKIP, match.confidence, match.rationale))
            continue
        try:
            destination = root / relative_path(match, source.suffix)
        except TemplateError as exc:
            items.append(PlanItem(source, None, PlanAction.SKIP, match.confidence, str(exc)))
            continue
        if destination == source:
            items.append(
                PlanItem(source, destination, PlanAction.SKIP, match.confidence, "already in place")
            )
            continue
        items.append(
            PlanItem(
                source,
                destination,
                PlanAction.MOVE,
                match.confidence,
                match.rationale,
                _meta_from_match(match),
            )
        )
    return Plan(tuple(items))
