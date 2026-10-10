# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for destination-path templating."""

from __future__ import annotations

from pathlib import PurePath

import pytest

from kemptd.models import (
    Candidate,
    Confidence,
    MatchResult,
    MediaKind,
    MovieCandidate,
    ParsedMedia,
    SeriesCandidate,
)
from kemptd.template import TemplateError, relative_path


def _match(parsed: ParsedMedia, candidate: Candidate | None) -> MatchResult:
    return MatchResult(parsed, candidate, 1.0, Confidence.HIGH, "rationale")


def test_movie_path() -> None:
    parsed = ParsedMedia(raw="x", kind=MediaKind.MOVIE, title="Inception", year=2010)
    match = _match(parsed, MovieCandidate("Inception", 2010, tmdb_id=27205))
    assert relative_path(match, ".mkv") == PurePath("Inception (2010)", "Inception (2010).mkv")


def test_episode_path() -> None:
    parsed = ParsedMedia(
        raw="x", kind=MediaKind.EPISODE, title="Slow Horses", season=2, episodes=(6,)
    )
    match = _match(parsed, SeriesCandidate("Slow Horses", 2022))
    assert relative_path(match, "mkv") == PurePath(
        "Slow Horses (2022)", "Season 02", "Slow Horses - S02E06.mkv"
    )


def test_multi_episode_filename() -> None:
    parsed = ParsedMedia(raw="x", kind=MediaKind.EPISODE, title="Show", season=1, episodes=(1, 2))
    match = _match(parsed, SeriesCandidate("Show", 2000))
    assert relative_path(match, ".mkv").name == "Show - S01E01-E02.mkv"


def test_illegal_characters_are_stripped() -> None:
    parsed = ParsedMedia(raw="x", kind=MediaKind.MOVIE, title="Face/Off", year=1997)
    match = _match(parsed, MovieCandidate("Face/Off", 1997))
    assert relative_path(match, ".mkv") == PurePath("FaceOff (1997)", "FaceOff (1997).mkv")


def test_no_candidate_raises() -> None:
    parsed = ParsedMedia(raw="x", kind=MediaKind.EPISODE, title="X", season=1, episodes=(1,))
    with pytest.raises(TemplateError, match="no candidate"):
        relative_path(MatchResult(parsed, None, 0.0, Confidence.NONE, "-"), ".mkv")


def test_absolute_numbered_episode_raises() -> None:
    parsed = ParsedMedia(
        raw="x", kind=MediaKind.EPISODE, title="Black Clover", absolute_episodes=(91,)
    )
    match = _match(parsed, SeriesCandidate("Black Clover", 2017))
    with pytest.raises(TemplateError, match="season"):
        relative_path(match, ".mkv")
