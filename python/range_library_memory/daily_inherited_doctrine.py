"""Durable inheritance of approved Weekly doctrine onto lower timeframes.

Daily is active now. Storage and projection are layer-generic so Intraday can
reuse the same contract later without another approval cycle or another tree.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .doctrine_drafts.daily.approved_ports import (
    run_daily_bos,
    run_daily_extreme_rejection_destination,
    run_daily_movement_classification,
    run_daily_profile_classification,
    run_daily_reclaim,
    run_daily_reclaim_depth,
)
from .doctrine_package_context import DoctrinePackageContext

INHERITED_ADAPTER = "inherited_weekly_doctrine_v1"
INHERITED_VERSION = "weekly-approved-parity-v2"
INHERITED_TABLE = "inherited_doctrine_enrichments"
DAILY_TARGET_LAYER = "DAILY"

_STAGE_SPECS: tuple[tuple[str, str, Callable[[Any], dict[str, list[dict[str, Any]]]]], ...] = (
    ("daily_structure", "weekly_structure", run_daily_bos),
    ("daily_reclaim", "weekly_reclaim", run_daily_reclaim),
    ("daily_reclaim_depth", "weekly_reclaim_depth", run_daily_reclaim_depth),
    ("daily_movement_classification", "weekly_movement_classification", run_daily_movement_classification),
    ("daily_profile_classification", "weekly_profile_classification", run_daily_profile_classification),
    ("daily_extreme_rejection_destination", "weekly_extreme_rejection_destination", run_daily_extreme_rejection_destination),
)
DAILY_MEMORY_KEYS = tuple(stage for stage, _, _ in _STAGE_SPECS)
WEEKLY_SOURCE_KEYS = tuple(source for _, source, _ in _STAGE_SPECS)
_HIERARCHY_ALIASES = {
    "weekly_structure": "daily_structure",
    "weekly_reclaim": "daily_reclaim",
    "weekly_profile_classification": "daily_profile_classification",
}


def _table_exists(connection: Any) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (INHERITED_TABLE,),
    ).fetchone() is not None


def _ensure_schema(connection: Any) -> None:
    connection.execute(f"""CREATE TABLE IF NOT EXISTS {INHERITED_TABLE} (
        target_layer TEXT NOT NULL,
        target_namespace TEXT NOT NULL,
        canonical_range_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        case_ref TEXT NOT NULL,
        source_script_key TEXT NOT NULL,
        source_version_id TEXT NOT NULL,
        source_version_label TEXT NOT NULL,
        adapter_key TEXT NOT NULL,
        processing_status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        output_hash TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(target_layer,target_namespace,canonical_range_id,symbol,case_ref)
    )""")
    connection.execute(f"""CREATE INDEX IF NOT EXISTS idx_{INHERITED_TABLE}_scope
        ON {INHERITED_TABLE}(symbol,target_layer,case_ref,active)""")


def _layer(node: Mapping[str, Any]) -> str:
    return str(node.get("structure_layer") or node.get("layer") or "").upper()


def _walk(root: Any) -> list[dict[str, Any]]:
    if not isinstance(root, dict):
        return []
    result: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if str(node.get("node_type") or "").upper() == "RANGE":
            result.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in reversed(children) if isinstance(child, dict))
    return result


def _layer_nodes(master_map: Mapping[str, Any], target_layer: str) -> dict[str, list[dict[str, Any]]]:
    wanted = str(target_layer).upper()
    result: dict[str, list[dict[str, Any]]] = {}
    seen: set[int] = set()
    for root_key in ("root", "trusted_root", "review_root"):
        for node in _walk(master_map.get(root_key)):
            if id(node) in seen or _layer(node) != wanted:
                continue
            seen.add(id(node))
            identity = str(node.get("id") or "")
            if identity:
                result.setdefault(identity, []).append(node)
    return result


def _daily_nodes(master_map: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return _layer_nodes(master_map, DAILY_TARGET_LAYER)


def _node_cases(node: Mapping[str, Any]) -> set[str]:
    refs = node.get("source_refs")
    if not isinstance(refs, list):
        return set()
    return {
        str(ref.get("case_ref") or "")
        for ref in refs
        if isinstance(ref, Mapping) and str(ref.get("case_ref") or "")
    }


def _clear_inherited_daily_memory(master_map: Mapping[str, Any]) -> None:
    removable = set(DAILY_MEMORY_KEYS) | set(_HIERARCHY_ALIASES)
    for copies in _daily_nodes(master_map).values():
        for node in copies:
            memory = node.get("analysis_enrichments")
            if not isinstance(memory, dict):
                continue
            for key in removable:
                memory.pop(key, None)
            if not memory:
                node.pop("analysis_enrichments", None)


def _approved_weekly_versions(connection: Any) -> dict[str, dict[str, str]]:
    placeholders = ",".join("?" for _ in WEEKLY_SOURCE_KEYS)
    rows = connection.execute(
        f"""SELECT s.script_key,v.version_id,v.version_label
              FROM doctrine_scripts s
              JOIN doctrine_script_versions v ON v.version_id=s.current_approved_version_id
             WHERE s.status='APPROVED' AND s.script_key IN ({placeholders})""",
        WEEKLY_SOURCE_KEYS,
    ).fetchall()
    return {
        str(row["script_key"]): {
            "version_id": str(row["version_id"]),
            "version_label": str(row["version_label"]),
        }
        for row in rows
    }


def _delete_scope(
    connection: Any,
    *,
    target_layer: str,
    symbol: str,
    case_ref: str,
    namespace: str | None = None,
) -> None:
    _ensure_schema(connection)
    sql = f"DELETE FROM {INHERITED_TABLE} WHERE target_layer=? AND UPPER(symbol)=? AND case_ref=?"
    params: list[Any] = [str(target_layer).upper(), str(symbol).upper(), str(case_ref)]
    if namespace:
        sql += " AND target_namespace=?"
        params.append(str(namespace))
    connection.execute(sql, params)


def _persist(
    connection: Any,
    *,
    pipeline: Any,
    target_layer: str,
    namespace: str,
    identity: str,
    symbol: str,
    case_ref: str,
    source_key: str,
    source_version: Mapping[str, str],
    status: str,
    payload: Mapping[str, Any],
    output_hash: str,
) -> None:
    _ensure_schema(connection)
    connection.execute(
        f"""INSERT OR REPLACE INTO {INHERITED_TABLE} (
            target_layer,target_namespace,canonical_range_id,symbol,case_ref,
            source_script_key,source_version_id,source_version_label,adapter_key,
            processing_status,payload_json,output_hash,active,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
        (
            str(target_layer).upper(), namespace, identity, str(symbol).upper(), str(case_ref),
            source_key, str(source_version.get("version_id") or ""),
            str(source_version.get("version_label") or ""), INHERITED_ADAPTER,
            status, pipeline.stable_json(dict(payload)), output_hash, pipeline.now(),
        ),
    )


