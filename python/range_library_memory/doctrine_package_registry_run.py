"""Pipeline persistence for one uploaded doctrine package version."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .doctrine_package_contract import PACKAGE_ADAPTER
from .doctrine_package_runtime import execute_package


_PACKAGE_DEPENDENCIES = {
    "weekly_reclaim": ("weekly_structure", "Weekly BOS"),
    "weekly_reclaim_depth": ("weekly_reclaim", "Weekly Reclaim"),
    "weekly_movement_classification": (
        "weekly_reclaim_depth",
        "Weekly Reclaim Depth",
    ),
    "weekly_profile_classification": (
        "weekly_reclaim_depth",
        "Weekly Reclaim Depth",
    ),
    "weekly_extreme_rejection_destination": (
        "weekly_profile_classification",
        "Weekly Profile Classification",
    ),
    "daily_mapping_coverage_audit": (
        "weekly_extreme_rejection_destination",
        "Weekly Extreme Rejection Destination",
    ),
    "weekly_daily_relationship_builder": (
        "daily_mapping_coverage_audit",
        "Daily Mapping Coverage Audit",
    ),
}


def _package_dependency_fingerprint(
    pipeline: Any,
    connection: Any,
    *,
    script_key: str,
) -> str:
    dependency = _PACKAGE_DEPENDENCIES.get(script_key)
    if dependency is None:
        return ""
    dependency_key, display_name = dependency
    row = connection.execute(
        """SELECT s.current_approved_version_id,v.adapter_key,
                  (SELECT v2.version_id FROM doctrine_script_versions v2
                   WHERE v2.script_id=s.script_id
                   ORDER BY v2.created_at DESC LIMIT 1) AS latest_version_id
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
        or str(row["current_approved_version_id"]) != str(row["latest_version_id"] or "")
    ):
        raise pipeline.DoctrinePipelineError(
            f"{script_key} requires the latest approved {display_name} package memory."
        )
    version_id = str(row["current_approved_version_id"])
    output_rows = connection.execute(
        """SELECT canonical_range_id,output_hash
           FROM doctrine_enrichments
           WHERE version_id=? AND active=1
           ORDER BY canonical_range_id""",
        (version_id,),
    ).fetchall()
    return pipeline.sha([
        dependency_key,
        version_id,
        [[str(item["canonical_range_id"]), str(item["output_hash"])] for item in output_rows],
    ])


