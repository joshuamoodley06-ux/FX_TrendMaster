"""Pipeline persistence for one uploaded doctrine package version."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctrine_package_contract import PACKAGE_ADAPTER, DoctrinePackageError
from .doctrine_package_runtime import execute_package


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
    except (DoctrinePackageError, OSError, ValueError) as exc:
        raise pipeline.DoctrinePipelineError(str(exc)) from exc

    with pipeline.connect(db) as connection:
        pipeline.ensure_schema(connection)
        approved = pipeline._approved_version(connection, version_id)
        if not approved and len(outputs) < 5:
            raise pipeline.DoctrinePipelineError(
                "A pending doctrine package must produce at least five eligible outputs."
            )
        samples = [] if approved else pipeline._sample(outputs, limit=5)
        if not approved and len(samples) != 5:
            raise pipeline.DoctrinePipelineError(
                "Doctrine package validation requires exactly five samples."
            )
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
