# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for plan (de)serialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from kemptd.models import Confidence
from kemptd.plan import Plan, PlanAction, PlanItem
from kemptd.serde import dump_plan, load_plan


def test_plan_round_trips(tmp_path: Path) -> None:
    plan = Plan(
        (
            PlanItem(
                Path("/src/ep.mkv"),
                Path("/lib/Show (2022)/Season 01/Show - S01E01.mkv"),
                PlanAction.MOVE,
                Confidence.HIGH,
                "rationale",
            ),
            PlanItem(Path("/src/x.mkv"), None, PlanAction.SKIP, Confidence.LOW, "not actionable"),
        )
    )
    path = tmp_path / "plan.json"
    dump_plan(plan, path)
    assert load_plan(path) == plan


def test_unknown_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text('{"version": 99, "items": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_plan(path)
