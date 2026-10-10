# SPDX-License-Identifier: GPL-3.0-or-later
"""(De)serialization for plans, so `scan` and `apply` can be separate steps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Confidence, MediaMeta
from .plan import Plan, PlanAction, PlanItem

__all__ = ["FORMAT_VERSION", "dump_plan", "load_plan"]

FORMAT_VERSION = 1


def _meta_to_dict(meta: MediaMeta) -> dict[str, Any]:
    return {
        "is_series": meta.is_series,
        "title": meta.title,
        "year": meta.year,
        "tmdb_id": meta.tmdb_id,
        "tvdb_id": meta.tvdb_id,
    }


def _meta_from_dict(data: dict[str, Any]) -> MediaMeta:
    return MediaMeta(
        is_series=data["is_series"],
        title=data["title"],
        year=data.get("year"),
        tmdb_id=data.get("tmdb_id"),
        tvdb_id=data.get("tvdb_id"),
    )


def _item_to_dict(item: PlanItem) -> dict[str, Any]:
    return {
        "source": str(item.source),
        "destination": str(item.destination) if item.destination is not None else None,
        "action": item.action.value,
        "confidence": item.confidence.value,
        "reason": item.reason,
        "meta": _meta_to_dict(item.meta) if item.meta is not None else None,
    }


def _item_from_dict(data: dict[str, Any]) -> PlanItem:
    destination = data["destination"]
    meta = data.get("meta")
    return PlanItem(
        source=Path(data["source"]),
        destination=Path(destination) if destination is not None else None,
        action=PlanAction(data["action"]),
        confidence=Confidence(data["confidence"]),
        reason=data["reason"],
        meta=_meta_from_dict(meta) if meta is not None else None,
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