def _project_stage(
    *,
    pipeline: Any,
    master_map: dict[str, Any],
    stage_key: str,
    source_key: str,
    source_version: Mapping[str, str],
    outputs: list[Mapping[str, Any]],
    connection: Any | None = None,
    symbol: str = "XAUUSD",
    case_ref: str = "",
    target_layer: str = DAILY_TARGET_LAYER,
) -> dict[str, int]:
    nodes = _layer_nodes(master_map, target_layer)
    counts = {"outputs": 0, "complete": 0, "pending": 0, "needs_review": 0}
    if connection is not None:
        _delete_scope(
            connection,
            target_layer=target_layer,
            symbol=symbol,
            case_ref=case_ref,
            namespace=stage_key,
        )
    for output in outputs:
        identity = str(output.get("canonical_range_id") or "")
        copies = nodes.get(identity, [])
        if not copies:
            continue
        status = str(output.get("processing_status") or "PENDING").upper()
        raw_payload = output.get("payload")
        payload = dict(raw_payload) if isinstance(raw_payload, Mapping) else {}
        payload.update({
            "inherited_processing_status": status,
            "inherited_from_weekly_script": source_key,
            "inherited_target_layer": str(target_layer).upper(),
        })
        output_hash = pipeline.sha([
            INHERITED_VERSION, target_layer, stage_key, identity, status,
            payload, source_version.get("version_id"),
        ])
        entry = {
            "version_id": f"inherited:{source_version.get('version_id')}",
            "version_label": str(source_version.get("version_label") or ""),
            "adapter_key": INHERITED_ADAPTER,
            "output_hash": output_hash,
            "processing_status": status,
            "payload": payload,
        }
        for node in copies:
            node.setdefault("analysis_enrichments", {})[stage_key] = json.loads(
                pipeline.stable_json(entry)
            )
        if connection is not None:
            _persist(
                connection,
                pipeline=pipeline,
                target_layer=target_layer,
                namespace=stage_key,
                identity=identity,
                symbol=symbol,
                case_ref=case_ref,
                source_key=source_key,
                source_version=source_version,
                status=status,
                payload=payload,
                output_hash=output_hash,
            )
        counts["outputs"] += 1
        counts["complete" if status == "COMPLETE" else "needs_review" if status == "NEEDS_REVIEW" else "pending"] += 1
    return counts


