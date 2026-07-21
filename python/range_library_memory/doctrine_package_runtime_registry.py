"""Install the versioned doctrine-package runtime.

Built-in adapters remain readable only for legacy workspace compatibility.
New doctrine knowledge, including Weekly BOS v1 and v2, enters Python's active
brain through ordinary package insertion, five-sample review, and approval.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctrine_package_contract import PACKAGE_ADAPTER
from .doctrine_package_registry_insert import insert_package
from .doctrine_package_registry_run import run_package_version


def install(pipeline: Any) -> None:
    if getattr(pipeline, "_doctrine_package_runtime_installed", False):
        return
    base_insert = pipeline.insert_script
    base_run = pipeline.run_version

    def insert_script(*args: Any, **kwargs: Any) -> dict[str, Any]:
        source = str(kwargs.get("source_code") or "")
        requested = kwargs.get("adapter_key") == PACKAGE_ADAPTER
        declared = "FXTM_DOCTRINE_CONTRACT" in source
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

    pipeline.PACKAGE_ADAPTER = PACKAGE_ADAPTER
    pipeline.insert_script = insert_script
    pipeline.run_version = run_version
    pipeline._doctrine_package_runtime_installed = True
