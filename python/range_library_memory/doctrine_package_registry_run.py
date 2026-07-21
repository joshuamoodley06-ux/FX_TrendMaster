"""Pipeline persistence for one uploaded doctrine package version."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctrine_package_contract import PACKAGE_ADAPTER
from .doctrine_package_runtime import execute_package


_PACKAGE_DEPENDENCIES = {
    "weekly_reclaim": ("weekly_structure", "Weekly BOS"),
    "weekly_reclaim_depth": ("weekly_reclaim", "Weekly Reclaim"),
}


def _require_package_dependency(
    pipeline: Any,
    connection: Any,
    *,
    script_key: str,
) -> None:
    dependency = _PACKAGE_DEPENDENCIES.get(script_key)
    if dependency is None:
        return
    dependency_key, display_name = dependency
    row = connection.execute(
        """SELECT s.current_approved_version_id,v.adapter_key
           FROM doctrine_scripts s
           LEFT JOIN doctrine_script_versions v
             ON v.version_id=s.current_approved_version_id
           WHERE s.script_key=?""",
        (dependency_key,),
    ).fetchone()
    if (
        row is None
        or not row["current_approved_version_id"]
        or str(row["adapter_key"] or "") != PACKAGE_ADAPTER
    ):
        raise pipeline.DoctrinePipelineError(
            f"{script_key} requires approved {display_name} package memory."
        )


def run_package_version(
    pipeline: Any,
    db_path: str | Path,
    *,
    version_id: str,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    db = pipeline.require_existing_db(db_path)
    symbol = str(symbol).upper()
    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        version = connection.execute(
            """SELECT v.*,s.script_key,s.execution_order
               FROM doctrine_script_versions v
               JOIN doctrine_scripts s USING(script_id)
               WHERE version_id=?""",
            (version_id,),
        ).fetchone()
        if version is None or str(version["adapter_key"]) != PACKAGE_ADAPTER:
            raise pipeline.DoctrinePipelineError("Doctrine package adapter mismatch.")
        _require_package_dependency(
            pipeline,
            connection,
            script_key=str(version["script_key"]),
        )
        master = pipeline._master_map(connection, symbol)
        structural = str(master.get("structural_content_hash") or "")
        run_id = pipeline.sha([version_id, case_ref, symbol, structural])
        existing = connection.execute(
            "SELECT * FROM doctrine_script_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if existing is not None:
            if pipeline._approved_version(connection, version_id) and existing["publication_status"] != "PUBLISHED":
                pipeline._publish_version(connection, version_id, symbol, pipeline.now())
                connection.commit()
            return {**pipeline._run_state(connection, run_id), "reused": True}

    try:
        outputs = execute_package(
            db,
            source_code=str(version["source_code"]),
            content_hash=str(version["content_hash"]),
            script_key=str(version["script_key"]),
            version_label=str(version["version_label"]),
            execution_order=int(version["execution_order"]),
            master_map=master,
            source_db=source_db,
            case_ref=case_ref,
            symbol=symbol,
            structural_content_hash=structural,
        )
    except Exception as exc:
        raise pipeline.DoctrinePipelineError(
            f"Doctrine package execution failed safely: {exc}"
        ) from exc

    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        approved = pipeline._approved_version(connection, version_id)
        # A selected case may contain fewer than five eligible Weekly ranges.
        # Run and display what exists, but package approval remains locked until
        # a separate run provides a genuine five-sample review.
        samples = [] if approved else pipeline._sample(outputs, limit=5)
        stamp = pipeline.now()
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
                len(outputs), len(outputs), len(samples), 0,
                stamp, stamp, stamp if approved else None,
            ),
        )
        for row in outputs:
            connection.execute(
                "INSERT OR IGNORE INTO doctrine_range_processing VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    version_id, row["canonical_range_id"], case_ref, symbol,
                    row["input_hash"], row["output_hash"],
                    row["processing_status"], stamp, run_id,
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
