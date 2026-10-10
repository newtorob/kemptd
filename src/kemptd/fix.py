# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply metadata corrections to a Jellyfin library.

For each diagnosed :class:`~kemptd.diagnose.Mismatch`, write an ``.nfo`` carrying
the correct provider id next to the item and ask Jellyfin to re-identify it. The
written sidecars are journaled in the same format as :mod:`kemptd.apply`, so
``kemptd undo`` reverses a fix run. Nothing existing is overwritten.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .diagnose import JellyfinLibrary, Mismatch
from .errors import ServerError
from .models import MediaMeta
from .nfo import movie_nfo_xml, series_nfo_xml

__all__ = ["FixReport", "apply_fixes", "nfo_path_for"]


@dataclass(slots=True)
class FixReport:
    written: int = 0
    refreshed: int = 0
    skipped: int = 0
    failed: int = 0
    journal_path: Path | None = None


def _meta(mismatch: Mismatch) -> MediaMeta:
    key, _, raw = mismatch.proposed_id.partition(":")
    value = int(raw) if raw.isdigit() else None
    return MediaMeta(
        is_series=not mismatch.is_movie,
        title=mismatch.proposed_title,
        year=mismatch.proposed_year,
        tmdb_id=value if key == "tmdb" else None,
        tvdb_id=value if key == "tvdb" else None,
    )


def nfo_path_for(mismatch: Mismatch) -> Path:
    """Where the sidecar goes: beside a movie file, or ``tvshow.nfo`` in a series dir."""
    path = Path(mismatch.path)
    return path.with_suffix(".nfo") if mismatch.is_movie else path / "tvshow.nfo"


def _nfo_xml(mismatch: Mismatch) -> str:
    meta = _meta(mismatch)
    return movie_nfo_xml(meta) if mismatch.is_movie else series_nfo_xml(meta)


def apply_fixes(
    library: JellyfinLibrary,
    mismatches: list[Mismatch],
    *,
    journal_path: Path,
    dry_run: bool = False,
) -> FixReport:
    """Write correct-id sidecars and refresh each item. Dry-run writes nothing."""
    report = FixReport(journal_path=None if dry_run else journal_path)
    journal: list[dict[str, str]] = []

    for mismatch in mismatches:
        nfo = nfo_path_for(mismatch)
        if nfo.exists():
            report.skipped += 1  # never clobber an existing sidecar
            continue
        if dry_run:
            report.written += 1
            continue
        try:
            nfo.parent.mkdir(parents=True, exist_ok=True)
            nfo.write_text(_nfo_xml(mismatch), encoding="utf-8")
        except OSError:
            report.failed += 1
            continue
        journal.append({"nfo": str(nfo)})
        report.written += 1
        try:
            library.refresh_item(mismatch.item_id)
            report.refreshed += 1
        except ServerError:
            # The sidecar is written; a later library scan will still pick it up.
            pass

    if not dry_run and journal:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")

    return report
