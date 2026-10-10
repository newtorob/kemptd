# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plan construction (pure; no filesystem access)."""

from __future__ import annotations

from pathlib import Path

from kemptd.models import Confidence, MatchResult, MediaKind, ParsedMedia, SeriesCandidate
from kemptd.plan import PlanAction, build_plan


def _entry(
    source: Path,
    title: str,
    *,
    season: int | None = 1,
    episode: int = 1,
    confidence: Confidence = Confidence.HIGH,
) -> tuple[Path, MatchResult]:
    parsed = ParsedMedia(
        raw=source.name,
        kind=MediaKind.EPISODE,
        title=title,
        season=season,
        episodes=(episode,) if season is not None else (),
        absolute_episodes=() if season is not None else (episode,),
    )
    match = MatchResult(parsed, SeriesCandidate(title, 2022), 1.0, confidence, "rationale")
    return source, match


def test_actionable_entry_becomes_move() -> None:
    src = Path("/src/Slow.Horses.S02E06.mkv")
    plan = build_plan([_entry(src, "Slow Horses", season=2, episode=6)], root=Path("/lib"))
    assert len(plan.moves) == 1
    move = plan.moves[0]
    assert move.action is PlanAction.MOVE
    assert move.destination == Path("/lib/Slow Horses (2022)/Season 02/Slow Horses - S02E06.mkv")


def test_low_confidence_is_skipped() -> None:
    plan = build_plan(
        [_entry(Path("/src/x.mkv"), "X", confidence=Confidence.LOW)], root=Path("/lib")
    )
    assert plan.moves == ()
    assert plan.skips[0].action is PlanAction.SKIP
    assert plan.skips[0].confidence is Confidence.LOW


def test_untemplatable_entry_is_skipped_with_reason() -> None:
    plan = build_plan(
        [_entry(Path("/src/bc.mkv"), "Black Clover", season=None, episode=91)], root=Path("/lib")
    )
    assert plan.moves == ()
    assert "season" in plan.skips[0].reason
