"""Weekly and Daily statistics snapshots for the approved FXTM doctrine workspace.

The report reads the persisted Master Map and approved analytical enrichments from
an instrument analysis workspace. It never writes mapping ranges, events, parent
links, or raw-ledger truth. The only writes are report snapshots and export files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .db import connect
from .inspection import require_existing_db

REPORT_SCHEMA_VERSION = "weekly_daily_statistics_v1"
DEFAULT_WEEKLY_START = "2023-01-29"
DEFAULT_DAILY_START = "2024-10-27"
SNAPSHOT_TABLE = "statistics_report_snapshots"
WEEKLY_NAMESPACES = (
    "weekly_structure",
    "weekly_reclaim",
    "weekly_reclaim_depth",
    "weekly_movement_classification",
    "weekly_profile_classification",
    "weekly_extreme_rejection_destination",
)
DAILY_NAMESPACES = tuple(key.replace("weekly_", "daily_", 1) for key in WEEKLY_NAMESPACES)


class StatisticsReportError(RuntimeError):
    """Raised when a report cannot be built from the approved workspace."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _stable_json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_stamp(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _normalize_case(value: Any) -> str:
    return str(value or "").strip().removeprefix("raw:")


def _matches_case(node: Mapping[str, Any], case_ref: str) -> bool:
    refs = node.get("source_refs")
    if not isinstance(refs, list) or not refs:
        return True
    expected = _normalize_case(case_ref)
    for raw in refs:
        if not isinstance(raw, Mapping):
            continue
        actual = _normalize_case(raw.get("case_ref"))
        if not actual or actual == expected:
            return True
    return False


def _eligible(node: Mapping[str, Any]) -> bool:
    navigation = str(node.get("navigation_status") or "TRUSTED").upper()
    statistics_status = str(node.get("statistics_status") or "ELIGIBLE").upper()
    return navigation == "TRUSTED" and statistics_status == "ELIGIBLE"


def _node_times(node: Mapping[str, Any]) -> list[datetime]:
    result: list[datetime] = []
    for key in (
        "range_high_time",
        "range_low_time",
        "active_from_time",
        "inactive_from_time",
        "script1_bos_time",
    ):
        parsed = _parse_time(node.get(key))
        if parsed is not None:
            result.append(parsed)
    enrichments = node.get("analysis_enrichments")
    if isinstance(enrichments, Mapping):
        for raw in enrichments.values():
            if not isinstance(raw, Mapping):
                continue
            payload = raw.get("payload")
            if not isinstance(payload, Mapping):
                continue
            for key, value in payload.items():
                if key.endswith("_time") or key.endswith("_at"):
                    parsed = _parse_time(value)
                    if parsed is not None:
                        result.append(parsed)
    return result


def _node_start(node: Mapping[str, Any]) -> datetime | None:
    candidates = [
        _parse_time(node.get("range_high_time")),
        _parse_time(node.get("range_low_time")),
        _parse_time(node.get("active_from_time")),
    ]
    return min((value for value in candidates if value is not None), default=None)


def _node_end(node: Mapping[str, Any]) -> datetime | None:
    explicit = _parse_time(node.get("inactive_from_time"))
    if explicit is not None:
        return explicit
    return max(_node_times(node), default=None)


