# SPDX-License-Identifier: GPL-3.0-or-later
"""kemptd — tidy, provider-backed media library organizer."""

from __future__ import annotations

__version__ = "0.1.0"

from .models import (
    Candidate,
    Confidence,
    MatchResult,
    MediaKind,
    MovieCandidate,
    ParsedMedia,
    SeriesCandidate,
)

__all__ = [
    "Candidate",
    "Confidence",
    "MatchResult",
    "MediaKind",
    "MovieCandidate",
    "ParsedMedia",
    "SeriesCandidate",
    "__version__",
]
