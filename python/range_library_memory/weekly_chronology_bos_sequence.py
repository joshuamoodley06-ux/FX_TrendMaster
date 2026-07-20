"""Sequential Weekly Script 1 v2 policy.

The base Weekly Script 1 module owns persistence and projection contracts. This
policy upgrades only the analytical sequence:

* trusted Weekly ranges are ordered by the candle on which both anchors became
  known (later anchor first), then by first anchor and canonical id;
* each range scans W1 candles only until the next strictly later stored Weekly
  range becomes defined;
* the first strict breach of either boundary establishes BOS direction;
* an unbroken calendar gap between stored ranges does not stop candle scanning;
* a candle that breaches both boundaries is review-required, never guessed.

The installer follows the same explicit policy-overlay pattern used by the
Master Map lifecycle module. It keeps v1 rows available while writing v2 rows.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

POLICY_VERSION = "weekly_script1_v2"
POLICY_CONTENT_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _anchor_times(core: Any, node: Mapping[str, Any]) -> tuple[datetime | None, datetime | None]:
    return core.parse_time(node.get("range_high_time")), core.parse_time(node.get("range_low_time"))


def _defined_time(core: Any, node: Mapping[str, Any]) -> datetime | None:
    high_time, low_time = _anchor_times(core, node)
    if high_time is None or low_time is None or high_time == low_time:
        return None
    return max(high_time, low_time)


def _first_anchor_time(core: Any, node: Mapping[str, Any]) -> datetime | None:
    high_time, low_time = _anchor_times(core, node)
    values = [value for value in (high_time, low_time) if value is not None]
    return min(values) if values else None


def _node_sort_key(core: Any, node: Mapping[str, Any]) -> tuple[Any, ...]:
    last = datetime.max.replace(tzinfo=UTC)
    defined = _defined_time(core, node)
    first = _first_anchor_time(core, node)
    return (
        0 if defined is not None else 1,
        defined or last,
        first or last,
        str(node.get("id") or ""),
    )


def _result_sort_key(core: Any, row: Mapping[str, Any]) -> tuple[Any, ...]:
    last = datetime.max.replace(tzinfo=UTC)
    defined = core.parse_time(row.get("chronology_end_time"))
    first = core.parse_time(row.get("chronology_start_time"))
    return (
        0 if defined is not None else 1,
        defined or last,
        first or last,
        str(row.get("canonical_range_id") or ""),
    )


def _annotate_sequence(core: Any, nodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(node) for node in sorted(nodes, key=lambda node: _node_sort_key(core, node))]
    defined_times = [_defined_time(core, node) for node in ordered]
    for index, node in enumerate(ordered):
        current_defined = defined_times[index]
        next_later_index: int | None = None
        if current_defined is not None:
            for candidate_index in range(index + 1, len(ordered)):
                candidate_defined = defined_times[candidate_index]
                if candidate_defined is not None and candidate_defined > current_defined:
                    next_later_index = candidate_index
                    break
        immediate_next = ordered[index + 1] if index + 1 < len(ordered) else None
        node["_script1_sequence_index"] = index
        node["_script1_next_canonical_range_id"] = (
            str(immediate_next.get("id") or "") if immediate_next is not None else None
        )
        node["_script1_scan_end_time"] = (
            _iso(defined_times[next_later_index])
            if next_later_index is not None and defined_times[next_later_index] is not None
            else None
        )
    return ordered


def _trusted_weeklies(base: Any, core: Any, master_map: Mapping[str, Any], year: int | None, case_ref: str) -> list[dict[str, Any]]:
    # Build sequence against the complete selected-case set. A year filter must
    # not hide the next stored range and accidentally let an earlier range scan
    # through another range's candle window.
    ordered = _annotate_sequence(core, base(master_map, None, case_ref))
    if year is None:
        return ordered
    return [
        node
        for node in ordered
        if year in {
            value.year
            for value in _anchor_times(core, node)
            if value is not None
        }
    ]


def _touch_examples(core: Any, candle: Any, high: float, low: float) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    if candle.high == high:
        evidence = core.candle_evidence(candle, "BOS_UP")
        evidence["boundary"] = "RANGE_HIGH"
        examples.append(evidence)
    if candle.low == low:
        evidence = core.candle_evidence(candle, "BOS_DOWN")
        evidence["boundary"] = "RANGE_LOW"
        examples.append(evidence)
    return examples


def _evaluate_weekly(
    core: Any,
    source: Any,
    node: Mapping[str, Any],
    *,
    structural_hash: str | None,
    case_ref: str,
    run_id: str,
) -> dict[str, Any]:
    row = core.base_result(node, structural_hash, case_ref, run_id)
    high, low = row["range_high"], row["range_low"]
    high_time, low_time = core.parse_time(row["range_high_time"]), core.parse_time(row["range_low_time"])
    if high is None or low is None or high <= low:
        return core.finish(row, "NEEDS_REVIEW", {"INVALID_RANGE_PRICES"})
    if high_time is None or low_time is None:
        return core.finish(row, "NEEDS_REVIEW", {"MISSING_OR_INVALID_ANCHOR_TIME"})
    if high_time == low_time:
        return core.finish(row, "NEEDS_REVIEW", {"EQUAL_ANCHOR_TIMES"})

    if low_time < high_time:
        chronology, start_time, end_time = "RL_TO_RH", row["range_low_time"], row["range_high_time"]
        expected_direction = "BOS_UP"
    else:
        chronology, start_time, end_time = "RH_TO_RL", row["range_high_time"], row["range_low_time"]
        expected_direction = "BOS_DOWN"
    row.update({
        "chronology_result": chronology,
        "chronology_start_time": start_time,
        "chronology_end_time": end_time,
        "expected_bos_direction": expected_direction,
    })

    aliases = core.direction_aliases(node)
    if len(aliases) > 1:
        return core.finish(row, "NEEDS_REVIEW", {"CONFLICTING_DIRECTION_ALIASES"})

    parsed_end = core.parse_time(end_time)
    latest_text = core.latest_candle_time(source, symbol=row["symbol"], timeframe="W1")
    latest = core.parse_time(latest_text)
    scan_end_text = str(node.get("_script1_scan_end_time") or "").strip() or None
    scan_end = core.parse_time(scan_end_text)
    effective_end = min(value for value in (latest, scan_end) if value is not None) if latest or scan_end else None
    if parsed_end is None or effective_end is None or effective_end <= parsed_end:
        reason = "NO_W1_CANDLES_BEFORE_NEXT_RANGE" if scan_end is not None else "NO_W1_CANDLES_AFTER_ENDING_ANCHOR"
        return core.finish(row, "PENDING", {reason})

    candles = core.load_candles(
        source,
        symbol=row["symbol"],
        timeframe="W1",
        start_time=str(end_time),
        end_time=_iso(effective_end),
    )
    candidates = [
        candle
        for candle in candles
        if parsed_end < (core.parse_time(candle.time) or parsed_end) <= effective_end
    ]
    row["candles_scanned"] = len(candidates)
    touches = [
        example
        for candle in candidates
        for example in _touch_examples(core, candle, high, low)
    ]
    row["exact_touch_count"] = len(touches)
    row["exact_touch_examples"] = touches[:3]

    for candle in candidates:
        up = candle.high > high
        down = candle.low < low
        if not up and not down:
            continue
        if up and down:
            row.update({
                "bos_candle_time": candle.time,
                "bos_candle_open": candle.open,
                "bos_candle_high": candle.high,
                "bos_candle_low": candle.low,
                "bos_candle_close": candle.close,
            })
            return core.finish(row, "NEEDS_REVIEW", {"BOTH_BOUNDARIES_BREACHED_SAME_W1"})

        direction = "BOS_UP" if up else "BOS_DOWN"
        boundary = high if up else low
        evidence = core.candle_evidence(candle, direction)
        row.update({
            "bos_boundary": boundary,
            "bos_direction": direction,
            "reclaim_direction": "DOWN" if direction == "BOS_UP" else "UP",
            "bos_candle_time": evidence["time"],
            "bos_candle_open": evidence["open"],
            "bos_candle_high": evidence["high"],
            "bos_candle_low": evidence["low"],
            "bos_candle_close": evidence["close"],
            "bos_evidence_price": evidence["price"],
        })
        if aliases and direction not in aliases:
            return core.finish(row, "NEEDS_REVIEW", {"DETECTED_DIRECTION_CONFLICTS_WITH_STRUCTURAL_ALIAS"})
        return core.finish(row, "COMPLETE", set())

    reason = "STRICT_BOS_NOT_PROVEN_BEFORE_NEXT_RANGE" if scan_end is not None else "STRICT_BOS_NOT_PROVEN"
    return core.finish(row, "PENDING", {reason})


def _sort_projected_weeklies(core: Any, master_map: dict[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    ordered = sorted(results, key=lambda row: _result_sort_key(core, row))
    order = {str(row.get("canonical_range_id") or ""): index for index, row in enumerate(ordered)}
    next_ids = {
        str(row.get("canonical_range_id") or ""): (
            str(ordered[index + 1].get("canonical_range_id") or "") if index + 1 < len(ordered) else None
        )
        for index, row in enumerate(ordered)
    }

    def visit(node: dict[str, Any]) -> None:
        canonical_id = str(node.get("id") or "")
        if canonical_id in order:
            node["script1_sequence_index"] = order[canonical_id]
            node["script1_range_defined_at"] = ordered[order[canonical_id]].get("chronology_end_time")
            node["script1_next_canonical_range_id"] = next_ids[canonical_id]
        children = [child for child in node.get("children") or [] if isinstance(child, dict)]
        known_positions = [index for index, child in enumerate(children) if str(child.get("id") or "") in order]
        if len(known_positions) > 1:
            sorted_known = sorted((children[index] for index in known_positions), key=lambda child: order[str(child.get("id") or "")])
            for position, child in zip(known_positions, sorted_known):
                children[position] = child
            node["children"] = children
        for child in children:
            visit(child)

    for root_key in ("root", "trusted_root", "review_root"):
        root = master_map.get(root_key)
        if isinstance(root, dict):
            visit(root)
    analysis = master_map.setdefault("analysis", {}).setdefault("weekly_script1", {})
    analysis["processing_version"] = core.VERSION
    analysis["sequence_order"] = "RANGE_DEFINED_AT_ASC"


def _load_stored_results(base: Any, core: Any, connection: Any, symbol: str, case_ref: str | None = None) -> list[dict[str, Any]]:
    return sorted(base(connection, symbol, case_ref), key=lambda row: _result_sort_key(core, row))


def _select_validation_samples(core: Any, results: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
    ordered = sorted(results, key=lambda row: _result_sort_key(core, row))
    selected: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in ordered:
        key = f"{row.get('chronology_result')}|{row.get('bos_direction')}|{row.get('processing_status')}"
        if key not in seen:
            selected.append(row)
            seen.add(key)
        if len(selected) == limit:
            return selected
    for row in ordered:
        if row not in selected:
            selected.append(row)
        if len(selected) == limit:
            break
    return selected


def _summarize(base: Any, core: Any, results: Sequence[Mapping[str, Any]], **kwargs: Any) -> dict[str, Any]:
    summary = base(results, **kwargs)
    ordered = sorted(results, key=lambda row: _result_sort_key(core, row))
    hashes = [str(row["result_hash"]) for row in ordered]
    summary["script"] = core.VERSION
    summary["rows"] = ordered
    summary["result_hashes"] = hashes
    summary["aggregate_hash"] = hashlib.sha256(core.canonical_json(hashes).encode("utf-8")).hexdigest()
    summary["sequence_order"] = "RANGE_DEFINED_AT_ASC"
    return summary


def _weekly_outputs(core: Any, connection: Any, case_ref: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM weekly_script1_results WHERE case_ref=? AND processing_version=? "
        "ORDER BY chronology_end_time,chronology_start_time,canonical_range_id",
        (case_ref, core.VERSION),
    ).fetchall()
    return [
        {
            "canonical_range_id": row["canonical_range_id"],
            "input_hash": row["source_structural_hash"] or row["result_hash"],
            "processing_status": row["processing_status"],
            "payload": {
                "chronology": row["chronology_result"],
                "bos_direction": row["bos_direction"],
                "bos_time": row["bos_candle_time"],
                "expected_bos_direction": row["expected_bos_direction"],
                "reasons": json.loads(row["reason_codes_json"]),
            },
            "output_hash": row["result_hash"],
        }
        for row in rows
    ]


def install(core: Any, doctrine_pipeline: Any | None = None) -> None:
    """Install the sequential v2 policy onto the established Script 1 contract."""
    if getattr(core, "_sequential_weekly_script1_v2_installed", False):
        if doctrine_pipeline is not None:
            doctrine_pipeline._weekly_outputs = lambda connection, case_ref: _weekly_outputs(core, connection, case_ref)
        return

    base_trusted_weeklies = core.trusted_weeklies
    base_project_results = core.project_results
    base_load_stored_results = core.load_stored_results
    base_summarize = core.summarize

    core.VERSION = POLICY_VERSION
    core.SCRIPT_CONTENT_HASH = hashlib.sha256(
        f"{core.SCRIPT_CONTENT_HASH}:{POLICY_CONTENT_HASH}".encode("utf-8")
    ).hexdigest()
    core.trusted_weeklies = lambda master_map, year, case_ref: _trusted_weeklies(
        base_trusted_weeklies, core, master_map, year, case_ref
    )
    core.evaluate_weekly = lambda source, node, **kwargs: _evaluate_weekly(core, source, node, **kwargs)

    def project_results(master_map: dict[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
        base_project_results(master_map, results)
        _sort_projected_weeklies(core, master_map, results)

    core.project_results = project_results
    core.load_stored_results = lambda connection, symbol, case_ref=None: _load_stored_results(
        base_load_stored_results, core, connection, symbol, case_ref
    )
    core.select_validation_samples = lambda results, limit=5: _select_validation_samples(core, results, limit)
    core.summarize = lambda results, **kwargs: _summarize(base_summarize, core, results, **kwargs)
    core._sequential_weekly_script1_v2_installed = True

    if doctrine_pipeline is not None:
        doctrine_pipeline._weekly_outputs = lambda connection, case_ref: _weekly_outputs(core, connection, case_ref)