def _payload(node: Mapping[str, Any], namespace: str) -> dict[str, Any]:
    enrichments = node.get("analysis_enrichments")
    if not isinstance(enrichments, Mapping):
        return {}
    raw = enrichments.get(namespace)
    if not isinstance(raw, Mapping):
        return {}
    payload = raw.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _ensure_snapshot_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
            report_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            symbol TEXT NOT NULL,
            case_ref TEXT NOT NULL,
            weekly_start TEXT NOT NULL,
            daily_start TEXT NOT NULL,
            structural_content_hash TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            json_path TEXT NOT NULL,
            weekly_csv_path TEXT NOT NULL,
            daily_csv_path TEXT NOT NULL,
            parent_csv_path TEXT NOT NULL
        )"""
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{SNAPSHOT_TABLE}_scope "
        f"ON {SNAPSHOT_TABLE}(symbol,case_ref,generated_at)"
    )


def _master_map(connection: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    if not _table_exists(connection, "master_map_outputs"):
        raise StatisticsReportError("Persisted Master Map table is missing.")
    row = connection.execute(
        "SELECT output_json FROM master_map_outputs WHERE UPPER(symbol)=?",
        (symbol.upper(),),
    ).fetchone()
    if row is None:
        raise StatisticsReportError(f"Persisted Master Map is missing for {symbol.upper()}.")
    try:
        value = json.loads(str(row["output_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise StatisticsReportError("Persisted Master Map JSON is invalid.") from exc
    if not isinstance(value, dict):
        raise StatisticsReportError("Persisted Master Map must be an object.")
    return value


def _current_approved_versions(connection: sqlite3.Connection) -> list[dict[str, str]]:
    if not (
        _table_exists(connection, "doctrine_scripts")
        and _table_exists(connection, "doctrine_script_versions")
    ):
        return []
    rows = connection.execute(
        """SELECT s.script_key,v.version_id,v.version_label,v.adapter_key
             FROM doctrine_scripts s
             JOIN doctrine_script_versions v ON v.version_id=s.current_approved_version_id
            WHERE s.status='APPROVED'
            ORDER BY s.execution_order,s.script_key"""
    ).fetchall()
    return [
        {
            "script_key": str(row["script_key"]),
            "version_id": str(row["version_id"]),
            "version_label": str(row["version_label"]),
            "adapter_key": str(row["adapter_key"]),
        }
        for row in rows
    ]


def _weekly_statuses(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    case_ref: str,
) -> dict[tuple[str, str], str]:
    required = {"doctrine_scripts", "doctrine_script_versions", "doctrine_range_processing"}
    if not all(_table_exists(connection, name) for name in required):
        return {}
    rows = connection.execute(
        """SELECT p.canonical_range_id,s.script_key,p.processing_status,p.processed_at
             FROM doctrine_range_processing p
             JOIN doctrine_script_versions v ON v.version_id=p.version_id
             JOIN doctrine_scripts s ON s.script_id=v.script_id
            WHERE s.status='APPROVED'
              AND s.current_approved_version_id=p.version_id
              AND UPPER(p.symbol)=?
              AND p.case_ref=?
            ORDER BY p.processed_at""",
        (symbol.upper(), case_ref),
    ).fetchall()
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        result[(str(row["canonical_range_id"]), str(row["script_key"]))] = str(
            row["processing_status"] or "PENDING"
        ).upper()
    return result


def _daily_statuses(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    case_ref: str,
) -> dict[tuple[str, str], str]:
    if not _table_exists(connection, "inherited_doctrine_enrichments"):
        return {}
    rows = connection.execute(
        """SELECT canonical_range_id,target_namespace,processing_status,updated_at
             FROM inherited_doctrine_enrichments
            WHERE UPPER(symbol)=? AND case_ref=? AND active=1
            ORDER BY updated_at""",
        (symbol.upper(), case_ref),
    ).fetchall()
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        result[(str(row["canonical_range_id"]), str(row["target_namespace"]))] = str(
            row["processing_status"] or "PENDING"
        ).upper()
    return result


def _namespace_status(
    node: Mapping[str, Any],
    namespace: str,
    stored: Mapping[tuple[str, str], str],
) -> str:
    identity = str(node.get("id") or "")
    status = str(stored.get((identity, namespace)) or "").upper()
    if status:
        return status
    payload = _payload(node, namespace)
    inherited = str(
        payload.get("inherited_processing_status")
        or payload.get("processing_status")
        or ""
    ).upper()
    if inherited:
        return inherited
    if namespace == "weekly_structure":
        legacy = str(node.get("script1_processing_status") or "").upper()
        if legacy:
            return legacy
    enrichments = node.get("analysis_enrichments")
    if isinstance(enrichments, Mapping) and namespace in enrichments:
        return "COMPLETE"
    return "PENDING"


def _overall_status(statuses: Mapping[str, str]) -> str:
    values = {str(value or "PENDING").upper() for value in statuses.values()}
    if "NEEDS_REVIEW" in values:
        return "NEEDS_REVIEW"
    if values and values <= {"COMPLETE"}:
        return "COMPLETE"
    return "PENDING"


def _counter(values: Iterable[Any], *, missing: str = "PENDING") -> dict[str, int]:
    normalized = [
        str(value if value not in (None, "") else missing).upper()
        for value in values
    ]
    return dict(sorted(Counter(normalized).items()))


def _numeric_summary(values: Iterable[Any]) -> dict[str, float | int | None]:
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            numbers.append(number)
    if not numbers:
        return {
            "count": 0,
            "average": None,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "count": len(numbers),
        "average": round(sum(numbers) / len(numbers), 4),
        "median": round(float(statistics.median(numbers)), 4),
        "minimum": round(min(numbers), 4),
        "maximum": round(max(numbers), 4),
    }


def _stage_status_counts(
    rows: Sequence[Mapping[str, Any]],
    namespaces: Sequence[str],
) -> dict[str, dict[str, int]]:
    return {
        namespace: _counter(
            row.get("stage_statuses", {}).get(namespace)
            for row in rows
        )
        for namespace in namespaces
    }


def _analysis_summary(rows: Sequence[Mapping[str, Any]], layer: str) -> dict[str, Any]:
    is_weekly = layer == "WEEKLY"
    unit_key = "weeks" if is_weekly else "days"
    return {
        "range_count": len(rows),
        "processing_status_counts": _counter(row.get("processing_status") for row in rows),
        "stage_status_counts": _stage_status_counts(
            rows,
            WEEKLY_NAMESPACES if is_weekly else DAILY_NAMESPACES,
        ),
        "bos_direction_counts": _counter(row.get("bos_direction") for row in rows),
        "reclaim_status_counts": _counter(row.get("reclaim_status") for row in rows),
        "profile_counts": _counter(row.get("profile") for row in rows),
        "movement_sequence_counts": _counter(row.get("movement_sequence") for row in rows),
        "extreme_destination_counts": _counter(row.get("extreme_destination") for row in rows),
        f"{unit_key}_to_bos": _numeric_summary(
            row.get(f"{unit_key}_to_bos") for row in rows
        ),
        f"{unit_key}_to_reclaim": _numeric_summary(
            row.get(f"{unit_key}_to_reclaim") for row in rows
        ),
    }


def _range_row(
    node: Mapping[str, Any],
    *,
    layer: str,
    parent_id: str | None,
    statuses: Mapping[tuple[str, str], str],
) -> dict[str, Any]:
    prefix = "weekly" if layer == "WEEKLY" else "daily"
    namespaces = WEEKLY_NAMESPACES if layer == "WEEKLY" else DAILY_NAMESPACES
    stage_statuses = {
        namespace: _namespace_status(node, namespace, statuses)
        for namespace in namespaces
    }
    structure = _payload(node, f"{prefix}_structure")
    reclaim = _payload(node, f"{prefix}_reclaim")
    depth = _payload(node, f"{prefix}_reclaim_depth")
    movement = _payload(node, f"{prefix}_movement_classification")
    profile = _payload(node, f"{prefix}_profile_classification")
    destination = _payload(node, f"{prefix}_extreme_rejection_destination")
    unit_key = "weeks" if layer == "WEEKLY" else "days"
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "layer": layer,
        "weekly_parent_id": parent_id,
        "start_date": _date_stamp(_node_start(node)),
        "end_date": _date_stamp(_node_end(node)),
        "range_high": node.get("range_high"),
        "range_low": node.get("range_low"),
        "range_status": str(node.get("status") or "").upper(),
        "processing_status": _overall_status(stage_statuses),
        "stage_statuses": stage_statuses,
        "bos_direction": structure.get("bos_direction") or node.get("script1_bos_direction"),
        "bos_time": structure.get("bos_time") or node.get("script1_bos_time"),
        f"{unit_key}_to_bos": structure.get(f"{unit_key}_to_bos"),
        "reclaim_status": reclaim.get("reclaim_status"),
        "reclaim_time": reclaim.get("reclaim_time"),
        f"{unit_key}_to_reclaim": reclaim.get(f"{unit_key}_to_reclaim"),
        "reclaim_depth_percent": depth.get("reclaim_depth_percent"),
        "movement_path": movement.get("movement_path"),
        "movement_sequence": movement.get("movement_sequence"),
        "profile": profile.get("profile_classification") or profile.get("profile_badge"),
        "extreme_origin": destination.get("primary_origin_zone"),
        "extreme_destination": destination.get("primary_maximum_destination"),
        "extreme_journey_status": destination.get("primary_journey_status"),
    }


def _collect_rows(
    master_map: Mapping[str, Any],
    *,
    case_ref: str,
    weekly_start: datetime,
    daily_start: datetime,
    weekly_statuses: Mapping[tuple[str, str], str],
    daily_statuses: Mapping[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    trusted = master_map.get("trusted_root")
    roots = trusted.get("children") if isinstance(trusted, Mapping) else []
    weekly_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    unlinked_daily = 0

    def visit(node: Any, weekly_parent_id: str | None = None) -> None:
        nonlocal unlinked_daily
        if (
            not isinstance(node, Mapping)
            or not _eligible(node)
            or not _matches_case(node, case_ref)
        ):
            return
        layer = str(node.get("structure_layer") or "").upper()
        identity = str(node.get("id") or "")
        current_parent = weekly_parent_id
        if layer == "WEEKLY":
            current_parent = identity
            start = _node_start(node)
            if start is not None and start >= weekly_start:
                weekly_rows.append(
                    _range_row(
                        node,
                        layer="WEEKLY",
                        parent_id=None,
                        statuses=weekly_statuses,
                    )
                )
        elif layer == "DAILY":
            start = _node_start(node)
            if start is not None and start >= daily_start:
                if current_parent is None:
                    unlinked_daily += 1
                daily_rows.append(
                    _range_row(
                        node,
                        layer="DAILY",
                        parent_id=current_parent,
                        statuses=daily_statuses,
                    )
                )
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                visit(child, current_parent)

    if isinstance(roots, list):
        for root in roots:
            visit(root)
    weekly_rows.sort(
        key=lambda row: (row.get("start_date") or "9999", row["canonical_range_id"])
    )
    daily_rows.sort(
        key=lambda row: (
            row.get("weekly_parent_id") or "~",
            row.get("start_date") or "9999",
            row["canonical_range_id"],
        )
    )
    return weekly_rows, daily_rows, unlinked_daily


def _alignment(weekly_bos: Any, daily_bos: Any) -> str:
    weekly = str(weekly_bos or "").upper()
    daily = str(daily_bos or "").upper()
    if weekly not in {"BOS_UP", "BOS_DOWN"} or daily not in {"BOS_UP", "BOS_DOWN"}:
        return "UNRESOLVED"
    return "BOS_ALIGNED" if weekly == daily else "BOS_COUNTER"


def _parent_rows(
    weekly_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    weekly_by_id = {str(row["canonical_range_id"]): row for row in weekly_rows}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in daily_rows:
        parent_id = str(row.get("weekly_parent_id") or "")
        if parent_id:
            grouped.setdefault(parent_id, []).append(row)
    result: list[dict[str, Any]] = []
    for parent_id, children in grouped.items():
        weekly = weekly_by_id.get(parent_id) or {
            "canonical_range_id": parent_id,
            "start_date": None,
            "processing_status": "PENDING",
            "bos_direction": None,
            "profile": None,
        }
        alignment_counts = _counter(
            _alignment(weekly.get("bos_direction"), child.get("bos_direction"))
            for child in children
        )
        result.append(
            {
                "weekly_parent_id": parent_id,
                "weekly_start_date": weekly.get("start_date"),
                "weekly_processing_status": weekly.get("processing_status"),
                "weekly_bos_direction": weekly.get("bos_direction"),
                "weekly_profile": weekly.get("profile"),
                "daily_child_count": len(children),
                "daily_complete_count": sum(
                    child.get("processing_status") == "COMPLETE" for child in children
                ),
                "daily_pending_count": sum(
                    child.get("processing_status") == "PENDING" for child in children
                ),
                "daily_needs_review_count": sum(
                    child.get("processing_status") == "NEEDS_REVIEW"
                    for child in children
                ),
                "bos_alignment_counts": alignment_counts,
                "daily_child_ids": [
                    str(child["canonical_range_id"]) for child in children
                ],
            }
        )
    result.sort(
        key=lambda row: (
            row.get("weekly_start_date") or "9999",
            row["weekly_parent_id"],
        )
    )
    return result


def _parent_summary(
    parent_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    unlinked: int,
) -> dict[str, Any]:
    child_counts = [int(row.get("daily_child_count") or 0) for row in parent_rows]
    alignment = Counter()
    for row in parent_rows:
        alignment.update(row.get("bos_alignment_counts") or {})
    return {
        "weekly_parent_count": len(parent_rows),
        "parents_with_daily_children": len(parent_rows),
        "daily_child_count": len(daily_rows),
        "unlinked_daily_count": unlinked,
        "average_daily_children_per_parent": (
            round(sum(child_counts) / len(child_counts), 4) if child_counts else None
        ),
        "median_daily_children_per_parent": (
            round(float(statistics.median(child_counts)), 4)
            if child_counts
            else None
        ),
        "bos_alignment_counts": dict(sorted(alignment.items())),
    }


def _csv_scalar(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_scalar(row.get(key)) for key in fieldnames})


def _output_paths(
    db_path: Path,
    report_id: str,
    output_dir: str | Path | None,
) -> dict[str, Path]:
    root = (
        Path(output_dir).resolve()
        if output_dir
        else db_path.resolve().parent / "statistics-reports"
    )
    folder = root / report_id
    return {
        "folder": folder,
        "json": folder / "report.json",
        "weekly_csv": folder / "weekly_ranges.csv",
        "daily_csv": folder / "daily_ranges.csv",
        "parent_csv": folder / "weekly_daily_parents.csv",
    }


def build_statistics_report(
    db_path: str | Path,
    *,
    case_ref: str,
    symbol: str = "XAUUSD",
    weekly_start: str = DEFAULT_WEEKLY_START,
    daily_start: str = DEFAULT_DAILY_START,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build and persist one immutable Weekly + Daily statistics snapshot."""
    db = require_existing_db(db_path)
    case_key = str(case_ref or "").strip()
    symbol_key = str(symbol or "").strip().upper()
    weekly_cutoff = _parse_time(weekly_start)
    daily_cutoff = _parse_time(daily_start)
    if not case_key:
        raise StatisticsReportError("case_ref is required.")
    if symbol_key != "XAUUSD":
        raise StatisticsReportError("Weekly + Daily statistics v1 supports XAUUSD only.")
    if weekly_cutoff is None or daily_cutoff is None:
        raise StatisticsReportError("Report date boundaries are invalid.")
    if daily_cutoff < weekly_cutoff:
        raise StatisticsReportError(
            "Daily-enabled boundary cannot precede Weekly boundary."
        )

    generated_at = _now()
    with connect(db) as connection:
        _ensure_snapshot_schema(connection)
        master = _master_map(connection, symbol_key)
        structural_hash = str(master.get("structural_content_hash") or "")
        if not structural_hash:
            raise StatisticsReportError(
                "Master Map structural content hash is missing."
            )
        versions = _current_approved_versions(connection)
        report_input_hash = _sha(
            [
                structural_hash,
                versions,
                case_key,
                symbol_key,
                weekly_cutoff.date().isoformat(),
                daily_cutoff.date().isoformat(),
            ]
        )
        prior = connection.execute(
            f"""SELECT payload_json FROM {SNAPSHOT_TABLE}
                 WHERE UPPER(symbol)=? AND case_ref=?
                   AND weekly_start=? AND daily_start=?
                   AND structural_content_hash=?
                 ORDER BY generated_at DESC LIMIT 1""",
            (
                symbol_key,
                case_key,
                weekly_cutoff.date().isoformat(),
                daily_cutoff.date().isoformat(),
                structural_hash,
            ),
        ).fetchone()
        if prior is not None:
            try:
                previous_payload = json.loads(str(prior["payload_json"]))
            except json.JSONDecodeError:
                previous_payload = None
            if (
                isinstance(previous_payload, dict)
                and previous_payload.get("report_input_hash") == report_input_hash
            ):
                previous_payload["reused"] = True
                previous_payload["stale"] = False
                previous_payload["current_structural_content_hash"] = structural_hash
                return previous_payload

        weekly_processing = _weekly_statuses(
            connection,
            symbol=symbol_key,
            case_ref=case_key,
        )
        daily_processing = _daily_statuses(
            connection,
            symbol=symbol_key,
            case_ref=case_key,
        )
        weekly_rows, daily_rows, unlinked_daily = _collect_rows(
            master,
            case_ref=case_key,
            weekly_start=weekly_cutoff,
            daily_start=daily_cutoff,
            weekly_statuses=weekly_processing,
            daily_statuses=daily_processing,
        )
        parent_rows = _parent_rows(weekly_rows, daily_rows)
        all_dates = [
            _parse_time(value)
            for row in [*weekly_rows, *daily_rows]
            for value in (
                row.get("start_date"),
                row.get("end_date"),
                row.get("bos_time"),
                row.get("reclaim_time"),
            )
        ]
        latest = max(
            (value for value in all_dates if value is not None),
            default=None,
        )
        report_id = (
            f"{generated_at[:19].replace(':', '').replace('-', '')}Z-"
            f"{_sha([structural_hash, case_key, generated_at])[:10]}"
        )
        paths = _output_paths(Path(db), report_id, output_dir)
        report: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_id": report_id,
            "generated_at": generated_at,
            "symbol": symbol_key,
            "case_ref": case_key,
            "structural_content_hash": structural_hash,
            "report_input_hash": report_input_hash,
            "reused": False,
            "dataset": {
                "weekly_start": weekly_cutoff.date().isoformat(),
                "weekly_only_through": "2024-10-06",
                "daily_enabled_start": daily_cutoff.date().isoformat(),
                "latest_mapped_date": _date_stamp(latest),
                "parent_join_rule": "EXACT_MASTER_MAP_HIERARCHY",
            },
            "doctrine_versions": versions,
            "overview": {
                "weekly": _analysis_summary(weekly_rows, "WEEKLY"),
                "daily": _analysis_summary(daily_rows, "DAILY"),
                "parent_child": _parent_summary(
                    parent_rows,
                    daily_rows,
                    unlinked_daily,
                ),
            },
            "weekly_rows": weekly_rows,
            "daily_rows": daily_rows,
            "parent_rows": parent_rows,
            "exports": {
                "folder": str(paths["folder"]),
                "json": str(paths["json"]),
                "weekly_csv": str(paths["weekly_csv"]),
                "daily_csv": str(paths["daily_csv"]),
                "parent_csv": str(paths["parent_csv"]),
            },
        }
        paths["folder"].mkdir(parents=True, exist_ok=True)
        paths["json"].write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_csv(paths["weekly_csv"], weekly_rows)
        _write_csv(paths["daily_csv"], daily_rows)
        _write_csv(paths["parent_csv"], parent_rows)
        connection.execute(
            f"""INSERT INTO {SNAPSHOT_TABLE} (
                report_id,schema_version,symbol,case_ref,weekly_start,daily_start,
                structural_content_hash,generated_at,payload_json,json_path,
                weekly_csv_path,daily_csv_path,parent_csv_path
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report_id,
                REPORT_SCHEMA_VERSION,
                symbol_key,
                case_key,
                weekly_cutoff.date().isoformat(),
                daily_cutoff.date().isoformat(),
                structural_hash,
                generated_at,
                _stable_json(report),
                str(paths["json"]),
                str(paths["weekly_csv"]),
                str(paths["daily_csv"]),
                str(paths["parent_csv"]),
            ),
        )
        connection.commit()
        return report


def apply_persisted_statistics_report_metadata(
    connection: sqlite3.Connection,
    master_map: dict[str, Any],
    *,
    symbol: str,
    history_limit: int = 20,
) -> dict[str, Any]:
    """Attach latest report payloads and history after a Master Map rebuild."""
    if not _table_exists(connection, SNAPSHOT_TABLE):
        master_map.setdefault("analysis", {}).pop(
            "weekly_daily_statistics_reports",
            None,
        )
        return {"case_count": 0, "snapshot_count": 0}
    rows = connection.execute(
        f"""SELECT * FROM {SNAPSHOT_TABLE}
             WHERE UPPER(symbol)=?
             ORDER BY generated_at DESC""",
        (symbol.upper(),),
    ).fetchall()
    current_hash = str(master_map.get("structural_content_hash") or "")
    by_case: dict[str, dict[str, Any]] = {}
    snapshot_count = 0
    for row in rows:
        case_ref = str(row["case_ref"] or "")
        bucket = by_case.setdefault(
            case_ref,
            {"latest_report": None, "snapshots": []},
        )
        if len(bucket["snapshots"]) >= max(1, history_limit):
            continue
        metadata = {
            "report_id": str(row["report_id"]),
            "schema_version": str(row["schema_version"]),
            "generated_at": str(row["generated_at"]),
            "weekly_start": str(row["weekly_start"]),
            "daily_start": str(row["daily_start"]),
            "structural_content_hash": str(row["structural_content_hash"]),
            "stale": bool(
                current_hash
                and str(row["structural_content_hash"]) != current_hash
            ),
            "exports": {
                "json": str(row["json_path"]),
                "weekly_csv": str(row["weekly_csv_path"]),
                "daily_csv": str(row["daily_csv_path"]),
                "parent_csv": str(row["parent_csv_path"]),
            },
        }
        bucket["snapshots"].append(metadata)
        snapshot_count += 1
        if bucket["latest_report"] is None:
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                payload["stale"] = metadata["stale"]
                payload["current_structural_content_hash"] = current_hash
                bucket["latest_report"] = payload
    summary = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "current_structural_content_hash": current_hash,
        "by_case": by_case,
    }
    master_map.setdefault("analysis", {})[
        "weekly_daily_statistics_reports"
    ] = summary
    return {
        "case_count": len(by_case),
        "snapshot_count": snapshot_count,
    }
