# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the TVDB provider, driven offline with httpx.MockTransport."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from kemptd.errors import ProviderError
from kemptd.models import EpisodeNumber, SeriesCandidate
from kemptd.providers import AbsoluteResolver, MetadataProvider, TvdbProvider

_ONE_PIECE = SeriesCandidate("One Piece", 1999, tvdb_id=81797)


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> TvdbProvider:
    client = httpx.Client(
        base_url="https://api4.thetvdb.com/v4", transport=httpx.MockTransport(handler)
    )
    return TvdbProvider("test-key", client=client)


def _token(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"data": {"token": "tok"}})


def test_search_series_maps_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return _token(request)
        assert request.url.path.endswith("/search")
        assert request.url.params["query"] == "One Piece"
        assert request.url.params["type"] == "series"
        return httpx.Response(
            200, json={"data": [{"tvdb_id": "81797", "name": "One Piece", "year": "1999"}]}
        )

    assert _provider(handler).search_series("One Piece") == [_ONE_PIECE]


def test_login_happens_once_and_authorizes_requests() -> None:
    logins = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal logins
        if request.url.path.endswith("/login"):
            logins += 1
            return _token(request)
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"data": []})

    provider = _provider(handler)
    provider.search_series("One Piece")
    provider.search_series("Naruto")  # distinct query, but no second login
    assert logins == 1


def test_resolve_absolute_maps_to_aired_season_episode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return _token(request)
        assert request.url.path == "/v4/series/81797/episodes/default"
        return httpx.Response(
            200,
            json={
                "data": {
                    "episodes": [
                        {"absoluteNumber": 1, "seasonNumber": 1, "number": 1},
                        {"absoluteNumber": 61, "seasonNumber": 3, "number": 1},
                    ]
                },
                "links": {"next": None},
            },
        )

    provider = _provider(handler)
    assert provider.resolve_absolute(_ONE_PIECE, 61) == EpisodeNumber(3, 1)
    assert provider.resolve_absolute(_ONE_PIECE, 999) is None


def test_resolve_absolute_without_id_returns_none() -> None:
    # No HTTP should occur, so a handler that always 500s proves it short-circuits.
    provider = _provider(lambda _: httpx.Response(500))
    assert provider.resolve_absolute(SeriesCandidate("Mystery"), 5) is None


def test_episode_map_follows_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return _token(request)
        if request.url.params.get("page") == "0":
            return httpx.Response(
                200,
                json={
                    "data": {"episodes": [{"absoluteNumber": 1, "seasonNumber": 1, "number": 1}]},
                    "links": {
                        "next": "https://api4.thetvdb.com/v4/series/81797/episodes/default?page=1"
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {"episodes": [{"absoluteNumber": 61, "seasonNumber": 3, "number": 1}]},
                "links": {"next": None},
            },
        )

    provider = _provider(handler)
    assert provider.resolve_absolute(_ONE_PIECE, 61) == EpisodeNumber(3, 1)  # from page 2


def test_login_failure_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    with pytest.raises(ProviderError, match="login returned 401"):
        _provider(handler).search_series("Anything")


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ProviderError, match="API key"):
        TvdbProvider("")


def test_satisfies_provider_and_resolver_protocols() -> None:
    provider = _provider(_token)
    assert isinstance(provider, MetadataProvider)
    assert isinstance(provider, AbsoluteResolver)
