# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan execution.

Applies a :class:`~kemptd.plan.Plan` with safety as the top priority:

* same-filesystem moves are atomic renames;
* cross-filesystem moves copy to a temp file, verify size, atomically swap, then
  unlink the source (copy-verify-swap) — the destination is never a half-file;
* existing destinations are skipped, never overwritten;
* every completed move is recorded to a JSON journal so :func:`undo` can reverse
  the operation. Nothing is ever deleted outright.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import KemptdError
from .nfo import nfo_targets
from .plan import Plan, PlanAction

__all__ = ["ApplyError", "ApplyReport", "apply_plan", "undo"]


class ApplyError(KemptdError):
    """A move could not be completed safely."""


@dataclass(slots=True)
class ApplyReport:
    moved: int = 0
    skipped: int = 0
    failed: int = 0
    journal_path: Path | None = None


def _nearest_existing_device(path: Path) -> int:
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            return ancestor.stat().st_dev
    raise ApplyError(f"no existing ancestor for {path}")


def _move(source: Path, destination: Path) -> None:
    """Move *source* to *destination* atomically, across filesystems if needed."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.stat().st_dev == _nearest_existing_device(destination.parent):
        source.replace(destination)  # atomic, same filesystem
        return

    partial = destination.with_name(destination.name + ".kemptd-partial")
    try:
        shutil.copy2(source, partial)
        if partial.stat().st_size != source.stat().st_size:
            raise ApplyError(f"size mismatch copying {source} -> {destination}")
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    source.unlink()


def apply_plan(
    plan: Plan, *, journal_path: Path, dry_run: bool = False, write_nfo: bool = False
) -> ApplyReport:
    """Execute *plan*. With ``dry_run`` nothing is touched and no journal is written.

    With ``write_nfo``, each applied move also drops a ``.nfo`` sidecar (carrying
    the provider id) so Plex/Jellyfin/Kodi match it deterministically. Sidecars
    are created only when absent and are recorded in the journal, so ``undo``
    removes exactly what this run wrote.
    """
    report = ApplyReport(journal_path=None if dry_run else journal_path)
    journal: list[dict[str, str]] = []

    for item in plan.items:
        if item.action is PlanAction.SKIP or item.destination is None:
            report.skipped += 1
            continue
        if item.destination.exists():
            report.skipped += 1  # never overwrite
            continue
        if dry_run:
            report.moved += 1
            continue
        try:
            _move(item.source, item.destination)
        except (OSError, ApplyError):
            report.failed += 1
            continue
        journal.append({"source": str(item.source), "destination": str(item.destination)})
        report.moved += 1

        if write_nfo and item.meta is not None:
            for nfo_path, xml in nfo_targets(item.destination, item.meta):
                if nfo_path.exists():
                    continue
                nfo_path.parent.mkdir(parents=True, exist_ok=True)
                nfo_path.write_text(xml, encoding="utf-8")
                journal.append({"nfo": str(nfo_path)})

    if not dry_run and journal:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")

    return report


def undo(journal_path: Path) -> int:
    """Reverse a journal; return the count of files restored.

    Sidecars written during the apply (``nfo`` entries) are removed first, then
    moves are reversed in LIFO order. Only files this run created/moved are
    touched — nothing pre-existing is disturbed.
    """
    entries = json.loads(journal_path.read_text(encoding="utf-8"))
    restored = 0
    for entry in reversed(entries):
        if "nfo" in entry:
            Path(entry["nfo"]).unlink(missing_ok=True)
            continue
        original, moved = Path(entry["source"]), Path(entry["destination"])
        if moved.exists() and not original.exists():
            _move(moved, original)
            restored += 1
    return restored
