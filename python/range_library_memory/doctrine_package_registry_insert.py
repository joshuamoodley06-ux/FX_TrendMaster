"""Insertion adapter for uploaded FXTM doctrine packages."""
from __future__ import annotations

from typing import Any

from .doctrine_package_contract import (
    PACKAGE_ADAPTER,
    DoctrinePackageError,
    inspect_package,
    normalize_source,
)
from .doctrine_package_storage import persist_package


def insert_package(pipeline: Any, base_insert: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    source = normalize_source(str(kwargs.get("source_code") or ""))
    key = str(kwargs.get("script_key") or "").strip().lower().replace(" ", "_")
    label = str(kwargs.get("version_label") or "").strip()
    order = int(kwargs.get("execution_order", 100))
    db_path = args[0] if args else kwargs.get("db_path")
    if db_path is None:
        raise pipeline.DoctrinePipelineError(
            "Doctrine package insertion requires an analysis database path."
        )
    try:
        metadata = inspect_package(
            source,
            expected_script_key=key,
            expected_version_label=label,
            expected_execution_order=order,
        )
        content_hash = pipeline.sha(source)
        stored = persist_package(
            pipeline.require_existing_db(db_path),
            source=source,
            content_hash=content_hash,
            metadata=metadata,
        )
    except (DoctrinePackageError, OSError, ValueError) as exc:
        raise pipeline.DoctrinePipelineError(str(exc)) from exc

    kwargs["adapter_key"] = PACKAGE_ADAPTER
    original = pipeline.WEEKLY_ADAPTER
    pipeline.WEEKLY_ADAPTER = PACKAGE_ADAPTER
    try:
        result = base_insert(*args, **kwargs)
    finally:
        pipeline.WEEKLY_ADAPTER = original
    return {**result, **stored}
