# SPDX-License-Identifier: GPL-3.0-or-later
"""Scoring parsed media against provider candidates.

Pure and deterministic: given a :class:`~kemptd.models.ParsedMedia` and a list of
candidates (from any provider), pick the best one and assign a confidence tier.
Uses only the standard library so results are reproducible in tests.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import (
    Candidate,
    Confidence,
    MatchResult,
    MediaKind,
    MovieCandidate,
    ParsedMedia,
)

__all__ = ["best_match", "score_candidate", "title_similarity"]

# Tiers are intentionally conservative: only HIGH is auto-actionable. The gap
# between MEDIUM and LOW is where "correct but reworded" (e.g. a dropped "and")
# lands, so a human can rubber-stamp those without wrong matches sneaking in.
_HIGH = 0.92
_MEDIUM = 0.80
_LOW = 0.60

_YEAR_BONUS = 0.05
_YEAR_PENALTY = 0.15

_NOISE = re.compile(r"\b(tv series|complete|collection|the)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(title: str) -> str:
    """Lowercase, strip leading articles/noise words, and fold punctuation."""
    stripped = _NOISE.sub(" ", title.lower())
    return _NON_ALNUM.sub(" ", stripped).strip()


def _tokens(title: str) -> set[str]:
    return set(_normalize(title).split())


def title_similarity(a: str, b: str) -> float:
    """Return a 0.0 to 1.0 similarity blending sequence ratio and token overlap.

    The token Jaccard term rewards shared words regardless of order/noise, while
    the sequence ratio guards against token-bag collisions between unrelated
    titles that happen to share common words.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return 0.55 * seq + 0.45 * jaccard


def score_candidate(parsed: ParsedMedia, candidate: Candidate) -> float:
    """Score how well *candidate* matches *parsed*, in ``[0.0, 1.0]``."""
    if parsed.title is None:
        return 0.0

    base = title_similarity(parsed.title, candidate.title)

    if parsed.year is not None and candidate.year is not None:
        base += _YEAR_BONUS if parsed.year == candidate.year else -_YEAR_PENALTY

    return max(0.0, min(1.0, base))


def _classify(score: float) -> Confidence:
    if score >= _HIGH:
        return Confidence.HIGH
    if score >= _MEDIUM:
        return Confidence.MEDIUM
    if score >= _LOW:
        return Confidence.LOW
    return Confidence.NONE


def _wanted_type(parsed: ParsedMedia, candidate: Candidate) -> bool:
    """Candidates must agree with the parsed media kind."""
    if isinstance(candidate, MovieCandidate):
        return parsed.kind is not MediaKind.EPISODE
    return parsed.kind is not MediaKind.MOVIE  # SeriesCandidate


def best_match(parsed: ParsedMedia, candidates: list[Candidate]) -> MatchResult:
    """Choose the highest-scoring compatible candidate and classify confidence.

    Returns a :class:`MatchResult` with ``candidate=None`` and
    ``Confidence.NONE`` when nothing clears the floor.
    """
    eligible = [c for c in candidates if _wanted_type(parsed, c)]
    if not eligible:
        return MatchResult(parsed, None, 0.0, Confidence.NONE, "no compatible candidates")

    ranked = sorted(eligible, key=lambda c: score_candidate(parsed, c), reverse=True)
    best = ranked[0]
    score = score_candidate(parsed, best)
    confidence = _classify(score)

    if confidence is Confidence.NONE:
        return MatchResult(parsed, None, score, confidence, f"best score {score:.2f} below floor")

    runner_up = f" (next: {score_candidate(parsed, ranked[1]):.2f})" if len(ranked) > 1 else ""
    rationale = f"{parsed.title!r} ~ {best.title!r} @ {score:.2f}{runner_up}"
    return MatchResult(parsed, best, score, confidence, rationale)
