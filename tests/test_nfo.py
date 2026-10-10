# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for NFO sidecar generation (pure; no filesystem access)."""

from __future__ import annotations

from pathlib import Path

from kemptd.models import MediaMeta
from kemptd.nfo import movie_nfo_xml, nfo_targets, series_nfo_xml


def test_series_nfo_has_title_year_and_default_uniqueid() -> None:
    xml = series_nfo_xml(MediaMeta(True, "Slow Horses", 2022, tmdb_id=95480))
    assert "<tvshow>" in xml
    assert "<title>Slow Horses</title>" in xml
    assert "<year>2022</year>" in xml
    assert '<uniqueid type="tmdb" default="true">95480</uniqueid>' in xml


def test_movie_nfo_uses_movie_root() -> None:
    xml = movie_nfo_xml(MediaMeta(False, "Inception", 2010, tmdb_id=27205))
    assert xml.startswith('<?xml version="1.0"')
    assert "<movie>" in xml
    assert '<uniqueid type="tmdb" default="true">27205</uniqueid>' in xml


def test_only_tvdb_id_is_still_marked_default() -> None:
    xml = series_nfo_xml(MediaMeta(True, "Show", 2001, tvdb_id=123))
    assert '<uniqueid type="tvdb" default="true">123</uniqueid>' in xml
    assert "tmdb" not in xml


def test_title_is_xml_escaped() -> None:
    xml = movie_nfo_xml(MediaMeta(False, "Tom & Jerry", 2021, tmdb_id=1))
    assert "<title>Tom &amp; Jerry</title>" in xml


def test_missing_year_is_omitted() -> None:
    xml = series_nfo_xml(MediaMeta(True, "Pilot", None, tmdb_id=1))
    assert "<year>" not in xml


def test_episode_target_is_tvshow_nfo_at_show_root() -> None:
    dest = Path("/lib/Slow Horses (2022)/Season 02/Slow Horses - S02E06.mkv")
    targets = nfo_targets(dest, MediaMeta(True, "Slow Horses", 2022, tmdb_id=95480))
    assert [p for p, _ in targets] == [Path("/lib/Slow Horses (2022)/tvshow.nfo")]


def test_movie_target_sits_next_to_the_file() -> None:
    dest = Path("/lib/Inception (2010)/Inception (2010).mkv")
    targets = nfo_targets(dest, MediaMeta(False, "Inception", 2010, tmdb_id=27205))
    assert [p for p, _ in targets] == [Path("/lib/Inception (2010)/Inception (2010).nfo")]
