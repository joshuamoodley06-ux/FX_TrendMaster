"""Independent sequential Weekly chronology/BOS adapter v2.

V1 remains executable and approved while this version is reviewed. V2 orders
Weekly ranges by the time both anchors became known, then scans W1 candles after
the later anchor. The first strict breach of either RH or RL establishes BOS.
Mapping gaps do not interrupt the scan.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

POLICY_VERSION = "weekly_script1_v2"
ADAPTER_KEY = "weekly_chronology_bos_v2"
SOURCE_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _sort_key(core: Any, item: Mapping[str, Any]) -> tuple[Any, ...]:
    high = core.parse_time(item.get("range_high_time"))
    low = core.parse_time(item.get("range_low_time"))
    last = datetime.max.replace(tzinfo=UTC)
    defined = max(high, low) if high is not None and low is not None and high != low else None
    first = min(value for value in (high, low) if value is not None) if high or low else None
    identity = str(item.get("canonical_range_id") or item.get("id") or "")
    return (0 if defined else 1, defined or last, first or last, identity)


def _ordered_weeklies(core: Any, master: Mapping[str, Any], case_ref: str) -> list[dict[str, Any]]:
    return [dict(node) for node in sorted(core.trusted_weeklies(master, None, case_ref), key=lambda row: _sort_key(core, row))]


def _structural_aliases(core: Any, node: Mapping[str, Any]) -> set[str]:
    # Prior Script 1 output is analytical evidence, not structural truth. Only
    # mapped/lifecycle directions may challenge the newly detected candle fact.
    return {
        value
        for field in ("direction_of_break", "lifecycle_direction_of_break")
        if (value := core.normalized_break_direction(node.get(field))) is not None
    }


def _touches(core: Any, candle: Any, high: float, low: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if candle.high == high:
        item = core.candle_evidence(candle, "BOS_UP")
        item["boundary"] = "RANGE_HIGH"
        result.append(item)
    if candle.low == low:
        item = core.candle_evidence(candle, "BOS_DOWN")
        item["boundary"] = "RANGE_LOW"
        result.append(item)
    return result


def evaluate_weekly_v2(
    core: Any,
    source: Any,
    node: Mapping[str, Any],
    *,
    structural_hash: str | None,
    case_ref: str,
    run_id: str,
) -> dict[str, Any]:
    row = core.base_result(node, structural_hash, case_ref, run_id)
    row["processing_version"] = POLICY_VERSION
    high, low = row["range_high"], row["range_low"]
    high_time = core.parse_time(row["range_high_time"])
    low_time = core.parse_time(row["range_low_time"])
    if high is None or low is None or high <= low:
        return core.finish(row, "NEEDS_REVIEW", {"INVALID_RANGE_PRICES"})
    if high_time is None or low_time is None:
        return core.finish(row, "NEEDS_REVIEW", {"MISSING_OR_INVALID_ANCHOR_TIME"})
    if high_time == low_time:
        return core.finish(row, "NEEDS_REVIEW", {"EQUAL_ANCHOR_TIMES"})

    if low_time < high_time:
        chronology, start_time, end_time = "RL_TO_RH", row["range_low_time"], row["range_high_time"]
        expected = "BOS_UP"
    else:
        chronology, start_time, end_time = "RH_TO_RL", row["range_high_time"], row["range_low_time"]
        expected = "BOS_DOWN"
    row.update({
        "chronology_result": chronology,
        "chronology_start_time": start_time,
        "chronology_end_time": end_time,
        "expected_bos_direction": expected,
    })

    aliases = _structural_aliases(core, node)
    if len(aliases) > 1:
        return core.finish(row, "NEEDS_REVIEW", {"CONFLICTING_DIRECTION_ALIASES"})

    ending_anchor = core.parse_time(end_time)
    latest_text = core.latest_candle_time(source, symbol=row["symbol"], timeframe="W1")
    latest = core.parse_time(latest_text)
    if ending_anchor is None or latest is None or latest <= ending_anchor:
        return core.finish(row, "PENDING", {"NO_W1_CANDLES_AFTER_ENDING_ANCHOR"})

    candles = core.load_candles(
        source,
        symbol=row["symbol"],
        timeframe="W1",
        start_time=str(end_time),
        end_time=str(latest_text),
    )
    candidates = [
        candle for candle in candles
        if ending_anchor < (core.parse_time(candle.time) or ending_anchor) <= latest
    ]
    row["candles_scanned"] = len(candidates)
    touches: list[dict[str, Any]] = []
    for candle in candidates:
        broke_up = candle.high > high
        broke_down = candle.low < low
        if not broke_up and not broke_down:
            touches.extend(_touches(core, candle, high, low))
            continue
        row["exact_touch_count"] = len(touches)
        row["exact_touch_examples"] = touches[:3]
        if broke_up and broke_down:
            row.update({
                "bos_candle_time": candle.time,
                "bos_candle_open": candle.open,
                "bos_candle_high": candle.high,
                "bos_candle_low": candle.low,
                "bos_candle_close": candle.close,
            })
            return core.finish(row, "NEEDS_REVIEW", {"BOTH_BOUNDARIES_BREACHED_SAME_W1"})

        direction = "BOS_UP" if broke_up else "BOS_DOWN"
        evidence = core.candle_evidence(candle, direction)
        row.update({
            "bos_boundary": high if broke_up else low,
            "bos_direction": direction,
            "reclaim_direction": "DOWN" if broke_up else "UP",
            "bos_candle_time": evidence["time"],
            "bos_candle_open": evidence["open"],
            "bos_candle_high": evidence["high"],
            "bos_candle_low": evidence["low"],
            "bos_candle_close": evidence["close"],
            "bos_evidence_price": evidence["price"],
        })
        if aliases and direction not in aliases:
            return core.finish(row, "NEEDS_REVIEW", {"DERIVED_DIRECTION_CONFLICTS_WITH_STRUCTURAL_ALIAS"})
        return core.finish(row, "COMPLETE", set())

    row["exact_touch_count"] = len(touches)
    row["exact_touch_examples"] = touches[:3]
    return core.finish(row, "PENDING", {"STRICT_BOS_NOT_PROVEN"})


def _sort_weekly_tree(core: Any, master: dict[str, Any]) -> None:
    def visit(node: dict[str, Any]) -> None:
        children = node.get("children")
        if not isinstance(children, list):
            return
        next_children = list(children)
        positions = [
            index for index, child in enumerate(next_children)
            if isinstance(child, dict)
            and str(child.get("structure_layer") or child.get("layer") or "").upper() == "WEEKLY"
        ]
        ordered = sorted((next_children[index] for index in positions), key=lambda item: _sort_key(core, item))
        for position, child in zip(positions, ordered):
            next_children[position] = child
        if positions:
            node["children"] = next_children
        for child in next_children:
            if isinstance(child, dict):
                visit(child)

    for key in ("root", "trusted_root", "review_root"):
        if isinstance(master.get(key), dict):
            visit(master[key])


def _project(core: Any, connection: Any, master: dict[str, Any], results: Sequence[Mapping[str, Any]], symbol: str) -> None:
    ordered = sorted(results, key=lambda row: _sort_key(core, row))
    by_id = {str(row["canonical_range_id"]): row for row in ordered}
    order = {str(row["canonical_range_id"]): index for index, row in enumerate(ordered)}

    def visit(node: dict[str, Any]) -> None:
        identity = str(node.get("id") or "")
        if identity in by_id:
            core.project_result_into_node(node, by_id[identity])
            node["script1_sequence_index"] = order[identity]
            node["script1_range_defined_at"] = by_id[identity].get("chronology_end_time")
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child)

    for key in ("root", "trusted_root", "review_root"):
        if isinstance(master.get(key), dict):
            visit(master[key])
    _sort_weekly_tree(core, master)
    analysis = master.setdefault("analysis", {}).setdefault("weekly_script1", {})
    analysis.update({
        "pipeline_name": "Weekly analysis",
        "processing_version": POLICY_VERSION,
        "sequence_order": "RANGE_DEFINED_AT_ASC",
        "total": len(ordered),
        "complete": sum(row.get("processing_status") == "COMPLETE" for row in ordered),
        "pending": sum(row.get("processing_status") == "PENDING" for row in ordered),
        "needs_review": sum(row.get("processing_status") == "NEEDS_REVIEW" for row in ordered),
    })
    connection.execute(
        "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
        (json.dumps(master, sort_keys=True), symbol.upper()),
    )
    for row in ordered:
        stored = connection.execute(
            "SELECT canonical_payload_json FROM master_map_ranges WHERE canonical_range_id=?",
            (row["canonical_range_id"],),
        ).fetchone()
        if stored is None:
            continue
        try:
            payload = json.loads(stored["canonical_payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        core.project_result_into_node(payload, row)
        payload["script1_sequence_index"] = order[str(row["canonical_range_id"])]
        connection.execute(
            "UPDATE master_map_ranges SET canonical_payload_json=? WHERE canonical_range_id=?",
            (json.dumps(payload, sort_keys=True), row["canonical_range_id"]),
        )


def build_weekly_chronology_bos_v2(
    core: Any,
    db_path: str | Path,
    *,
    source_db: str | Path,
    case_ref: str,
    symbol: str = "XAUUSD",
) -> dict[str, Any]:
    db = core.require_existing_db(db_path)
    symbol = str(symbol).upper()
    case_ref = str(case_ref or "").strip()
    if symbol != "XAUUSD" or not case_ref:
        raise core.WeeklyChronologyBosError("Weekly Script 1 v2 requires XAUUSD and an explicit case_ref.")
    try:
        with closing(core.open_source_market_db(source_db, required_tables=("candles",))) as source, core.connect(db) as connection:
            core.ensure_schema(connection)
            master = core.load_master_map(connection, symbol)
            structural_hash = str(master.get("structural_content_hash") or "") or None
            run_id = hashlib.sha256(core.canonical_json([
                POLICY_VERSION, SOURCE_HASH, structural_hash, case_ref, symbol
            ]).encode("utf-8")).hexdigest()
            nodes = _ordered_weeklies(core, master, case_ref)
            if not nodes:
                raise core.WeeklyChronologyBosError("Selected case contains no trusted Weekly records.")
            results = [
                evaluate_weekly_v2(
                    core, source, node, structural_hash=structural_hash,
                    case_ref=case_ref, run_id=run_id,
                )
                for node in nodes
            ]
            for row in results:
                core.insert_result(connection, row)
            _project(core, connection, master, results, symbol)
            connection.commit()
    except core.SourceMarketDbError as exc:
        raise core.WeeklyChronologyBosError(str(exc)) from exc
    ordered = sorted(results, key=lambda row: _sort_key(core, row))
    return {
        "script": POLICY_VERSION,
        "run_id": run_id,
        "symbol": symbol,
        "sequence_order": "RANGE_DEFINED_AT_ASC",
        "weekly_rows_processed": len(ordered),
        "bos_up": sum(row.get("bos_direction") == "BOS_UP" for row in ordered),
        "bos_down": sum(row.get("bos_direction") == "BOS_DOWN" for row in ordered),
        "pending": sum(row.get("processing_status") == "PENDING" for row in ordered),
        "needs_review": sum(row.get("processing_status") == "NEEDS_REVIEW" for row in ordered),
        "rows": ordered,
    }


def _outputs(core: Any, connection: Any, case_ref: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT * FROM {core.TABLE} WHERE case_ref=? AND processing_version=? "
        "ORDER BY chronology_end_time,chronology_start_time,canonical_range_id",
        (case_ref, POLICY_VERSION),
    ).fetchall()
    return [{
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
    } for row in rows]


def _run_version_v2(
    pipeline: Any,
    core: Any,
    db_path: str | Path,
    *,
    version_id: str,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    db = pipeline.require_existing_db(db_path)
    symbol = symbol.upper()
    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        version = connection.execute(
            """SELECT v.*,s.script_key FROM doctrine_script_versions v
               JOIN doctrine_scripts s USING(script_id) WHERE version_id=?""",
            (version_id,),
        ).fetchone()
        if version is None or str(version["adapter_key"]) != ADAPTER_KEY:
            raise pipeline.DoctrinePipelineError("Sequential Weekly adapter mismatch.")
        structural = str(pipeline._master_map(connection, symbol).get("structural_content_hash") or "")
        run_id = pipeline.sha([version_id, case_ref, symbol, structural])
        existing = connection.execute("SELECT * FROM doctrine_script_runs WHERE run_id=?", (run_id,)).fetchone()
        if existing is not None:
            if pipeline._approved_version(connection, version_id) and existing["publication_status"] != "PUBLISHED":
                pipeline._publish_version(connection, version_id, symbol, pipeline.now())
                connection.commit()
            return {**pipeline._run_state(connection, run_id), "reused": True}

    build_weekly_chronology_bos_v2(
        core, db, source_db=source_db, case_ref=case_ref, symbol=symbol
    )
    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        outputs = _outputs(core, connection, case_ref)
        stamp = pipeline.now()
        approved = pipeline._approved_version(connection, version_id)
        samples = [] if approved else pipeline._sample(outputs)
        version = connection.execute(
            "SELECT v.*,s.script_key FROM doctrine_script_versions v "
            "JOIN doctrine_scripts s USING(script_id) WHERE version_id=?",
            (version_id,),
        ).fetchone()
        structural = str(pipeline._master_map(connection, symbol).get("structural_content_hash") or "")
        run_id = pipeline.sha([version_id, case_ref, symbol, structural])
        connection.execute(
            """INSERT INTO doctrine_script_runs(
                 run_id,version_id,case_ref,symbol,input_structural_hash,run_status,
                 approval_status,publication_status,eligible_count,analysed_count,
                 sample_count,approval_count,executed_at,completed_at,published_at,error_text)
               VALUES (?,?,?,?,?,'COMPLETE',?,?,?,?,?,?,?,?,?,NULL)""",
            (
                run_id, version_id, case_ref, symbol, structural,
                "APPROVED" if approved else "PENDING",
                "PUBLISHED" if approved else "UNPUBLISHED",
                len(outputs), len(outputs), len(samples), 0, stamp, stamp,
                stamp if approved else None,
            ),
        )
        for row in outputs:
            connection.execute(
                "INSERT OR IGNORE INTO doctrine_range_processing VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    version_id, row["canonical_range_id"], case_ref, symbol,
                    row["input_hash"], row["output_hash"], row["processing_status"], stamp, run_id,
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO doctrine_enrichments VALUES (?,?,?,?,?,?,?)",
                (
                    version_id, row["canonical_range_id"], version["script_key"],
                    pipeline.stable_json(row["payload"]), row["output_hash"],
                    stamp if approved else None, 1 if approved else 0,
                ),
            )
        for order, row in enumerate(samples):
            connection.execute(
                "INSERT INTO doctrine_validation_samples VALUES (?,?,?,?, 'PENDING',NULL)",
                (
                    run_id, row["canonical_range_id"], order,
                    pipeline.sha([row["canonical_range_id"], row["output_hash"]]),
                ),
            )
        if approved:
            pipeline._publish_version(connection, version_id, symbol, stamp)
        connection.commit()
        return {**pipeline._run_state(connection, run_id), "reused": False}


def install(core: Any, pipeline: Any) -> None:
    """Register v2 while leaving the approved v1 adapter untouched."""
    if getattr(pipeline, "_weekly_v2_installed", False):
        return
    base_insert = pipeline.insert_script
    base_run = pipeline.run_version
    base_apply = pipeline.apply_approved_enrichments

    def insert_script(*args: Any, **kwargs: Any) -> dict[str, Any]:
        source = str(kwargs.get("source_code") or "")
        if kwargs.get("adapter_key") == pipeline.WEEKLY_ADAPTER and POLICY_VERSION in source:
            kwargs["adapter_key"] = ADAPTER_KEY
        if kwargs.get("adapter_key") != ADAPTER_KEY:
            return base_insert(*args, **kwargs)
        original = pipeline.WEEKLY_ADAPTER
        pipeline.WEEKLY_ADAPTER = ADAPTER_KEY
        try:
            return base_insert(*args, **kwargs)
        finally:
            pipeline.WEEKLY_ADAPTER = original

    def run_version(db_path: str | Path, **kwargs: Any) -> dict[str, Any]:
        with pipeline.connect(pipeline.require_existing_db(db_path)) as connection:
            pipeline.ensure_schema(connection)
            version = connection.execute(
                "SELECT adapter_key FROM doctrine_script_versions WHERE version_id=?",
                (kwargs["version_id"],),
            ).fetchone()
        if version is not None and str(version["adapter_key"]) == ADAPTER_KEY:
            return _run_version_v2(pipeline, core, db_path, **kwargs)
        return base_run(db_path, **kwargs)

    def apply_approved_enrichments(connection: Any, master: dict[str, Any], *, symbol: str) -> None:
        base_apply(connection, master, symbol=symbol)
        active = connection.execute(
            """SELECT 1 FROM doctrine_scripts s JOIN doctrine_script_versions v
               ON v.version_id=s.current_approved_version_id
               WHERE s.status='APPROVED' AND v.adapter_key=? LIMIT 1""",
            (ADAPTER_KEY,),
        ).fetchone()
        if active is None:
            return
        _sort_weekly_tree(core, master)
        state = master.setdefault("analysis", {}).setdefault("weekly_script1", {})
        state.update({
            "processing_version": POLICY_VERSION,
            "sequence_order": "RANGE_DEFINED_AT_ASC",
        })
        connection.execute(
            "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
            (json.dumps(master, sort_keys=True), symbol.upper()),
        )

    pipeline.insert_script = insert_script
    pipeline.run_version = run_version
    pipeline.apply_approved_enrichments = apply_approved_enrichments
    pipeline._weekly_v2_installed = True
