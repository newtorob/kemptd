# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for candidate scoring and match classification."""

from __future__ import annotations

from kemptd.matching import best_match, title_similarity
from kemptd.models import (
    Candidate,
    Confidence,
    MediaKind,
    MovieCandidate,
    ParsedMedia,
    SeriesCandidate,
)


def _episode(title: str, *, year: int | None = None) -> ParsedMedia:
    return ParsedMedia(
        raw=title, kind=MediaKind.EPISODE, title=title, year=year, season=1, episodes=(1,)
    )


def test_exact_title_is_high_confidence() -> None:
    parsed = _episode("Slow Horses")
    result = best_match(parsed, [SeriesCandidate("Slow Horses", 2022)])
    assert result.candidate is not None
    assert result.candidate.title == "Slow Horses"
    assert result.confidence is Confidence.HIGH
    assert result.is_actionable


def test_picks_real_show_over_parody() -> None:
    """The regression that bit us: don't match 'Dragon Ball Z' to the Abridged parody."""
    parsed = _episode("Dragon Ball Z TV Series")
    candidates: list[Candidate] = [
        SeriesCandidate("Dragon Ball Z Abridged", 2008),
        SeriesCandidate("Dragon Ball Z", 1989),
    ]
    result = best_match(parsed, candidates)
    assert result.candidate is not None
    assert result.candidate.title == "Dragon Ball Z"
    assert result.confidence is Confidence.HIGH


def test_reworded_title_scores_reviewable_not_rejected() -> None:
    """'...Fionna Cake' vs '...Fionna and Cake' should be close enough to review."""
    sim = title_similarity("Adventure Time Fionna Cake", "Adventure Time: Fionna and Cake")
    assert sim >= 0.80


def test_wrong_year_penalized() -> None:
    parsed = _episode("The Office", year=2005)
    us = best_match(parsed, [SeriesCandidate("The Office", 2005)])
    uk = best_match(parsed, [SeriesCandidate("The Office", 2001)])
    assert us.score > uk.score


def test_no_candidates_is_none() -> None:
    result = best_match(_episode("Whatever"), [])
    assert result.candidate is None
    assert result.confidence is Confidence.NONE


def test_movie_candidate_rejected_for_episode() -> None:
    parsed = _episode("Billions")
    result = best_match(parsed, [MovieCandidate("Billions", 2016)])
    assert result.candidate is None
    assert result.confidence is Confidence.NONE


def test_unparsed_title_scores_zero() -> None:
    parsed = ParsedMedia(raw="???", kind=MediaKind.EPISODE, title=None, season=1, episodes=(1,))
    result = best_match(parsed, [SeriesCandidate("Anything")])
    assert result.confidence is Confidence.NONE


def _movie(raw: str, title: str, *, year: int | None = None) -> ParsedMedia:
    return ParsedMedia(raw=raw, kind=MediaKind.MOVIE, title=title, year=year)


def test_recovers_full_title_when_guessit_drops_a_part() -> None:
    """Live-data regression: guessit truncates 'Hostel: Part III' to 'Hostel'.

    Scoring against the fuller title from the raw name must beat the shorter,
    wrong candidate that the truncated title matched perfectly.
    """
    parsed = _movie("Hostel.Part.III.2011.1080p.BluRay.mkv", "Hostel", year=2011)
    candidates: list[Candidate] = [
        MovieCandidate("Hostel", 2005, tmdb_id=1),
        MovieCandidate("Hostel: Part III", 2011, tmdb_id=2),
    ]
    result = best_match(parsed, candidates)
    assert result.candidate is not None
    assert result.candidate.title == "Hostel: Part III"


def test_recovers_dropped_trailing_word() -> None:
    """'The Space Between Us' parsed as 'The Space Between' must not win the shorter film."""
    parsed = _movie("The.Space.Between.Us.2017.1080p.mkv", "The Space Between", year=2017)
    candidates: list[Candidate] = [
        MovieCandidate("The Space Between", 2017, tmdb_id=1),
        MovieCandidate("The Space Between Us", 2017, tmdb_id=2),
    ]
    result = best_match(parsed, candidates)
    assert result.candidate is not None
    assert result.candidate.title == "The Space Between Us"


def test_scene_prefix_does_not_break_clean_match() -> None:
    parsed = _movie(
        "www.UIndex.org - Anatomy of a Fall 2023 1080p BluRay HEVC.mkv",
        "Anatomy of a Fall",
        year=2023,
    )
    result = best_match(parsed, [MovieCandidate("Anatomy of a Fall", 2023, tmdb_id=1)])
    assert result.candidate is not None
    assert result.confidence is Confidence.HIGH
