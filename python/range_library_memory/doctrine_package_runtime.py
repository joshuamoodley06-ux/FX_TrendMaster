"""Execute one exact stored FXTM doctrine package version."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .doctrine_package_context import DoctrinePackageContext
from .doctrine_package_contract import DoctrinePackageError, inspect_package, normalize_source
from .doctrine_package_loader import load_entry
from .doctrine_package_outputs import validate_outputs
from .doctrine_package_storage import persist_package


def execute_package(
    db_path: str | Path,
    *,
    source_code: str,
    content_hash: str,
    script_key: str,
    version_label: str,
    execution_order: int,
    master_map: Mapping[str, Any],
    source_db: str | Path,
    case_ref: str,
    symbol: str,
    structural_content_hash: str,
) -> list[dict[str, Any]]:
    if Path(db_path).resolve() == Path(source_db).resolve():
        raise DoctrinePackageError("Analysis and candle database paths must differ.")
    source = normalize_source(source_code)
    metadata = inspect_package(
        source,
        expected_script_key=script_key,
        expected_version_label=version_label,
        expected_execution_order=execution_order,
    )
    stored = persist_package(
        db_path,
        source=source,
        content_hash=content_hash,
        metadata=metadata,
    )
    entry = load_entry(Path(stored["package_path"]), metadata, content_hash)
    context = DoctrinePackageContext(
        master_map=master_map,
        source_db=source_db,
        case_ref=case_ref,
        symbol=symbol,
        structural_content_hash=structural_content_hash,
    )
    return validate_outputs(
        entry(context),
        context=context,
        package_hash=content_hash,
    )
