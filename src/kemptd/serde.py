# SPDX-License-Identifier: GPL-3.0-or-later
"""(De)serialization for plans, so `scan` and `apply` can be separate steps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Confidence
from .plan import Plan, PlanAction, PlanItem

__all__ = ["FORMAT_VERSION", "dump_plan", "load_plan"]

FORMAT_VERSION = 1


def _item_to_dict(item: PlanItem) -> dict[str, Any]:
    return {
        "source": str(item.source),
        "destination": str(item.destination) if item.destination is not None else None,
        "action": item.action.value,
        "confidence": item.confidence.value,
        "reason": item.reason,
    }


def _item_from_dict(data: dict[str, Any]) -> PlanItem:
    destination = data["destination"]
    return PlanItem(
        source=Path(data["source"]),
        destination=Path(destination) if destination is not None else None,
        action=PlanAction(data["action"]),
        confidence=Confidence(data["confidence"]),
        reason=data["reason"],
    )


def dump_plan(plan: Plan, path: Path) -> None:
    """Write *plan* to *path* as JSON."""
    payload = {"version": FORMAT_VERSION, "items": [_item_to_dict(i) for i in plan.items]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_plan(path: Path) -> Plan:
    """Read a plan previously written by :func:`dump_plan`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported plan format version: {version!r}")
    return Plan(tuple(_item_from_dict(i) for i in payload["items"]))
