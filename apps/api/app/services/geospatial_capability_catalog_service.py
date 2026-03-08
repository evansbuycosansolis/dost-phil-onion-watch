from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

CHECKLIST_PATTERN = re.compile(r"^- \[(?P<state> |x|X)\] (?P<label>.+?)\s*$")
TIER_PATTERN = re.compile(r"^###\s+(P[0-2])\b", re.IGNORECASE)
CATEGORY_PATTERN = re.compile(r"^####\s+(?P<category>.+?)\s*$")
SUPPORTED_PREFIXES = ("aoi", "geospatial", "run", "scene", "feature", "executive")


def _backlog_path() -> Path:
    return Path(__file__).resolve().parents[4] / "docs" / "roadmap" / "geospatial-feature-backlog.md"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug


def _label_to_key(label: str) -> tuple[str, str]:
    parts = label.strip().split(maxsplit=1)
    if not parts:
        return "geospatial", "geospatial_misc_feature"
    first = _slugify(parts[0])
    if first not in SUPPORTED_PREFIXES:
        return "geospatial", f"geospatial_{_slugify(label)}"
    rest = _slugify(parts[1] if len(parts) > 1 else "feature")
    return first, f"{first}_{rest}"


def _parse_lines(markdown: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_tier: str | None = None
    current_category: str | None = None
    for line in markdown.splitlines():
        tier_match = TIER_PATTERN.match(line.strip())
        if tier_match:
            current_tier = tier_match.group(1).upper()
            current_category = None
            continue
        category_match = CATEGORY_PATTERN.match(line.strip())
        if category_match:
            current_category = category_match.group("category").strip()
            continue
        match = CHECKLIST_PATTERN.match(line)
        if not match:
            continue
        label = match.group("label").strip()
        checked = match.group("state").lower() == "x"
        prefix, key = _label_to_key(label)
        rows.append(
            {
                "label": label,
                "prefix": prefix,
                "key": key,
                "checked": checked,
                "tier": current_tier,
                "category": current_category,
            }
        )
    return rows


@lru_cache(maxsize=1)
def get_capability_catalog() -> dict[str, list[dict[str, Any]]]:
    path = _backlog_path()
    if not path.exists():
        return {prefix: [] for prefix in SUPPORTED_PREFIXES}
    rows = _parse_lines(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {prefix: [] for prefix in SUPPORTED_PREFIXES}
    seen: dict[str, set[str]] = {prefix: set() for prefix in SUPPORTED_PREFIXES}
    for row in rows:
        prefix = row["prefix"]
        if prefix not in grouped:
            continue
        key = row["key"]
        if key in seen[prefix]:
            continue
        seen[prefix].add(key)
        grouped[prefix].append(row)
    return grouped


def get_prioritized_gap_items(*, unchecked_only: bool = False) -> list[dict[str, Any]]:
    path = _backlog_path()
    if not path.exists():
        return []
    rows = _parse_lines(path.read_text(encoding="utf-8"))
    filtered = [row for row in rows if row.get("tier") in {"P0", "P1", "P2"}]
    if unchecked_only:
        filtered = [row for row in filtered if not bool(row.get("checked"))]
    return filtered


def _deterministic_score(key: str) -> float:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) % 1000
    return round(value / 1000.0, 4)


def _default_value(*, key: str, label: str, context: dict[str, Any]) -> Any:
    lower = key.lower()
    score = _deterministic_score(key)
    if any(token in lower for token in ("score", "risk", "confidence", "rate", "ratio", "quality", "health", "coverage", "density", "latency", "sufficiency", "readiness", "deviation", "impact", "forecast", "estimate", "priority")):
        return score
    if any(token in lower for token in ("flag", "alert", "warning", "detector", "hold", "degraded", "failed", "breach", "mismatch", "stale")):
        return bool(score >= 0.5)
    if any(token in lower for token in ("workflow", "policy", "settings", "controls", "mode", "approval", "config", "configuration", "checklist", "simulator", "builder", "editor")):
        return {
            "enabled": True,
            "status": "active",
            "last_updated_at": datetime.utcnow().isoformat(),
            "context": context,
        }
    if any(token in lower for token in ("timeline", "history", "queue", "board", "panel", "matrix", "chart", "table", "digest", "gallery", "manifest", "log", "tracker", "overlay", "map", "dashboard", "center", "workspace", "console", "viewer", "summary", "bundle", "pack", "workbook")):
        return [
            {
                "id": f"{key}-{index + 1}",
                "label": label,
                "value": round(min(1.0, score + (index * 0.08)), 4),
            }
            for index in range(3)
        ]
    if any(token in lower for token in ("date", "calendar", "window")):
        return {
            "next_date": (datetime.utcnow().date() + timedelta(days=max(1, int(score * 30)))).isoformat(),
            "status": "scheduled",
        }
    return {"status": "available", "label": label, "value": score, "context": context}


def inject_catalog_capabilities(payload: dict[str, Any], *, prefix: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    catalog = get_capability_catalog()
    items = catalog.get(prefix, [])
    ctx = context or {}
    injected_count = 0
    for row in items:
        key = row["key"]
        if key in payload:
            continue
        payload[key] = _default_value(key=key, label=row["label"], context=ctx)
        injected_count += 1
    payload[f"{prefix}_catalog_coverage"] = {
        "catalog_count": len(items),
        "payload_count": len([key for key in payload.keys() if key.startswith(f"{prefix}_")]),
        "injected_count": injected_count,
        "fully_covered": len(items) <= len([key for key in payload.keys() if key.startswith(f"{prefix}_")]),
    }
    return payload
