"""OHLC refinement and output evidence helpers for Master Map lifecycle resolution."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def refine_break_time(core: Any, source_db: str | Path | None, raw: Any, event: Any, direction: str) -> str | None:
    if source_db is None or event.event_time is None:
        return None
    path = Path(source_db)
    if not path.exists():
        return None
    start = core.parse_time(event.event_time)
    duration = timeframe_duration(event_timeframe(core, event) or raw.timeframe)
    if start is None or duration is None:
        return None
    end = start + duration
    refinements = {
        "W1": ("D1", "H4", "H1"), "D1": ("H4", "H1"),
        "H4": ("H1",), "H1": ("M15",),
    }.get((event_timeframe(core, event) or raw.timeframe or "").upper(), ())
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candles'").fetchone() is None:
                return None
            for timeframe in refinements:
                rows = []
                for row in con.execute(
                    "SELECT time,high,low FROM candles WHERE symbol=? AND timeframe=?",
                    (raw.symbol, timeframe),
                ):
                    candle_time = parse_market_time(core, row["time"])
                    if candle_time is not None and start <= candle_time < end:
                        rows.append((candle_time, row))
                for candle_time, row in sorted(rows, key=lambda value: value[0]):
                    if direction == "DOWN" and raw.low is not None and float(row["low"]) < raw.low:
                        return candle_time.isoformat().replace("+00:00", "Z")
                    if direction == "UP" and raw.high is not None and float(row["high"]) > raw.high:
                        return candle_time.isoformat().replace("+00:00", "Z")
    except sqlite3.Error:
        return None
    return None


def event_timeframe(core: Any, event: Any) -> str | None:
    return core.upper(core.text(core.payload(event.raw_json), "source_timeframe", "timeframe", "chart_timeframe"))


def timeframe_duration(value: str | None) -> timedelta | None:
    return {
        "W1": timedelta(days=7), "D1": timedelta(days=1),
        "H4": timedelta(hours=4), "H1": timedelta(hours=1),
        "M15": timedelta(minutes=15),
    }.get((value or "").upper())


def parse_market_time(core: Any, value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            pass
    return core.parse_time(text)


def annotate_output(core: Any, output: dict[str, Any], ranges: list[Any], report: list[dict[str, Any]]) -> None:
    by_id = {item.id: item for item in ranges}
    for root_key in ("root", "trusted_root", "review_root"):
        stack = [
            *output[root_key].get("children", []),
            *output[root_key].get("unlinked_review_children", []),
        ]
        while stack:
            node = stack.pop()
            item = by_id.get(node.get("id"))
            if item is not None:
                node.update({
                    "status": item.canonical_status,
                    "inactive_from_time": item.canonical_inactive_from,
                    "direction_of_break": item.canonical_break_direction,
                    "lifecycle_history": list(item.lifecycle_history),
                    "lifecycle_resolution_source": item.lifecycle_resolution_source,
                    "snapshot_lifecycle": item.snapshot_lifecycle,
                    "supporting_break_events": item.supporting_break_events,
                })
            stack.extend(node.get("children", []))
    output["lifecycle_evidence_report"] = report
    stable = {
        "schema_version": core.VERSION, "symbol": output["symbol"],
        "root": core.strip_volatile_for_hash(output["root"]),
        "trusted_root": core.strip_volatile_for_hash(output["trusted_root"]),
        "review_root": core.strip_volatile_for_hash(output["review_root"]),
        "statistics": output["statistics"],
        "review_items": core.strip_volatile_for_hash(output["review_items"]),
        "lifecycle_evidence_report": core.strip_volatile_for_hash(report),
    }
    output["structural_content_hash"] = hashlib.sha256(core.dump(stable).encode()).hexdigest()


def lifecycle_evidence_report(core: Any, ranges: list[Any], reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons: dict[str, list[str]] = {}
    for review in reviews:
        if review.get("entity_kind") == "RANGE":
            for canonical_id in review.get("canonical_ids", []):
                reasons.setdefault(canonical_id, []).extend(review.get("reason_codes", []))
    report = []
    for item in ranges:
        if len(item.sources) < 2:
            continue
        snapshots = {row["raw_id"]: row for row in item.snapshot_lifecycle}
        candidates = []
        for raw in item.sources:
            payload = core.payload(raw.raw_json)
            row = snapshots.get(raw.raw_id, {})
            candidates.append({
                "case_ref": raw.case_ref, "source_record_id": raw.source_id,
                "raw_id": raw.raw_id, "import_run_id": raw.import_run_id,
                "import_order": raw.raw_id,
                "source_created_at_utc": raw.source_created_at,
                "source_updated_at_utc": raw.source_updated_at,
                "source_exported_at_utc": raw.source_exported_at,
                "source_status": raw.status,
                "snapshot_status": row.get("snapshot_status", raw.status),
                "active_from_time": raw.active_from,
                "inactive_from_time": raw.inactive_from,
                "direction_of_break": raw.break_direction,
                "broken_by_event_id": core.text(payload, "broken_by_event_id"),
                "old_range_id": core.text(payload, "old_range_id"),
                "new_range_id": core.text(payload, "new_range_id"),
            })
        report.append({
            "conflict_group_id": core.cid("lifecycle", (item.id,)),
            "canonical_ids": [item.id],
            "reason_codes": sorted(set(reasons.get(item.id, []))),
            "anchor": {
                "symbol": item.row.symbol, "structure_layer": item.row.layer,
                "source_timeframe": item.row.timeframe,
                "range_high": item.row.high, "range_low": item.row.low,
                "range_high_time": item.row.high_time,
                "range_low_time": item.row.low_time,
            },
            "candidates": sorted(candidates, key=lambda row: (
                row.get("source_updated_at_utc") or row.get("source_created_at_utc") or "",
                row["import_order"], row.get("case_ref") or "",
            )),
            "canonical_lifecycle": {
                "status": item.canonical_status,
                "active_from_time": item.row.active_from,
                "inactive_from_time": item.canonical_inactive_from,
                "direction_of_break": item.canonical_break_direction,
                "history": list(item.lifecycle_history),
                "resolution_source": item.lifecycle_resolution_source,
                "supporting_break_events": item.supporting_break_events,
            },
            "automatic_reconciliation": (
                "APPLIED_EXACT_BOUNDARY_LIFECYCLE_RULE"
                if item.processing_status == core.INCLUDED
                and item.lifecycle_resolution_source in {"EVENT_EVIDENCE", "EVENT_AND_OHLC"}
                else "NOT_APPLIED"
            ),
        })
    return sorted(report, key=lambda row: row["conflict_group_id"])
