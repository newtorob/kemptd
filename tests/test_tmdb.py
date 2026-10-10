# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the TMDb provider, driven offline with httpx.MockTransport."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from kemptd.errors import ProviderError
from kemptd.models import MovieCandidate, SeriesCandidate
from kemptd.providers import MetadataProvider, TmdbProvider


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> TmdbProvider:
    client = httpx.Client(
        base_url="https://api.themoviedb.org/3", transport=httpx.MockTransport(handler)
    )
    return TmdbProvider("test-key", client=client)


def test_search_series_maps_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search/tv")
        assert request.url.params["query"] == "Slow Horses"
        assert request.url.params["api_key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "results": [{"id": 95480, "name": "Slow Horses", "first_air_date": "2022-04-01"}]
            },
        )

    assert _provider(handler).search_series("Slow Horses") == [
        SeriesCandidate("Slow Horses", 2022, tmdb_id=95480)
    ]


def test_search_movie_maps_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search/movie")
        assert request.url.params["primary_release_year"] == "2010"
        return httpx.Response(
            200,
            json={"results": [{"id": 27205, "title": "Inception", "release_date": "2010-07-16"}]},
        )

    assert _provider(handler).search_movie("Inception", year=2010) == [
        MovieCandidate("Inception", 2010, tmdb_id=27205)
    ]


def test_results_are_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"results": [{"id": 1, "name": "X", "first_air_date": "2020"}]}
        )

    provider = _provider(handler)
    provider.search_series("X")
    provider.search_series("X")  # same query → served from cache
    assert calls == 1


def test_missing_date_yields_none_year() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"id": 7, "name": "Pilot Era"}]})

    assert _provider(handler).search_series("Pilot Era")[0].year is None


def test_http_error_raises_provider_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "invalid key"})

    with pytest.raises(ProviderError, match="401"):
        _provider(handler).search_series("Anything")


def test_transport_failure_raises_provider_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(ProviderError, match="request failed"):
        _provider(handler).search_movie("Anything")


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ProviderError, match="API key"):
        TmdbProvider("")


def test_satisfies_provider_protocol() -> None:
    provider = _provider(lambda _: httpx.Response(200, json={"results": []}))
    assert isinstance(provider, MetadataProvider)
