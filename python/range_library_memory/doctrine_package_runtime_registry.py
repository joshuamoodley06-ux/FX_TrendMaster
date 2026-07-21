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
)


def _is_legacy_weekly_bootstrap(kwargs: dict[str, Any], source: str) -> bool:
    return (
        "FXTM_DOCTRINE_CONTRACT" not in source
        and str(kwargs.get("script_key") or "").strip().lower() == "weekly_structure"
        and str(kwargs.get("adapter_key") or "").strip().startswith("weekly_chronology_bos_")
    )


def _bootstrap_weekly_packages(
    pipeline: Any,
    base_insert: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    package_dir = Path(__file__).with_name("doctrine_packages")
    inserted: list[dict[str, Any]] = []
    for filename, display_name in _WEEKLY_PACKAGE_CHAIN:
        source_path = package_dir / filename
        source = source_path.read_text(encoding="utf-8")
        package_kwargs = dict(kwargs)
        package_kwargs.update({
            "source_code": source,
            "display_name": display_name,
            "adapter_key": PACKAGE_ADAPTER,
            "description": f"Bundled FXTM doctrine package: {display_name}",
        })
        inserted.append(insert_package(pipeline, base_insert, *args, **package_kwargs))

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

    def list_scripts(db_path: str | Path) -> list[dict[str, Any]]:
        """Return cockpit summaries with each script's own runs and samples."""
        rows = base_list(db_path)
        enriched: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            try:
                value["doctrine_state"] = pipeline.show_script(db_path, str(row["script_key"]))
            except pipeline.DoctrinePipelineError:
                value["doctrine_state"] = None
            enriched.append(value)
        return enriched

    pipeline.PACKAGE_ADAPTER = PACKAGE_ADAPTER
    pipeline.insert_script = insert_script
    pipeline.run_version = run_version
    pipeline.list_scripts = list_scripts
    pipeline._doctrine_package_runtime_installed = True
