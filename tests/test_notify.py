# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for media-server rescan notifiers, driven offline with MockTransport."""

from __future__ import annotations

import httpx
import pytest

from kemptd.config import Settings
from kemptd.errors import ConfigError
from kemptd.notify import (
    JellyfinNotifier,
    NotifyError,
    PlexNotifier,
    ServerNotifier,
    build_notifiers,
)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_plex_refresh_hits_sections_all_with_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["token"] = request.url.params["X-Plex-Token"]
        return httpx.Response(200)

    PlexNotifier("http://server", "tok123", client=_client(handler)).refresh()
    assert seen == {"path": "/library/sections/all/refresh", "token": "tok123"}


def test_jellyfin_refresh_posts_with_auth_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(204)

    JellyfinNotifier("http://server", "key456", client=_client(handler)).refresh()
    assert seen["method"] == "POST"
    assert seen["path"] == "/Library/Refresh"
    assert seen["auth"] == 'MediaBrowser Token="key456"'


def test_http_error_becomes_notify_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(NotifyError, match="Plex refresh failed"):
        PlexNotifier("http://server", "t", client=_client(handler)).refresh()


def test_build_notifiers_constructs_requested_servers() -> None:
    settings = Settings(
        plex_url="http://p",
        plex_token="pt",
        jellyfin_url="http://j",
        jellyfin_api_key="jk",
    )
    notifiers = build_notifiers(["plex", "jellyfin"], settings)
    assert [n.name for n in notifiers] == ["plex", "jellyfin"]
    assert all(isinstance(n, ServerNotifier) for n in notifiers)


def test_build_notifiers_rejects_missing_config() -> None:
    with pytest.raises(ConfigError, match="KEMPTD_PLEX_URL"):
        build_notifiers(["plex"], Settings())


def test_build_notifiers_rejects_unknown_target() -> None:
    with pytest.raises(ConfigError, match="unknown rescan target"):
        build_notifiers(["kodi"], Settings())
