"""Build a disposable, read-only XAUUSD Mapping Assistant snapshot.

The snapshot rebuilds the Master Map inside a temporary SQLite backup, runs the
first-query doctrine report against that disposable build, and projects only the
missing-work records Electron needs. The source Range Library database is never
mutated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .master_map import build_master_map
from .xauusd_first_query_doctrine import build_first_query_doctrine_report

SNAPSHOT_SCHEMA_VERSION = "xauusd_mapping_assistant_snapshot_v0.1"
GAP_SCHEMA_VERSION = "xauusd_mapping_assistant_gap_v0.1"
FIXED_BUILD_TIME = "1970-01-01T00:00:00Z"


class MappingAssistantError(ValueError):
    """Unsafe or invalid Mapping Assistant input."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def backup_sqlite_database(source: str | Path, destination: str | Path) -> None:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Range Library database does not exist: {source_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_readonly_uri(source_path), uri=True) as source_db:
        with sqlite3.connect(destination_path) as destination_db:
            source_db.backup(destination_db)


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def shift_days(value: Any, days: int) -> str | None:
    parsed = parse_time(value)
    return iso(parsed + timedelta(days=days)) if parsed else None


def sorted_times(values: Sequence[Any]) -> list[str]:
    parsed = [parse_time(value) for value in values]
    return [iso(value) for value in sorted(item for item in parsed if item is not None) if iso(value)]


def flatten_ranges(root: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(node: Mapping[str, Any]) -> None:
        if str(node.get("node_type") or "").upper() == "RANGE":
            result.append(dict(node))
        for child in node.get("children") or []:
            if isinstance(child, Mapping):
                visit(child)
        for child in node.get("unlinked_review_children") or []:
            if isinstance(child, Mapping):
                visit(child)

    visit(root)
    return result


def source_record_ids(node: Mapping[str, Any] | None) -> list[str]:
    if not node:
        return []
    values = {
        str(ref.get("source_record_id"))
        for ref in node.get("source_refs") or []
        if isinstance(ref, Mapping) and ref.get("source_record_id") not in (None, "")
    }
    return sorted(values)


def layer_default_timeframe(layer: str | None) -> str:
    return {
        "WEEKLY": "W1",
        "DAILY": "D1",
        "INTRADAY": "H1",
        "MICRO": "M15",
    }.get(str(layer or "").upper(), "D1")


def range_contract(node: Mapping[str, Any] | None) -> dict[str, Any]:
    node = node or {}
    layer = str(node.get("structure_layer") or "WEEKLY").upper()
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "source_range_ids": source_record_ids(node),
        "structure_layer": layer,
        "source_timeframe": str(node.get("source_timeframe") or layer_default_timeframe(layer)).upper(),
        "range_high": node.get("range_high"),
        "range_low": node.get("range_low"),
        "range_high_time": node.get("range_high_time"),
        "range_low_time": node.get("range_low_time"),
        "active_from_time": node.get("active_from_time"),
        "inactive_from_time": node.get("inactive_from_time"),
        "status": node.get("status"),
        "navigation_status": node.get("navigation_status"),
        "statistics_status": node.get("statistics_status"),
        "source_refs": list(node.get("source_refs") or []),
    }


def trader_instruction(action: str, earliest_freeze: str | None) -> tuple[str, str]:
    date_label = str(earliest_freeze or "the first blocked candidate").split("T")[0]
    if action == "CONFIRM_WEEKLY_LIFECYCLE":
        return (
            "Weekly lifecycle needs confirmation",
            f"Review this exact Weekly parent before {date_label}. Confirm whether its active leg was still valid, broken, or unresolved.",
        )
    if action == "REVIEW_PARENT_LINK":
        return (
            "Weekly parent link needs review",
            f"Review the candidate and its containing Weekly range before {date_label}. Correct the parent only through the normal audited mapping workflow.",
        )
    if action == "CONFIRM_WEEKLY_ORIGIN":
        return (
            "Weekly origin needs confirmation",
            f"Open this Weekly parent at its origin and confirm the direction-establishing evidence that existed before {date_label}.",
        )
    return (
        "Weekly direction evidence missing",
        f"Review the Weekly move that created this exact parent before {date_label}. Map the direction-establishing BOS only when the chart proves it.",
    )


