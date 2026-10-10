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

# Release-name cleanup: guessit sometimes truncates titles (drops "Part III",
# a trailing "Us", …), which makes a shorter wrong candidate score a perfect
# match. Recovering the fuller "pre-boundary" title from the raw name fixes that.
_SITE_PREFIX = re.compile(r"^\s*www[\s.]\S*?\s*-\s*", re.IGNORECASE)
_TITLE_BOUNDARY = re.compile(
    r"\b(s\d{1,2}e\d{1,3}|s\d{1,2}|season\s*\d+|19\d{2}|20\d{2}|1080p|720p|2160p|480p|4k"
    r"|web[\s.-]?rip|web[\s.-]?dl|blu[\s.-]?ray|br[\s.-]?rip|hdtv|dvdrip|x264|x265|h\s?26[45]"
    r"|hevc|aac|ddp?5|10bit|unrated|internal|repack|proper|remux|complete)\b",
    re.IGNORECASE,
)


def _full_title(raw: str) -> str:
    """Recover a fuller title from a raw release name than guessit may expose.

    Strips a scene-site prefix, folds separators, and cuts at the first release
    marker (season/episode, year, quality, codec). Best-effort: returns "" when
    nothing usable remains.
    """
    stem = raw.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = _SITE_PREFIX.sub("", stem).replace(".", " ").replace("_", " ")
    boundary = _TITLE_BOUNDARY.search(stem)
    if boundary:
        stem = stem[: boundary.start()]
    stem = re.sub(r"[\s\-(\[]+$", "", stem)
    return stem.strip()


def _scoring_title(parsed: ParsedMedia) -> str:
    """Choose the title to score with.

    Prefer the recovered full title *only* when it's a clean extension of
    guessit's title (same prefix, extra trailing words) — the "dropped word"
    case (Hostel → Hostel: Part III). When the raw name is junkier than
    guessit's title (scene prefixes, anime ``[group]`` tags), keep guessit's.
    """
    title = parsed.title or ""
    full = _full_title(parsed.raw)
    if not title:
        return full
    normalized, normalized_full = _normalize(title), _normalize(full)
    if normalized and normalized_full.startswith(normalized + " "):
        return full
    return title


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
    title = _scoring_title(parsed)
    if not title:
        return 0.0

    base = title_similarity(title, candidate.title)

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