def _project_hierarchy_aliases(master_map: dict[str, Any]) -> None:
    for copies in _daily_nodes(master_map).values():
        for node in copies:
            memory = node.get("analysis_enrichments")
            if not isinstance(memory, dict):
                continue
            for alias_key, daily_key in _HIERARCHY_ALIASES.items():
                source = memory.get(daily_key)
                if not isinstance(source, Mapping):
                    continue
                alias = json.loads(json.dumps(source))
                alias["adapter_key"] = f"{INHERITED_ADAPTER}:hierarchy"
                if isinstance(alias.get("payload"), dict):
                    alias["payload"]["hierarchy_alias_of"] = daily_key
                memory[alias_key] = alias


def apply_persisted_inherited_enrichments(
    connection: Any,
    master_map: dict[str, Any],
    *,
    symbol: str,
) -> dict[str, int]:
    """Reapply durable lower-timeframe memory after any Master Map rebuild."""
    if not _table_exists(connection):
        return {"applied": 0, "needs_review": 0}
    rows = connection.execute(
        f"""SELECT * FROM {INHERITED_TABLE}
             WHERE UPPER(symbol)=? AND active=1
             ORDER BY target_layer,target_namespace,canonical_range_id,case_ref""",
        (str(symbol).upper(),),
    ).fetchall()
    managed: dict[str, set[str]] = {}
    for row in rows:
        managed.setdefault(str(row["target_layer"]).upper(), set()).add(str(row["target_namespace"]))
    for layer, namespaces in managed.items():
        for copies in _layer_nodes(master_map, layer).values():
            for node in copies:
                memory = node.get("analysis_enrichments")
                if not isinstance(memory, dict):
                    continue
                for namespace in namespaces:
                    memory.pop(namespace, None)
                if layer == DAILY_TARGET_LAYER:
                    for alias in _HIERARCHY_ALIASES:
                        memory.pop(alias, None)
                if not memory:
                    node.pop("analysis_enrichments", None)

    applied = 0
    needs_review = 0
    for row in rows:
        layer = str(row["target_layer"]).upper()
        identity = str(row["canonical_range_id"])
        for node in _layer_nodes(master_map, layer).get(identity, []):
            case_ref = str(row["case_ref"] or "")
            node_cases = _node_cases(node)
            if case_ref and node_cases and case_ref not in node_cases:
                continue
            status = str(row["processing_status"] or "PENDING").upper()
            node.setdefault("analysis_enrichments", {})[str(row["target_namespace"])] = {
                "version_id": f"inherited:{row['source_version_id']}",
                "version_label": str(row["source_version_label"] or ""),
                "adapter_key": str(row["adapter_key"] or INHERITED_ADAPTER),
                "output_hash": str(row["output_hash"] or ""),
                "processing_status": status,
                "payload": json.loads(str(row["payload_json"] or "{}")),
            }
            applied += 1
            needs_review += int(status == "NEEDS_REVIEW")
    _project_hierarchy_aliases(master_map)
    summary = {"applied": applied, "needs_review": needs_review}
    master_map.setdefault("analysis", {})["inherited_lower_timeframe_projection"] = summary
    connection.execute(
        "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
        (json.dumps(master_map, sort_keys=True), str(symbol).upper()),
    )
    return summary


