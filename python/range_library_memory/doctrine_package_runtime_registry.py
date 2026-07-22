"""Install the versioned doctrine-package runtime.

Built-in adapters remain readable only for legacy workspace compatibility.
New doctrine knowledge enters Python's active brain through ordinary package
insertion, five-sample review, and approval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctrine_package_contract import PACKAGE_ADAPTER
from .doctrine_package_registry_insert import insert_package
from .doctrine_package_registry_run import run_package_version


_WEEKLY_PACKAGE_CHAIN = (
    ("weekly_bos.py", "Weekly BOS"),
    ("weekly_reclaim.py", "Weekly Reclaim"),
    ("weekly_reclaim_depth.py", "Weekly Reclaim Depth"),
    ("weekly_movement_classification.py", "Weekly Movement Classification"),
    ("weekly_profile_classification.py", "Weekly Profile Classification"),
    ("weekly_extreme_rejection_destination.py", "Weekly Extreme Rejection Destination"),
)


def _is_legacy_weekly_bootstrap(kwargs: dict[str, Any], source: str) -> bool:
    return (
        "FXTM_DOCTRINE_CONTRACT" not in source
        and str(kwargs.get("script_key") or "").strip().lower() == "weekly_structure"
        and str(kwargs.get("adapter_key") or "").strip().startswith("weekly_chronology_bos_")
    )


def _ensure_bundled_weekly_packages(
    pipeline: Any,
    base_insert: Any,
    db_path: str | Path,
) -> list[dict[str, Any]]:
    """Register current bundled sources without activating or running them."""
    package_dir = Path(__file__).with_name("doctrine_packages")
    inserted: list[dict[str, Any]] = []
    for filename, display_name in _WEEKLY_PACKAGE_CHAIN:
        source = (package_dir / filename).read_text(encoding="utf-8")
        inserted.append(insert_package(
            pipeline,
            base_insert,
            db_path,
            source_code=source,
            display_name=display_name,
            script_key="bundled-package-metadata-is-authoritative",
            version_label="bundled",
            adapter_key=PACKAGE_ADAPTER,
            execution_order=0,
            description=f"Bundled FXTM doctrine package: {display_name}",
        ))
    return inserted


def _bootstrap_weekly_packages(
    pipeline: Any,
    base_insert: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    db_path = args[0] if args else kwargs.get("db_path")
    if db_path is None:
        raise pipeline.DoctrinePipelineError(
            "Weekly package bootstrap requires an analysis database path."
        )
    inserted = _ensure_bundled_weekly_packages(pipeline, base_insert, db_path)

    # The existing Electron activation expects one inserted version to run first.
    # Return Weekly BOS while also exposing the full registered chain.
    return {
        **inserted[0],
        "bootstrapped_packages": [
            {
                "script_key": item["script_key"],
                "version_id": item["version_id"],
                "version_label": item["version_label"],
            }
            for item in inserted
        ],
    }


def install(pipeline: Any) -> None:
    if getattr(pipeline, "_doctrine_package_runtime_installed", False):
        return
    base_insert = pipeline.insert_script
    base_run = pipeline.run_version
    base_review = pipeline.review_sample
    base_list = pipeline.list_scripts

    def insert_script(*args: Any, **kwargs: Any) -> dict[str, Any]:
        source = str(kwargs.get("source_code") or "")
        requested = kwargs.get("adapter_key") == PACKAGE_ADAPTER
        declared = "FXTM_DOCTRINE_CONTRACT" in source
        if _is_legacy_weekly_bootstrap(kwargs, source):
            return _bootstrap_weekly_packages(pipeline, base_insert, *args, **kwargs)
        if not requested and not declared:
            return base_insert(*args, **kwargs)
        return insert_package(pipeline, base_insert, *args, **kwargs)

    def run_version(db_path: str | Path, **kwargs: Any) -> dict[str, Any]:
        with pipeline.connect(pipeline.require_existing_db(db_path)) as connection:
            pipeline.ensure_schema(connection)
            version = connection.execute(
                "SELECT adapter_key FROM doctrine_script_versions WHERE version_id=?",
                (kwargs["version_id"],),
            ).fetchone()
        if version is not None and str(version["adapter_key"]) == PACKAGE_ADAPTER:
            return run_package_version(pipeline, db_path, **kwargs)
        return base_run(db_path, **kwargs)

    def review_sample(db_path: str | Path, **kwargs: Any) -> dict[str, Any]:
        """Keep short case reviews pending until a true five-sample run exists."""
        db = pipeline.require_existing_db(db_path)
        run_id = str(kwargs.get("run_id") or "")
        decision = str(kwargs.get("decision") or "").upper()
        canonical_range_id = str(kwargs.get("canonical_range_id") or "")
        with pipeline.connect(db) as connection:
            pipeline.ensure_schema(connection)
            run = connection.execute(
                """SELECT r.*,v.adapter_key,s.script_id,s.current_approved_version_id
                   FROM doctrine_script_runs r
                   JOIN doctrine_script_versions v USING(version_id)
                   JOIN doctrine_scripts s USING(script_id)
                   WHERE r.run_id=?""",
                (run_id,),
            ).fetchone()
        if run is None or str(run["adapter_key"]) != PACKAGE_ADAPTER or int(run["sample_count"]) >= 5:
            return base_review(db_path, **kwargs)
        if decision not in {"APPROVED", "REJECTED"}:
            raise pipeline.DoctrinePipelineError("Invalid sample decision.")

        stamp = pipeline.now()
        with pipeline.connect(db) as connection:
            pipeline.ensure_schema(connection)
            sample = connection.execute(
                "SELECT * FROM doctrine_validation_samples WHERE run_id=? AND canonical_range_id=?",
                (run_id, canonical_range_id),
            ).fetchone()
            if sample is None:
                raise pipeline.DoctrinePipelineError("Validation sample not found.")
            if sample["decision"] not in {"PENDING", decision}:
                raise pipeline.DoctrinePipelineError(
                    "Validation sample already has a different decision."
                )
            if sample["decision"] == "PENDING":
                connection.execute(
                    """UPDATE doctrine_validation_samples
                       SET decision=?,decided_at=?
                       WHERE run_id=? AND canonical_range_id=?""",
                    (decision, stamp, run_id, canonical_range_id),
                )
            decisions = [
                row[0]
                for row in connection.execute(
                    "SELECT decision FROM doctrine_validation_samples WHERE run_id=?",
                    (run_id,),
                )
            ]
            approved = decisions.count("APPROVED")
            rejected = "REJECTED" in decisions
            if rejected:
                connection.execute(
                    """UPDATE doctrine_script_runs
                       SET approval_status='REJECTED',approval_count=?
                       WHERE run_id=?""",
                    (approved, run_id),
                )
                connection.execute(
                    "UPDATE doctrine_script_versions SET rejected_at=? WHERE version_id=?",
                    (stamp, run["version_id"]),
                )
                next_status = "APPROVED" if run["current_approved_version_id"] else "REJECTED"
                connection.execute(
                    "UPDATE doctrine_scripts SET status=?,updated_at=? WHERE script_id=?",
                    (next_status, stamp, run["script_id"]),
                )
            else:
                connection.execute(
                    """UPDATE doctrine_script_runs
                       SET approval_status='PENDING',approval_count=?
                       WHERE run_id=?""",
                    (approved, run_id),
                )
            connection.commit()
            return dict(connection.execute(
                "SELECT * FROM doctrine_script_runs WHERE run_id=?",
                (run_id,),
            ).fetchone())

    def list_scripts(db_path: str | Path) -> list[dict[str, Any]]:
        """Register current bundles and return each script's own review state."""
        _ensure_bundled_weekly_packages(pipeline, base_insert, db_path)
        rows = base_list(db_path)
        enriched: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            try:
                state = pipeline.show_script(db_path, str(row["script_key"]))
                value["doctrine_state"] = state
                current_id = str(state.get("current_approved_version_id") or "")
                current = next(
                    (
                        version for version in state.get("versions", [])
                        if str(version.get("version_id") or "") == current_id
                    ),
                    None,
                )
                latest_id = str(row.get("version_id") or "")
                package_ready = bool(
                    current_id
                    and latest_id
                    and current_id == latest_id
                    and current is not None
                    and str(current.get("adapter_key") or "") == PACKAGE_ADAPTER
                )
                value["package_dependency_ready"] = package_ready
                # A legacy package or older approved package may remain available
                # for rollback, but it cannot unlock the latest package chain.
                if str(row["script_key"]) in {
                    "weekly_structure",
                    "weekly_reclaim",
                    "weekly_reclaim_depth",
                    "weekly_movement_classification",
                    "weekly_profile_classification",
                    "weekly_extreme_rejection_destination",
                } and not package_ready:
                    value["current_approved_version_id"] = None
            except pipeline.DoctrinePipelineError:
                value["doctrine_state"] = None
                value["package_dependency_ready"] = False
            enriched.append(value)
        return enriched

    pipeline.PACKAGE_ADAPTER = PACKAGE_ADAPTER
    pipeline.insert_script = insert_script
    pipeline.run_version = run_version
    pipeline.review_sample = review_sample
    pipeline.list_scripts = list_scripts
    pipeline._doctrine_package_runtime_installed = True
