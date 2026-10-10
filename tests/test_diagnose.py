# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for read-only Jellyfin metadata diagnosis (offline via MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from kemptd.diagnose import JellyfinLibrary, diagnose_library
from kemptd.errors import ServerError
from kemptd.models import MovieCandidate, SeriesCandidate

_ITEMS = {
    "Items": [
        {
            "Id": "a1",
            "Name": "Mars",
            "Type": "Movie",
            "ProductionYear": 2016,
            "Path": "/media/Movies/Mars (2024)/Mars.2024.1080p.mkv",
            "ProviderIds": {"Tmdb": "111"},  # wrong film
        },
        {
            "Id": "b2",
            "Name": "Inception",
            "Type": "Movie",
            "ProductionYear": 2010,
            "Path": "/media/Movies/Inception (2010)/Inception.2010.1080p.mkv",
            "ProviderIds": {"Tmdb": "27205"},  # correct
        },
        {
            "Id": "c3",
            "Name": "One Piece",
            "Type": "Series",
            "ProductionYear": 1999,
            "Path": "/data/One Piece (1999)",
            "ProviderIds": {"Tvdb": "81797"},  # correct
        },
    ]
}


class FakeProvider:
    name = "fake"

    def search_movie(self, title: str, *, year: int | None = None) -> list[MovieCandidate]:
        return {
            "mars": [MovieCandidate("Mars", 2024, tmdb_id=999)],
            "inception": [MovieCandidate("Inception", 2010, tmdb_id=27205)],
        }.get(title.casefold(), [])

    def search_series(self, title: str, *, year: int | None = None) -> list[SeriesCandidate]:
        return {
            "one piece": [SeriesCandidate("One Piece", 1999, tvdb_id=81797)],
        }.get(title.casefold(), [])


def _library(handler: object) -> JellyfinLibrary:
    client = httpx.Client(base_url="http://jelly:8096", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return JellyfinLibrary("http://jelly:8096", "key", client=client)


def test_items_are_parsed_and_authorized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/Items"
        assert request.headers["Authorization"] == 'MediaBrowser Token="key"'
        assert request.url.params["IncludeItemTypes"] == "Movie,Series"
        return httpx.Response(200, json=_ITEMS)

    items = _library(handler).items()
    assert [i.name for i in items] == ["Mars", "Inception", "One Piece"]
    assert items[0].is_movie and not items[2].is_movie
    assert items[0].provider_ids == {"Tmdb": "111"}


def test_diagnose_flags_only_the_real_mismatch() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ITEMS)

    mismatches = diagnose_library(_library(handler), FakeProvider())

    assert len(mismatches) == 1
    bad = mismatches[0]
    assert bad.current_name == "Mars"
    assert bad.current_id == "tmdb:111"
    assert bad.proposed_title == "Mars"
    assert bad.proposed_year == 2024
    assert bad.proposed_id == "tmdb:999"


def test_unmatched_item_is_reported_with_proposal() -> None:
    items = {
        "Items": [
            {
                "Id": "x",
                "Name": "Inception",
                "Type": "Movie",
                "ProductionYear": 2010,
                "Path": "/media/Movies/Inception (2010)/Inception.2010.mkv",
                "ProviderIds": {},  # server never matched it
            }
        ]
    }
    mismatches = diagnose_library(
        _library(lambda _: httpx.Response(200, json=items)), FakeProvider()
    )
    assert len(mismatches) == 1
    assert mismatches[0].current_id is None
    assert mismatches[0].proposed_id == "tmdb:27205"


def test_limit_caps_items_checked() -> None:
    mismatches = diagnose_library(
        _library(lambda _: httpx.Response(200, json=_ITEMS)), FakeProvider(), limit=0
    )
    assert mismatches == []


def test_http_error_raises_server_error() -> None:
    with pytest.raises(ServerError, match="401"):
        _library(lambda _: httpx.Response(401)).items()


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ServerError, match="API key"):
        JellyfinLibrary("http://jelly:8096", "")
