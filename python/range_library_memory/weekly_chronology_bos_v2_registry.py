"""Doctrine registry compatibility for independent Weekly Script 1 versions."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .weekly_chronology_bos_v2 import (
    ADAPTER_KEY,
    POLICY_VERSION,
    install as install_v2,
)


def _candidate_results(core: Any, connection: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"SELECT * FROM {core.TABLE} WHERE processing_version=? "
        "ORDER BY chronology_end_time,chronology_start_time,canonical_range_id",
        (POLICY_VERSION,),
    ).fetchall()
    return [core.decode_stored_row(row) for row in rows]


def _canonical_sort_key(core: Any, node: Mapping[str, Any]) -> tuple[Any, ...]:
    high = core.parse_time(node.get("range_high_time"))
    low = core.parse_time(node.get("range_low_time"))
    defined = max(high, low) if high is not None and low is not None and high != low else None
    first = min(value for value in (high, low) if value is not None) if high or low else None
    return (
        0 if defined is not None else 1,
        defined.isoformat() if defined is not None else "9999",
        first.isoformat() if first is not None else "9999",
        str(node.get("id") or ""),
    )


def _project_candidate_results(core: Any, master: dict[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    """Expose pending v2 facts for validation without activating them as enrichment."""
    by_id = {str(row["canonical_range_id"]): row for row in results}
    ordered = sorted(results, key=lambda row: (
        str(row.get("chronology_end_time") or "9999"),
        str(row.get("chronology_start_time") or "9999"),
        str(row.get("canonical_range_id") or ""),
    ))
    order = {str(row["canonical_range_id"]): index for index, row in enumerate(ordered)}

    def visit(node: dict[str, Any]) -> None:
        identity = str(node.get("id") or "")
        if identity in by_id:
            core.project_result_into_node(node, by_id[identity])
            node["script1_sequence_index"] = order[identity]
            node["script1_range_defined_at"] = by_id[identity].get("chronology_end_time")
        children = [child for child in node.get("children") or [] if isinstance(child, dict)]
        weekly_positions = [
            index for index, child in enumerate(children)
            if str(child.get("structure_layer") or child.get("layer") or "").upper() == "WEEKLY"
        ]
        if len(weekly_positions) > 1:
            sorted_weeklies = sorted(
                (children[index] for index in weekly_positions),
                key=lambda child: _canonical_sort_key(core, child),
            )
            for position, child in zip(weekly_positions, sorted_weeklies):
                children[position] = child
            node["children"] = children
        for child in children:
            visit(child)

    for root_key in ("root", "trusted_root", "review_root"):
        root = master.get(root_key)
        if isinstance(root, dict):
            visit(root)
    if results:
        master.setdefault("analysis", {}).setdefault("weekly_script1_candidate", {}).update({
            "processing_version": POLICY_VERSION,
            "sequence_order": "RANGE_DEFINED_AT_ASC",
            "total": len(results),
            "complete": sum(row.get("processing_status") == "COMPLETE" for row in results),
            "pending": sum(row.get("processing_status") == "PENDING" for row in results),
            "needs_review": sum(row.get("processing_status") == "NEEDS_REVIEW" for row in results),
        })


def install(core: Any, pipeline: Any) -> None:
    """Register v2 while preserving the approved v1 execution and publication path."""
    install_v2(core, pipeline)
    if getattr(pipeline, "_weekly_v2_registry_installed", False):
        return

    base_apply_approved = pipeline.apply_approved_enrichments
    base_run_active = pipeline.run_active_pipeline

    def weekly_outputs_v1(connection: Any, case_ref: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM weekly_script1_results "
            "WHERE case_ref=? AND processing_version=? "
            "ORDER BY chronology_end_time,chronology_start_time,canonical_range_id",
            (case_ref, core.VERSION),
        ).fetchall()
        return [{
            "canonical_range_id": row["canonical_range_id"],
            "input_hash": row["source_structural_hash"] or row["result_hash"],
            "processing_status": row["processing_status"],
            "payload": {
                "chronology": row["chronology_result"],
                "bos_direction": row["bos_direction"],
                "bos_time": row["bos_candle_time"],
                "reasons": json.loads(row["reason_codes_json"]),
            },
            "output_hash": row["result_hash"],
        } for row in rows]

    def ordered_sample(rows: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
        chosen: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            payload = row["payload"]
            key = f"{payload.get('chronology')}|{payload.get('bos_direction')}|{row['processing_status']}"
            if key not in seen:
                chosen.append(row)
                seen.add(key)
            if len(chosen) == limit:
                return chosen
        for row in rows:
            if row not in chosen:
                chosen.append(row)
            if len(chosen) == limit:
                break
        return chosen

    def apply_with_candidate(connection: Any, master: dict[str, Any], *, symbol: str) -> None:
        # First publish only the exact approved version. Then overlay pending v2
        # fields as non-active validation evidence. Generic approved enrichment
        # remains untouched, so rejection safely falls back to v1.
        base_apply_approved(connection, master, symbol=symbol)
        candidate = _candidate_results(core, connection)
        if candidate:
            _project_candidate_results(core, master, candidate)
            connection.execute(
                "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
                (json.dumps(master, sort_keys=True), symbol.upper()),
            )

    def run_active_with_candidate(
        db_path: Any,
        *,
        case_ref: str,
        symbol: str,
        source_db: Any,
    ) -> dict[str, Any]:
        pending_version_id: str | None = None
        with pipeline.connect(pipeline.require_existing_db(db_path)) as connection:
            pipeline.ensure_schema(connection)
            row = connection.execute(
                """SELECT v.version_id FROM doctrine_script_versions v
                   JOIN doctrine_scripts s USING(script_id)
                   WHERE v.adapter_key=? AND v.approved_at IS NULL AND v.rejected_at IS NULL
                   ORDER BY v.created_at DESC LIMIT 1""",
                (ADAPTER_KEY,),
            ).fetchone()
            if row is not None:
                pending_version_id = str(row["version_id"])

        candidate_run = None
        if pending_version_id:
            candidate_run = pipeline.run_version(
                db_path,
                version_id=pending_version_id,
                case_ref=case_ref,
                symbol=symbol,
                source_db=source_db,
            )

        summary = base_run_active(
            db_path,
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        if candidate_run is not None:
            summary["candidate_version_id"] = pending_version_id
            summary["candidate_run_id"] = candidate_run["run"]["run_id"]
            summary["candidate_validation"] = True
        return summary

    pipeline._weekly_outputs = weekly_outputs_v1
    pipeline._sample = ordered_sample
    pipeline.apply_approved_enrichments = apply_with_candidate
    pipeline.run_active_pipeline = run_active_with_candidate
    pipeline._weekly_v2_registry_installed = True