def _review_samples(
    pipeline: Any,
    script_key: str,
    outputs: list[Mapping[str, Any]],
    limit: int = 5,
) -> list[Mapping[str, Any]]:
    """Keep doctrine edge cases visible in the five-sample review."""
    chosen: list[Mapping[str, Any]] = []

    def add(row: Mapping[str, Any]) -> None:
        if row not in chosen and len(chosen) < limit:
            chosen.append(row)

    if script_key == "weekly_structure":
        # A SAME_W1 anchor case previously approved as pending must reappear when
        # the corrected BOS package is run.
        for row in sorted(outputs, key=lambda item: str(item["canonical_range_id"])):
            if str(row.get("payload", {}).get("chronology") or "").upper() == "SAME_W1":
                add(row)
                break
    elif script_key == "weekly_reclaim":
        for wanted in (
            "RECLAIMED",
            "ABANDONED",
            "ABANDONED_THEN_RECLAIMED",
            "NEEDS_REVIEW",
            "PENDING",
        ):
            for row in sorted(outputs, key=lambda item: str(item["canonical_range_id"])):
                if str(row.get("payload", {}).get("reclaim_status") or "").upper() == wanted:
                    add(row)
                    break
    elif script_key == "weekly_reclaim_depth":
        # The five samples must expose both valid mapped range stories, not just
        # five percentages from the same anchor order.
        for wanted in (
            "OPPOSITE_THEN_CONTINUATION",
            "CONTINUATION_THEN_OPPOSITE",
            "SAME_W1",
        ):
            for row in sorted(outputs, key=lambda item: str(item["canonical_range_id"])):
                if str(row.get("payload", {}).get("range2_anchor_sequence") or "").upper() == wanted:
                    add(row)
                    break
        for wanted in (
            "NO_RETRACEMENT",
            "BOUNDARY_TOUCH",
            "RETRACED_INTO_RANGE",
            "TOUCHED_OLD_OPPOSITE",
            "EXCEEDED_OLD_OPPOSITE",
            "PENDING",
            "NEEDS_REVIEW",
        ):
            for row in sorted(outputs, key=lambda item: str(item["canonical_range_id"])):
                if str(row.get("payload", {}).get("depth_status") or "").upper() == wanted:
                    add(row)
                    break
    elif script_key == "weekly_movement_classification":
        ordered = sorted(outputs, key=lambda item: str(item["canonical_range_id"]))

        # First show a genuine alternating storyline with at least three legs.
        for row in ordered:
            if int(row.get("payload", {}).get("movement_leg_count") or 0) >= 3:
                add(row)
                break

        # Then show chapters that begin from each possible movement role.
        for first_code in ("CT", "PT"):
            for row in ordered:
                legs = row.get("payload", {}).get("movement_legs") or []
                if isinstance(legs, list) and legs and str(legs[0].get("code") or "") == first_code:
                    add(row)
                    break

        # Explicitly include a valid movement chapter whose depth is still pending.
        for row in ordered:
            if str(row.get("payload", {}).get("reclaim_depth_status") or "").upper() in {
                "PENDING",
                "MISSING",
            } and row.get("payload", {}).get("movement_path"):
                add(row)
                break

        # Finish with a normal depth-enriched chapter when one exists.
        for row in ordered:
            if str(row.get("payload", {}).get("countertrend_classification") or "").upper() in {
                "NO_RANGE1_RETRACEMENT",
                "BOUNDARY_TOUCH",
                "COUNTERTREND_RETRACEMENT",
            }:
                add(row)
                break
    elif script_key == "weekly_profile_classification":
        ordered = sorted(outputs, key=lambda item: str(item["canonical_range_id"]))

        # Show each approved trader profile where the mapped history provides it.
        for wanted in ("S&R", "S&R>FP", "S&D"):
            for row in ordered:
                if str(row.get("payload", {}).get("profile_classification") or "") == wanted:
                    add(row)
                    break

        # The continuation override must be reviewed separately from shallow depth.
        for row in ordered:
            if str(row.get("payload", {}).get("classification_basis") or "").upper() == "ABND_SAME_DIRECTION_BOS":
                add(row)
                break

        # Keep one unresolved profile visible when available rather than sampling
        # five already-obvious copies of the same threshold result.
        for row in ordered:
            if str(row.get("processing_status") or "").upper() in {"PENDING", "NEEDS_REVIEW"}:
                add(row)
                break
    elif script_key == "weekly_extreme_rejection_destination":
        ordered = sorted(outputs, key=lambda item: str(item["canonical_range_id"]))

        # Keep both sides of the range represented when the history provides them.
        for wanted_origin in ("DISCOUNT_EXTREME", "PREMIUM_EXTREME"):
            for row in ordered:
                if str(row.get("payload", {}).get("primary_origin_zone") or "").upper() == wanted_origin:
                    add(row)
                    break

        # Then show the destination ladder rather than five copies of one outcome.
        for wanted_destination in (
            "NO_FOLLOW_THROUGH",
            "FAIR_PRICE",
            "OPPOSITE_EXTREME",
            "OPPOSITE_EXTERNAL",
        ):
            for row in ordered:
                if str(row.get("payload", {}).get("primary_maximum_destination") or "").upper() == wanted_destination:
                    add(row)
                    break

        # Leave one open or ambiguous journey visible when available.
        for row in ordered:
            if str(row.get("processing_status") or "").upper() in {"PENDING", "NEEDS_REVIEW"}:
                add(row)
                break
    elif script_key == "daily_mapping_coverage_audit":
        ordered = sorted(outputs, key=lambda item: str(item["canonical_range_id"]))
        for wanted in (
            "NOT_MAPPED",
            "COMPLETE",
            "PARTIAL",
            "MAPPING_GAP",
            "INVALID_PARENT_LINK",
        ):
            for row in ordered:
                if str(row.get("payload", {}).get("coverage_status") or "").upper() == wanted:
                    add(row)
                    break
    elif script_key == "weekly_daily_relationship_builder":
        ordered = sorted(outputs, key=lambda item: str(item["canonical_range_id"]))

        # A future Daily child is the critical historical leakage guard.
        for row in ordered:
            if int(row.get("payload", {}).get("future_daily_ranges_excluded") or 0) > 0:
                add(row)
                break

        # Prefer a second, distinct multi-range Daily sequence. The future-leakage
        # sample above is often multi-range too, so stopping on it again wastes one
        # of the five review slots.
        for row in ordered:
            if row not in chosen and int(row.get("payload", {}).get("daily_relationship_count") or 0) >= 2:
                add(row)
                break

        # Keep a distinct active Daily range visible for the freeze check.
        for row in ordered:
            if row not in chosen and row.get("payload", {}).get("active_daily_range_id"):
                add(row)
                break

        # Show missing mapping and bad relationship evidence when present.
        for wanted in ("NOT_MAPPED", "MAPPING_GAP", "INVALID_PARENT_LINK"):
            for row in ordered:
                if str(row.get("payload", {}).get("coverage_status") or "").upper() == wanted:
                    add(row)
                    break

    for row in pipeline._sample(outputs, limit=limit):
        add(row)
    for row in sorted(outputs, key=lambda item: str(item["canonical_range_id"])):
        add(row)
    return chosen


