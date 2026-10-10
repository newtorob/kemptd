# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the filename parser, seeded from real-world messy names."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kemptd.models import MediaKind
from kemptd.parse import parse_filename


@pytest.mark.parametrize(
    ("name", "title", "year", "season", "episodes"),
    [
        (
            "www.UIndex.org    -    Fallout.2024.S02E01.1080p.HEVC.x265-MeGusta.mkv",
            "fallout",
            2024,
            2,
            (1,),
        ),
        ("BILLIONS - S01E01 - Pilot (1080p - BluRay).mp4", "billions", None, 1, (1,)),
        ("Peaky.Blinders.S03E04.1080p.BluRay.x264-GROUP.mkv", "peaky blinders", None, 3, (4,)),
        ("Slow.Horses.S02E06.1080p.ATVP.WEB-DL.DDP5.1-FLUX.mkv", "slow horses", None, 2, (6,)),
        ("Show.Name.S01E01E02.720p.mkv", "show name", None, 1, (1, 2)),
    ],
)
def test_parse_episodes(
    name: str,
    title: str,
    year: int | None,
    season: int | None,
    episodes: tuple[int, ...],
) -> None:
    pm = parse_filename(name)
    assert pm.kind is MediaKind.EPISODE
    assert pm.title is not None and pm.title.lower() == title
    assert pm.year == year
    assert pm.season == season
    assert pm.episodes == episodes


def test_parse_movie() -> None:
    pm = parse_filename("The.Odyssey.2026.1080p.WEBRip.mkv")
    assert pm.kind is MediaKind.MOVIE
    assert pm.title is not None and pm.title.lower() == "the odyssey"
    assert pm.year == 2026
    assert pm.season is None
    assert pm.episodes == ()


def test_absolute_numbered_anime_is_flagged() -> None:
    pm = parse_filename("Black Clover 091 (1080p)(HEVC x265 10bit).mkv")
    assert pm.title is not None and pm.title.lower() == "black clover"
    assert pm.season is None
    assert pm.is_absolute_numbered
    assert pm.absolute_episodes == (91,)
    assert pm.episodes == ()


def test_multi_episode_flag() -> None:
    pm = parse_filename("Show.Name.S01E01E02.720p.mkv")
    assert pm.is_multi_episode
    assert not pm.is_absolute_numbered


@given(st.text())
def test_parse_never_raises(name: str) -> None:
    """The parser must tolerate arbitrary input without throwing."""
    pm = parse_filename(name)
    assert pm.title is None or isinstance(pm.title, str)
    assert isinstance(pm.episodes, tuple)
    assert pm.raw == name
