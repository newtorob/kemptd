# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Plex reader, driven offline with httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from kemptd.diagnose import LibraryReader, Mismatch, diagnose_library
from kemptd.errors import ServerError
from kemptd.models import Confidence, MovieCandidate, SeriesCandidate
from kemptd.plex import PlexServer, apply_plex_fixes

_SECTIONS = {
    "MediaContainer": {
        "Directory": [
            {"key": "5", "type": "movie", "title": "Movies"},
            {"key": "6", "type": "show", "title": "TV Shows"},
        ]
    }
}
_MOVIES = {
    "MediaContainer": {
        "Metadata": [
            {
                "ratingKey": "39552",
                "title": "Mars",
                "year": 2016,
                "type": "movie",
                "Guid": [{"id": "imdb://tt1"}, {"id": "tmdb://111"}],
                "Media": [{"Part": [{"file": "/media/Movies/Mars (2024)/Mars.2024.1080p.mkv"}]}],
            }
        ]
    }
}
_SHOWS = {
    "MediaContainer": {
        "Metadata": [
            {
                "ratingKey": "25052",
                "title": "One Piece",
                "year": 1999,
                "type": "show",
                "Guid": [{"id": "tvdb://81797"}],
                "Location": [{"path": "/media/TV/One Piece (1999)"}],
            }
        ]
    }
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    assert request.url.params["X-Plex-Token"] == "tok"
    assert request.headers["Accept"] == "application/json"
    if path == "/library/sections":
        return httpx.Response(200, json=_SECTIONS)
    if path == "/library/sections/5/all":
        return httpx.Response(200, json=_MOVIES)
    if path == "/library/sections/6/all":
        return httpx.Response(200, json=_SHOWS)
    return httpx.Response(404, json={})


def _server(handler: object = _handler) -> PlexServer:
    client = httpx.Client(base_url="http://plex:32400", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return PlexServer("http://plex:32400", "tok", client=client)


class FakeProvider:
    name = "fake"

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        return [MovieCandidate("Mars", 2024, tmdb_id=999)] if "mars" in title.casefold() else []

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        return (
            [SeriesCandidate("One Piece", 1999, tvdb_id=81797)]
            if "one piece" in title.casefold()
            else []
        )


def test_items_parse_guids_paths_and_types() -> None:
    items = _server().items()
    assert [(i.name, i.is_movie) for i in items] == [("Mars", True), ("One Piece", False)]
    movie, show = items
    assert movie.provider_ids == {"Imdb": "tt1", "Tmdb": "111"}
    assert movie.path == "/media/Movies/Mars (2024)/Mars.2024.1080p.mkv"
    assert show.provider_ids == {"Tvdb": "81797"}
    assert show.path == "/media/TV/One Piece (1999)"
    assert show.id == "25052"


def test_plex_satisfies_library_reader_protocol() -> None:
    assert isinstance(_server(), LibraryReader)


def test_diagnose_flags_plex_mismatch() -> None:
    # Plex has Mars as tmdb:111 (wrong 2016 film); filename says Mars.2024 -> tmdb:999.
    mismatches = diagnose_library(_server(), FakeProvider())
    assert len(mismatches) == 1
    assert mismatches[0].current_name == "Mars"
    assert mismatches[0].current_id == "tmdb:111"
    assert mismatches[0].proposed_id == "tmdb:999"
    assert mismatches[0].item_id == "39552"  # Plex ratingKey, for a future /match fix


def test_http_error_raises_server_error() -> None:
    with pytest.raises(ServerError, match="401"):
        _server(lambda _: httpx.Response(401)).items()


def test_empty_token_rejected() -> None:
    with pytest.raises(ServerError, match="token"):
        PlexServer("http://plex:32400", "")


_MATCHES = {
    "MediaContainer": {
        "SearchResult": [
            {"name": "Mars", "year": 2026, "guid": "plex://movie/aaa"},
            {"name": "Mars", "year": 2024, "guid": "plex://movie/bbb"},
            {"name": "Ado: MARS", "year": 2024, "guid": "plex://movie/ccc"},
        ]
    }
}


def _mars_mismatch() -> Mismatch:
    return Mismatch(
        item_id="43157",
        path="/x/Mars.2024.mkv",
        is_movie=True,
        current_name="Mars",
        current_year=2026,
        current_id="tmdb:916588",
        proposed_title='"MARS"',
        proposed_year=2024,
        proposed_id="tmdb:1545737",
        confidence=Confidence.HIGH,
        rationale="r",
    )


def test_apply_plex_fix_picks_exact_match_and_puts() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json=_MATCHES)
        if request.url.path.endswith("/match") and request.method == "PUT":
            seen["guid"] = request.url.params.get("guid")
            return httpx.Response(200, json={"MediaContainer": {}})
        return httpx.Response(404, json={})

    report = apply_plex_fixes(_server(handler), [_mars_mismatch()])
    assert report.applied == 1 and report.skipped == 0
    assert seen["guid"] == "plex://movie/bbb"  # the Mars 2024 = tmdb:1545737 one


def test_ambiguous_candidates_are_skipped() -> None:
    matches = {
        "MediaContainer": {
            "SearchResult": [
                {"name": "Mars", "year": 2024, "guid": "plex://movie/bbb"},
                {"name": "Mars", "year": 2024, "guid": "plex://movie/ddd"},
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json=matches)
        return httpx.Response(200, json={"MediaContainer": {}})

    report = apply_plex_fixes(_server(handler), [_mars_mismatch()])
    assert report.applied == 0 and report.skipped == 1


def test_dry_run_does_not_put() -> None:
    puts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json=_MATCHES)
        if request.method == "PUT":
            puts.append(1)
        return httpx.Response(200, json={"MediaContainer": {}})

    report = apply_plex_fixes(_server(handler), [_mars_mismatch()], dry_run=True)
    assert report.applied == 1 and puts == []