def _preserved_prior_approved_run(
    pipeline: Any,
    connection: Any,
    *,
    version: Any,
    version_id: str,
    case_ref: str,
    symbol: str,
) -> dict[str, Any] | None:
    """Reuse prior approved evidence while a newer version is still a candidate."""
    if not pipeline._approved_version(connection, version_id):
        return None
    latest = connection.execute(
        """SELECT version_id FROM doctrine_script_versions
           WHERE script_id=? ORDER BY created_at DESC LIMIT 1""",
        (version["script_id"],),
    ).fetchone()
    if latest is None or str(latest["version_id"]) == version_id:
        return None
    existing = connection.execute(
        """SELECT run_id FROM doctrine_script_runs
           WHERE version_id=? AND case_ref=? AND UPPER(symbol)=?
             AND run_status='COMPLETE'
           ORDER BY completed_at DESC,executed_at DESC LIMIT 1""",
        (version_id, case_ref, symbol.upper()),
    ).fetchone()
    if existing is None:
        return None
    run_id = str(existing["run_id"])
    run = connection.execute(
        "SELECT publication_status FROM doctrine_script_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if run is not None and str(run["publication_status"] or "") != "PUBLISHED":
        pipeline._publish_version(connection, version_id, symbol, pipeline.now())
        connection.commit()
    return {
        **pipeline._run_state(connection, run_id),
        "reused": True,
        "preserved_prior_approved": True,
    }


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
        preserved = _preserved_prior_approved_run(
            pipeline,
            connection,
            version=version,
            version_id=version_id,
            case_ref=case_ref,
            symbol=symbol,
        )
        if preserved is not None:
            return preserved
        dependency_fingerprint = _package_dependency_fingerprint(
            pipeline,
            connection,
            script_key=str(version["script_key"]),
        )
        master = pipeline._master_map(connection, symbol)
        structural = str(master.get("structural_content_hash") or "")
        analysis_input_hash = pipeline.sha([
            structural,
            dependency_fingerprint,
        ]) if dependency_fingerprint else structural
        run_id = pipeline.sha([version_id, case_ref, symbol, analysis_input_hash])
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
            structural_content_hash=analysis_input_hash,
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
        samples = [] if approved else _review_samples(
            pipeline,
            str(version["script_key"]),
            outputs,
            limit=5,
        )
        stamp = pipeline.now()
        connection.execute(
            """INSERT INTO doctrine_script_runs(
                 run_id,version_id,case_ref,symbol,input_structural_hash,run_status,
                 approval_status,publication_status,eligible_count,analysed_count,
                 sample_count,approval_count,executed_at,completed_at,published_at,error_text)
               VALUES (?,?,?,?,?,'COMPLETE',?,?,?,?,?,?,?,?,?,NULL)""",
            (
                run_id, version_id, case_ref, symbol, analysis_input_hash,
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