def structure_navigation(parent: Mapping[str, Any], earliest_freeze: str | None) -> dict[str, Any]:
    anchor_times = sorted_times([
        parent.get("range_high_time"),
        parent.get("range_low_time"),
        parent.get("active_from_time"),
    ])
    preferred = parent.get("active_from_time") or (anchor_times[-1] if anchor_times else earliest_freeze)
    earliest_anchor = anchor_times[0] if anchor_times else preferred
    visible_start = shift_days(earliest_anchor, -84) or earliest_anchor or earliest_freeze
    visible_end = earliest_freeze or shift_days(preferred, 42) or preferred
    return {
        "canonical_range_id": str(parent.get("id") or ""),
        "event_id": None,
        "target_layer": "WEEKLY",
        "target_timeframe": "W1",
        "preferred_anchor_time": preferred,
        "visible_start": visible_start,
        "visible_end": visible_end,
    }


def candidate_navigation(child: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    layer = str(child.get("structure_layer") or "DAILY").upper()
    freeze = state.get("freeze_at")
    times = sorted_times([
        child.get("range_high_time"),
        child.get("range_low_time"),
        child.get("active_from_time"),
        freeze,
    ])
    pad_before, pad_after = {
        "DAILY": (35, 14),
        "INTRADAY": (7, 3),
        "MICRO": (2, 1),
    }.get(layer, (21, 7))
    visible_start = shift_days(times[0] if times else freeze, -pad_before)
    visible_end = shift_days(times[-1] if times else freeze, pad_after)
    return {
        "canonical_range_id": str(child.get("id") or state.get("child_range_id") or ""),
        "event_id": state.get("confirming_event_id"),
        "target_layer": layer,
        "target_timeframe": str(
            state.get("source_timeframe")
            or child.get("source_timeframe")
            or layer_default_timeframe(layer)
        ).upper(),
        "preferred_anchor_time": freeze,
        "visible_start": visible_start,
        "visible_end": visible_end,
    }


def stable_gap_id(parent_id: str, missing: Sequence[str], candidate_ids: Sequence[str]) -> str:
    raw = "|".join([parent_id, *sorted(missing), *sorted(candidate_ids)])
    return f"mapping-gap:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def project_mapping_assistant_snapshot(
    master_map: Mapping[str, Any],
    doctrine_report: Mapping[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if str(master_map.get("symbol") or "").upper() != "XAUUSD":
        raise MappingAssistantError("Mapping Assistant v0.1 is scoped to XAUUSD only.")
    range_index = {
        str(item.get("id")): item
        for item in flatten_ranges(master_map.get("root") or {})
        if item.get("id")
    }
    state_index = {
        str(item.get("candidate_state_id")): item
        for item in doctrine_report.get("states") or []
        if isinstance(item, Mapping) and item.get("candidate_state_id")
    }

    gaps: list[dict[str, Any]] = []
    for queue_item in doctrine_report.get("weekly_parent_priority_queue") or []:
        if not isinstance(queue_item, Mapping):
            continue
        parent_id = str(queue_item.get("weekly_parent_range_id") or "")
        parent = range_index.get(parent_id)
        candidate_ids = [str(value) for value in queue_item.get("candidate_state_ids") or []]
        candidate_states = [state_index[value] for value in candidate_ids if value in state_index]
        if not parent or not candidate_states:
            continue
        first_state = min(candidate_states, key=lambda item: str(item.get("freeze_at") or ""))
        child = range_index.get(str(first_state.get("child_range_id") or ""))
        if not child:
            continue
        missing = [str(value) for value in queue_item.get("exact_missing_evidence") or []]
        action = str(queue_item.get("recommended_mapping_action") or "MAP_WEEKLY_FORMATION_BOS")
        title, instruction = trader_instruction(action, first_state.get("freeze_at"))
        gaps.append({
            "schema_version": GAP_SCHEMA_VERSION,
            "gap_id": stable_gap_id(parent_id, missing, candidate_ids),
            "priority_rank": int(queue_item.get("priority_rank") or 0),
            "gap_type": "RESEARCH_EVIDENCE",
            "symbol": "XAUUSD",
            "parent": range_contract(parent),
            "research_impact": {
                "blocked_candidate_count": int(queue_item.get("blocked_candidate_count") or len(candidate_states)),
                "blocked_candidate_ids": sorted(candidate_ids),
                "earliest_candidate_freeze": queue_item.get("earliest_candidate_freeze"),
                "latest_candidate_freeze": queue_item.get("latest_candidate_freeze"),
            },
            "requirement": {
                "missing_evidence_code": missing,
                "recommended_action_code": action,
                "evidence_already_present": list(queue_item.get("evidence_already_present") or []),
                "trader_title": title,
                "trader_instruction": instruction,
            },
            "navigation": {
                "open_structure": structure_navigation(parent, first_state.get("freeze_at")),
                "show_first_candidate": candidate_navigation(child, first_state),
            },
        })

    gaps.sort(key=lambda item: (item["priority_rank"], item["gap_id"]))
    summary = doctrine_report.get("summary") or {}
    payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or utc_now(),
        "symbol": "XAUUSD",
        "structural_content_hash": master_map.get("structural_content_hash"),
        "summary": {
            "research_gap_count": len(gaps),
            "blocked_candidate_count": sum(
                int(item["research_impact"]["blocked_candidate_count"]) for item in gaps
            ),
            "unique_weekly_parent_count": int(summary.get("unique_weekly_parent_count") or len(gaps)),
            "structure_query_ready_count": int(summary.get("structure_query_ready_count") or 0),
            "confirmation_query_ready_count": int(summary.get("confirmation_query_ready_count") or 0),
            "outcome_query_ready_count": int(summary.get("outcome_query_ready_count") or 0),
            "overall_first_query_ready_count": int(summary.get("overall_first_query_ready_count") or 0),
        },
        "gaps": gaps,
        "master_map": master_map,
    }
    stable = dict(payload)
    stable.pop("generated_at_utc", None)
    payload["determinism_hash"] = hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()
    return payload


def build_mapping_assistant_snapshot(
    db_path: str | Path,
    *,
    symbol: str = "XAUUSD",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source = Path(db_path).expanduser().resolve()
    if symbol.strip().upper() != "XAUUSD":
        raise MappingAssistantError("Mapping Assistant v0.1 is scoped to XAUUSD only.")
    if not source.exists():
        raise FileNotFoundError(f"Range Library database does not exist: {source}")
    before = sha256_file(source)
    with tempfile.TemporaryDirectory(prefix="fxtm-mapping-assistant-") as temporary:
        snapshot_db = Path(temporary) / "range_library_snapshot.sqlite3"
        backup_sqlite_database(source, snapshot_db)
        master_map = build_master_map(
            snapshot_db,
            symbol="XAUUSD",
            built_at_utc=FIXED_BUILD_TIME,
            build_id="mapping-assistant-disposable",
        )
        report = build_first_query_doctrine_report(
            master_map,
            generated_at_utc=FIXED_BUILD_TIME,
        )
        payload = project_mapping_assistant_snapshot(
            master_map,
            report,
            generated_at_utc=generated_at_utc,
        )
    after = sha256_file(source)
    if before != after:
        raise MappingAssistantError("Source Range Library database changed during read-only Mapping Assistant build.")
    payload["source_integrity"] = {
        "database_path": str(source),
        "sha256_before": before,
        "sha256_after": after,
        "unchanged": True,
        "build_mode": "DISPOSABLE_SQLITE_BACKUP",
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.xauusd_mapping_assistant")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_mapping_assistant_snapshot(args.db_path, symbol=args.symbol)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"research_gap_count: {result['summary']['research_gap_count']}")
        print(f"blocked_candidate_count: {result['summary']['blocked_candidate_count']}")
        print(f"determinism_hash: {result['determinism_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