def refresh_inherited_daily_doctrine(
    pipeline: Any,
    db_path: str | Path,
    *,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    db = pipeline.require_existing_db(db_path)
    symbol_key = str(symbol).upper()
    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        _ensure_schema(connection)
        master_map = pipeline._master_map(connection, symbol_key)
        _clear_inherited_daily_memory(master_map)
        approved = _approved_weekly_versions(connection)
        missing = [key for key in WEEKLY_SOURCE_KEYS if key not in approved]
        if missing:
            _delete_scope(
                connection,
                target_layer=DAILY_TARGET_LAYER,
                symbol=symbol_key,
                case_ref=case_ref,
            )
            summary = {
                "status": "WAITING_FOR_APPROVED_WEEKLY_DOCTRINE",
                "missing_weekly_scripts": missing,
                "approval_required": False,
                "stage_counts": {},
            }
        else:
            structural_hash = str(master_map.get("structural_content_hash") or "")
            stage_counts: dict[str, dict[str, int]] = {}
            for stage_key, source_key, runner in _STAGE_SPECS:
                result = runner(DoctrinePackageContext(
                    master_map=master_map,
                    source_db=source_db,
                    case_ref=case_ref,
                    symbol=symbol_key,
                    structural_content_hash=structural_hash,
                ))
                raw_outputs = result.get("outputs")
                outputs = [row for row in raw_outputs if isinstance(row, Mapping)] if isinstance(raw_outputs, list) else []
                stage_counts[stage_key] = _project_stage(
                    pipeline=pipeline,
                    master_map=master_map,
                    stage_key=stage_key,
                    source_key=source_key,
                    source_version=approved[source_key],
                    outputs=outputs,
                    connection=connection,
                    symbol=symbol_key,
                    case_ref=case_ref,
                )
            _project_hierarchy_aliases(master_map)
            summary = {
                "status": "ACTIVE",
                "version": INHERITED_VERSION,
                "adapter": INHERITED_ADAPTER,
                "target_layer": DAILY_TARGET_LAYER,
                "approval_required": False,
                "source_weekly_versions": approved,
                "stage_counts": stage_counts,
                "daily_outputs": sum(item["outputs"] for item in stage_counts.values()),
                "refreshed_at": pipeline.now(),
            }
        master_map.setdefault("analysis", {})["daily_inherited_doctrine"] = summary
        connection.execute(
            "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
            (json.dumps(master_map, sort_keys=True), symbol_key),
        )
        connection.commit()
        return summary


def install(pipeline: Any) -> None:
    if getattr(pipeline, "_daily_inherited_doctrine_installed", False):
        return
    base_run_active = pipeline.run_active_pipeline
    base_apply_approved = pipeline.apply_approved_enrichments

    def apply_approved_enrichments(
        connection: Any,
        master_map: dict[str, Any],
        *,
        symbol: str,
    ) -> None:
        base_apply_approved(connection, master_map, symbol=symbol)
        apply_persisted_inherited_enrichments(connection, master_map, symbol=symbol)

    def run_active_pipeline(
        db_path: str | Path,
        *,
        case_ref: str,
        symbol: str,
        source_db: str | Path,
    ) -> dict[str, Any]:
        summary = base_run_active(
            db_path,
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        summary["daily_inherited_doctrine"] = refresh_inherited_daily_doctrine(
            pipeline,
            db_path,
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        return summary

    pipeline.apply_approved_enrichments = apply_approved_enrichments
    pipeline.run_active_pipeline = run_active_pipeline
    pipeline._daily_inherited_doctrine_installed = True
