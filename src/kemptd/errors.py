# SPDX-License-Identifier: GPL-3.0-or-later
"""Exception hierarchy for kemptd."""

from __future__ import annotations

__all__ = ["ConfigError", "KemptdError", "ProviderError", "ServerError"]


class KemptdError(Exception):
    """Base class for all kemptd errors."""


class ProviderError(KemptdError):
    """A metadata provider failed to return a usable response."""


class ConfigError(KemptdError):
    """Configuration is missing or invalid."""


class ServerError(KemptdError):
    """A media server (Plex/Jellyfin) failed to return a usable response."""
