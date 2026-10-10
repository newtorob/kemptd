# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plan execution and undo (against real temp directories)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import kemptd.apply as apply_module
from kemptd.apply import apply_plan, undo
from kemptd.models import Confidence
from kemptd.plan import Plan, PlanAction, PlanItem


def _move(source: Path, destination: Path) -> PlanItem:
    return PlanItem(source, destination, PlanAction.MOVE, Confidence.HIGH, "rationale")


def test_apply_moves_file_and_writes_journal(tmp_path: Path) -> None:
    src = tmp_path / "in" / "ep.mkv"
    src.parent.mkdir()
    src.write_bytes(b"payload")
    dst = tmp_path / "lib" / "Show (2022)" / "Season 01" / "Show - S01E01.mkv"
    journal = tmp_path / "j.json"

    report = apply_plan(Plan((_move(src, dst),)), journal_path=journal)

    assert report.moved == 1
    assert dst.read_bytes() == b"payload"
    assert not src.exists()
    assert json.loads(journal.read_text())[0]["destination"] == str(dst)


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    src = tmp_path / "ep.mkv"
    src.write_bytes(b"new")
    dst = tmp_path / "lib" / "ep.mkv"
    dst.parent.mkdir()
    dst.write_bytes(b"existing")

    report = apply_plan(Plan((_move(src, dst),)), journal_path=tmp_path / "j.json")

    assert report.skipped == 1
    assert report.moved == 0
    assert dst.read_bytes() == b"existing"
    assert src.exists()


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "ep.mkv"
    src.write_bytes(b"x")
    dst = tmp_path / "lib" / "ep.mkv"

    report = apply_plan(Plan((_move(src, dst),)), journal_path=tmp_path / "j.json", dry_run=True)

    assert report.moved == 1
    assert report.journal_path is None
    assert src.exists() and not dst.exists()
    assert not (tmp_path / "j.json").exists()


def test_undo_restores_originals(tmp_path: Path) -> None:
    src = tmp_path / "in" / "ep.mkv"
    src.parent.mkdir()
    src.write_bytes(b"payload")
    dst = tmp_path / "lib" / "ep.mkv"
    journal = tmp_path / "j.json"
    apply_plan(Plan((_move(src, dst),)), journal_path=journal)
    assert dst.exists() and not src.exists()

    restored = undo(journal)

    assert restored == 1
    assert src.read_bytes() == b"payload"
    assert not dst.exists()


def test_cross_filesystem_copy_verify_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "in" / "ep.mkv"
    src.parent.mkdir()
    src.write_bytes(b"payload")
    dst = tmp_path / "lib" / "ep.mkv"
    # Force the cross-filesystem branch by reporting a mismatched device.
    monkeypatch.setattr(apply_module, "_nearest_existing_device", lambda _p: -1)

    report = apply_plan(Plan((_move(src, dst),)), journal_path=tmp_path / "j.json")

    assert report.moved == 1
    assert dst.read_bytes() == b"payload"
    assert not src.exists()
    assert not dst.with_name(dst.name + ".kemptd-partial").exists()


def test_skip_item_is_not_moved(tmp_path: Path) -> None:
    item = PlanItem(tmp_path / "a.mkv", None, PlanAction.SKIP, Confidence.LOW, "nope")
    report = apply_plan(Plan((item,)), journal_path=tmp_path / "j.json")
    assert report.skipped == 1
    assert report.moved == 0
