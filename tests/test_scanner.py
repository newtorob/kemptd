# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for library scanning, driven by a fake provider (no network)."""

from __future__ import annotations

from pathlib import Path

from kemptd.errors import ProviderError
from kemptd.models import MovieCandidate, SeriesCandidate
from kemptd.scanner import scan_library


class FakeProvider:
    """In-memory provider keyed by casefolded title."""

    name = "fake"

    def __init__(
        self,
        series: dict[str, list[SeriesCandidate]] | None = None,
        movies: dict[str, list[MovieCandidate]] | None = None,
    ) -> None:
        self._series = series or {}
        self._movies = movies or {}

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        return self._series.get(title.casefold(), [])

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        return self._movies.get(title.casefold(), [])


def _big(path: Path) -> None:
    """Create a sparse file large enough to clear the sample-size filter."""
    with path.open("wb") as handle:
        handle.truncate(60 * 1024 * 1024)


def test_scan_builds_move_for_matched_episode(tmp_path: Path) -> None:
    _big(tmp_path / "Slow.Horses.S02E06.1080p.WEB.mkv")
    provider = FakeProvider(series={"slow horses": [SeriesCandidate("Slow Horses", 2022)]})

    plan = scan_library(tmp_path, provider)

    assert len(plan.moves) == 1
    assert plan.moves[0].destination == (
        tmp_path / "Slow Horses (2022)" / "Season 02" / "Slow Horses - S02E06.mkv"
    )


def test_small_files_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "sample.mkv").write_bytes(b"tiny")
    assert scan_library(tmp_path, FakeProvider()).items == ()


def test_unmatched_file_becomes_skip(tmp_path: Path) -> None:
    _big(tmp_path / "Totally.Unknown.Thing.S01E01.1080p.mkv")
    plan = scan_library(tmp_path, FakeProvider())
    assert plan.moves == ()
    assert len(plan.skips) == 1


def test_provider_error_does_not_crash_scan(tmp_path: Path) -> None:
    class Boom:
        name = "boom"

        def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
            raise ProviderError("provider down")

        def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
            raise ProviderError("provider down")

    _big(tmp_path / "Show.S01E01.1080p.mkv")
    plan = scan_library(tmp_path, Boom())
    assert len(plan.skips) == 1
    assert "provider error" in plan.skips[0].reason


def test_limit_caps_processing(tmp_path: Path) -> None:
    _big(tmp_path / "A.Show.S01E01.1080p.mkv")
    _big(tmp_path / "B.Show.S01E01.1080p.mkv")
    plan = scan_library(tmp_path, FakeProvider(), limit=1)
    assert len(plan.items) == 1
