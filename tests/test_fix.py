# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for applying Jellyfin metadata fixes (NFO write + refresh)."""

from __future__ import annotations

import json
from pathlib import Path

from kemptd.apply import undo
from kemptd.diagnose import Mismatch
from kemptd.errors import ServerError
from kemptd.fix import apply_fixes, nfo_path_for
from kemptd.models import Confidence


class FakeLibrary:
    def __init__(self) -> None:
        self.refreshed: list[str] = []

    def refresh_item(self, item_id: str) -> None:
        self.refreshed.append(item_id)


class BrokenLibrary:
    def refresh_item(self, item_id: str) -> None:
        raise ServerError("server down")


def _mm(item_id: str, path: str, is_movie: bool, proposed_id: str, **kw: object) -> Mismatch:
    return Mismatch(
        item_id=item_id,
        path=path,
        is_movie=is_movie,
        current_name=str(kw.get("current_name", "old")),
        current_year=None,
        current_id=kw.get("current_id"),  # type: ignore[arg-type]
        proposed_title=str(kw.get("title", "Title")),
        proposed_year=kw.get("year", 2020),  # type: ignore[arg-type]
        proposed_id=proposed_id,
        confidence=Confidence.HIGH,
        rationale="r",
    )


def test_nfo_path_for_movie_and_series(tmp_path: Path) -> None:
    movie = _mm("1", str(tmp_path / "Film (2020)" / "Film.2020.mkv"), True, "tmdb:5")
    assert nfo_path_for(movie) == tmp_path / "Film (2020)" / "Film.2020.nfo"
    series = _mm("2", str(tmp_path / "Show (2020)"), False, "tmdb:9")
    assert nfo_path_for(series) == tmp_path / "Show (2020)" / "tvshow.nfo"


def test_apply_writes_series_nfo_and_refreshes(tmp_path: Path) -> None:
    folder = tmp_path / "Show (1999)"
    folder.mkdir()
    m = _mm("abc", str(folder), False, "tvdb:81797", title="One Piece", year=1999)
    lib = FakeLibrary()

    report = apply_fixes(lib, [m], journal_path=tmp_path / "j.json")  # type: ignore[arg-type]

    assert report.written == 1 and report.refreshed == 1
    assert lib.refreshed == ["abc"]
    nfo = (folder / "tvshow.nfo").read_text()
    assert '<uniqueid type="tvdb" default="true">81797</uniqueid>' in nfo
    assert json.loads((tmp_path / "j.json").read_text())[0]["nfo"].endswith("tvshow.nfo")


def test_apply_writes_movie_nfo_beside_file(tmp_path: Path) -> None:
    folder = tmp_path / "Film (2010)"
    folder.mkdir()
    (folder / "Film.2010.mkv").write_bytes(b"x")
    m = _mm("m", str(folder / "Film.2010.mkv"), True, "tmdb:27205", title="Inception", year=2010)

    apply_fixes(FakeLibrary(), [m], journal_path=tmp_path / "j.json")  # type: ignore[arg-type]

    assert "<movie>" in (folder / "Film.2010.nfo").read_text()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    folder = tmp_path / "Show (2020)"
    folder.mkdir()
    lib = FakeLibrary()
    m = _mm("x", str(folder), False, "tmdb:1")

    report = apply_fixes(lib, [m], journal_path=tmp_path / "j.json", dry_run=True)  # type: ignore[arg-type]

    assert report.written == 1 and report.refreshed == 0
    assert not (folder / "tvshow.nfo").exists()
    assert lib.refreshed == []


def test_existing_nfo_is_not_clobbered(tmp_path: Path) -> None:
    folder = tmp_path / "Show (2020)"
    folder.mkdir()
    (folder / "tvshow.nfo").write_text("keep me")
    m = _mm("x", str(folder), False, "tmdb:1")

    report = apply_fixes(FakeLibrary(), [m], journal_path=tmp_path / "j.json")  # type: ignore[arg-type]

    assert report.skipped == 1 and report.written == 0
    assert (folder / "tvshow.nfo").read_text() == "keep me"


def test_refresh_failure_still_writes_sidecar(tmp_path: Path) -> None:
    folder = tmp_path / "Show (2020)"
    folder.mkdir()
    m = _mm("x", str(folder), False, "tmdb:1")

    report = apply_fixes(BrokenLibrary(), [m], journal_path=tmp_path / "j.json")  # type: ignore[arg-type]

    assert report.written == 1 and report.refreshed == 0
    assert (folder / "tvshow.nfo").exists()


def test_fix_journal_is_undoable(tmp_path: Path) -> None:
    folder = tmp_path / "Show (2020)"
    folder.mkdir()
    m = _mm("x", str(folder), False, "tmdb:1")
    journal = tmp_path / "j.json"
    apply_fixes(FakeLibrary(), [m], journal_path=journal)  # type: ignore[arg-type]
    assert (folder / "tvshow.nfo").exists()

    undo(journal)

    assert not (folder / "tvshow.nfo").exists()
