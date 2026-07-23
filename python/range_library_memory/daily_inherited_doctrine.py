"""Automatically apply approved Weekly doctrine to trusted Daily ranges.

The six Weekly rules were already reviewed and approved. This runtime does not
register six new Daily approval scripts. It reuses the exact Daily-resolution
ports after the approved Weekly chain runs, projects their factual outputs onto
trusted Daily nodes, and leaves raw hierarchy truth untouched.
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
INHERITED_VERSION = "weekly-approved-parity-v1"

_STAGE_SPECS: tuple[tuple[str, str, Callable[[Any], dict[str, list[dict[str, Any]]]]], ...] = (
    ("daily_structure", "weekly_structure", run_daily_bos),
    ("daily_reclaim", "weekly_reclaim", run_daily_reclaim),
    ("daily_reclaim_depth", "weekly_reclaim_depth", run_daily_reclaim_depth),
    (
        "daily_movement_classification",
        "weekly_movement_classification",
        run_daily_movement_classification,
    ),
    (
        "daily_profile_classification",
        "weekly_profile_classification",
        run_daily_profile_classification,
    ),
    (
        "daily_extreme_rejection_destination",
        "weekly_extreme_rejection_destination",
        run_daily_extreme_rejection_destination,
    ),
)

DAILY_MEMORY_KEYS = tuple(stage_key for stage_key, _, _ in _STAGE_SPECS)
WEEKLY_SOURCE_KEYS = tuple(source_key for _, source_key, _ in _STAGE_SPECS)

# Existing hierarchy rendering reads the approved Weekly display namespaces.
# These aliases are added only to Daily nodes after all calculations finish.
# They do not register scripts, alter raw mapping, or affect Weekly nodes.
_HIERARCHY_ALIASES = {
    "weekly_structure": "daily_structure",
    "weekly_reclaim": "daily_reclaim",
    "weekly_profile_classification": "daily_profile_classification",
}


def _layer(node: Mapping[str, Any]) -> str:
    return str(node.get("structure_layer") or node.get("layer") or "").upper()


def _walk(root: Any) -> list[dict[str, Any]]:
    if not isinstance(root, dict):
        return []
    rows: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = [root]
    while stack:
        node = stack.pop()
        if str(node.get("node_type") or "").upper() == "RANGE":
            rows.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in reversed(children) if isinstance(child, dict))
    return rows


def _daily_nodes(master_map: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    seen_objects: set[int] = set()
    for root_key in ("root", "trusted_root"):
        for node in _walk(master_map.get(root_key)):
            if id(node) in seen_objects or _layer(node) != "DAILY":
                continue
            seen_objects.add(id(node))
            identity = str(node.get("id") or "")
            if identity:
                result.setdefault(identity, []).append(node)
    return result


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
              JOIN doctrine_script_versions v
                ON v.version_id=s.current_approved_version_id
             WHERE s.status='APPROVED'
               AND s.script_key IN ({placeholders})""",
        WEEKLY_SOURCE_KEYS,
    ).fetchall()
    return {
        str(row["script_key"]): {
            "version_id": str(row["version_id"]),
            "version_label": str(row["version_label"]),
        }
        for row in rows
    }


def _project_stage(
    *,
    pipeline: Any,
    master_map: dict[str, Any],
    stage_key: str,
    source_key: str,
    source_version: Mapping[str, str],
    outputs: list[Mapping[str, Any]],
) -> dict[str, int]:
    nodes = _daily_nodes(master_map)
    counts = {"outputs": 0, "complete": 0, "pending": 0, "needs_review": 0}
    for raw_output in outputs:
        identity = str(raw_output.get("canonical_range_id") or "")
        copies = nodes.get(identity, [])
        if not copies:
            continue
        status = str(raw_output.get("processing_status") or "PENDING").upper()
        raw_payload = raw_output.get("payload")
        payload = dict(raw_payload) if isinstance(raw_payload, Mapping) else {}
        payload["inherited_processing_status"] = status
        payload["inherited_from_weekly_script"] = source_key
        output_hash = pipeline.sha([
            INHERITED_VERSION,
            stage_key,
            identity,
            status,
            payload,
            source_version.get("version_id"),
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
        counts["outputs"] += 1
        if status == "COMPLETE":
            counts["complete"] += 1
        elif status == "NEEDS_REVIEW":
            counts["needs_review"] += 1
        else:
            counts["pending"] += 1
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
                alias_payload = alias.get("payload")
                if isinstance(alias_payload, dict):
                    alias_payload["hierarchy_alias_of"] = daily_key
                memory[alias_key] = alias


def refresh_inherited_daily_doctrine(
    pipeline: Any,
    db_path: str | Path,
    *,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    """Rebuild Daily analytical memory from the already-approved Weekly rule set."""
    db = pipeline.require_existing_db(db_path)
    symbol_key = str(symbol).upper()
    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        master_map = pipeline._master_map(connection, symbol_key)
        _clear_inherited_daily_memory(master_map)
        approved = _approved_weekly_versions(connection)
        missing = [key for key in WEEKLY_SOURCE_KEYS if key not in approved]
        if missing:
            summary = {
                "status": "WAITING_FOR_APPROVED_WEEKLY_DOCTRINE",
                "missing_weekly_scripts": missing,
                "approval_required": False,
                "stage_counts": {},
            }
            master_map.setdefault("analysis", {})["daily_inherited_doctrine"] = summary
            connection.execute(
                "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
                (json.dumps(master_map, sort_keys=True), symbol_key),
            )
            connection.commit()
            return summary

        structural_hash = str(master_map.get("structural_content_hash") or "")
        stage_counts: dict[str, dict[str, int]] = {}
        for stage_key, source_key, runner in _STAGE_SPECS:
            context = DoctrinePackageContext(
                master_map=master_map,
                source_db=source_db,
                case_ref=case_ref,
                symbol=symbol_key,
                structural_content_hash=structural_hash,
            )
            result = runner(context)
            raw_outputs = result.get("outputs")
            outputs = [
                row for row in raw_outputs
                if isinstance(row, Mapping)
            ] if isinstance(raw_outputs, list) else []
            stage_counts[stage_key] = _project_stage(
                pipeline=pipeline,
                master_map=master_map,
                stage_key=stage_key,
                source_key=source_key,
                source_version=approved[source_key],
                outputs=outputs,
            )

        _project_hierarchy_aliases(master_map)
        summary = {
            "status": "ACTIVE",
            "version": INHERITED_VERSION,
            "adapter": INHERITED_ADAPTER,
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
    """Run inherited Daily doctrine after the normal approved pipeline."""
    if getattr(pipeline, "_daily_inherited_doctrine_installed", False):
        return
    base_run_active = pipeline.run_active_pipeline

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
        inherited = refresh_inherited_daily_doctrine(
            pipeline,
            db_path,
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        summary["daily_inherited_doctrine"] = inherited
        return summary

    pipeline.run_active_pipeline = run_active_pipeline
    pipeline._daily_inherited_doctrine_installed = True
