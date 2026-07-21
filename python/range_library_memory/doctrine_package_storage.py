"""Deterministic controlled storage for exact doctrine package source."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .doctrine_package_contract import (
    DoctrinePackageError, DoctrinePackageMetadata, content_sha, normalize_source,
)


def package_file_path(db_path: str | Path, *, script_key: str, content_hash: str) -> Path:
    db = Path(db_path).resolve()
    return db.parent / "doctrine-packages" / script_key / content_hash / "package.py"


def persist_package(
    db_path: str | Path,
    *,
    source: str,
    content_hash: str,
    metadata: DoctrinePackageMetadata,
) -> dict[str, Any]:
    normalized = normalize_source(source)
    if content_sha(normalized) != content_hash:
        raise DoctrinePackageError("Package hash does not match normalized source.")
    target = package_file_path(
        db_path, script_key=metadata.script_key, content_hash=content_hash
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("package.py.tmp")
    temp.write_text(normalized, encoding="utf-8", newline="\n")
    os.replace(temp, target)
    manifest = {
        **metadata.as_dict(),
        "content_hash": content_hash,
        "package_file": target.name,
    }
    manifest_path = target.with_name("manifest.json")
    manifest_temp = manifest_path.with_name("manifest.json.tmp")
    manifest_temp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(manifest_temp, manifest_path)
    if content_sha(target.read_text(encoding="utf-8")) != content_hash:
        raise DoctrinePackageError("Stored package failed hash verification.")
    return {
        "package_path": str(target),
        "manifest_path": str(manifest_path),
        "package_contract": metadata.contract,
    }
