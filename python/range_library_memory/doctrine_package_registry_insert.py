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
    db_path = args[0] if args else kwargs.get("db_path")
    if db_path is None:
        raise pipeline.DoctrinePipelineError(
            "Doctrine package insertion requires an analysis database path."
        )
    try:
        metadata = inspect_package(source)
        content_hash = pipeline.sha(source)
        stored = persist_package(
            pipeline.require_existing_db(db_path),
            source=source,
            content_hash=content_hash,
            metadata=metadata,
        )
    except (DoctrinePackageError, OSError, ValueError) as exc:
        raise pipeline.DoctrinePipelineError(str(exc)) from exc

    # The selected package source is authoritative. The cockpit form is only a
    # friendly launcher and may still contain defaults from the previous script.
    kwargs["script_key"] = metadata.script_key
    kwargs["version_label"] = metadata.version_label
    kwargs["execution_order"] = metadata.execution_order
    kwargs["adapter_key"] = PACKAGE_ADAPTER

    original = pipeline.WEEKLY_ADAPTER
    pipeline.WEEKLY_ADAPTER = PACKAGE_ADAPTER
    try:
        result = base_insert(*args, **kwargs)
    finally:
        pipeline.WEEKLY_ADAPTER = original
    return {**result, **stored}
