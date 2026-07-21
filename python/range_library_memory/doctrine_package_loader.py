"""Load the exact validated doctrine source version."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from .doctrine_package_contract import (
    DoctrinePackageError, DoctrinePackageMetadata, content_sha,
)


def load_entry(path: Path, metadata: DoctrinePackageMetadata, expected_hash: str) -> Any:
    source = path.read_text(encoding="utf-8")
    if content_sha(source) != expected_hash:
        raise DoctrinePackageError("Stored package hash changed before execution.")
    name = f"_fxtm_doctrine_{metadata.script_key}_{expected_hash[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DoctrinePackageError("Could not create a doctrine package module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = {
        "FXTM_DOCTRINE_CONTRACT": getattr(module, "FXTM_DOCTRINE_CONTRACT", None),
        "SCRIPT_KEY": getattr(module, "SCRIPT_KEY", None),
        "VERSION_LABEL": getattr(module, "VERSION_LABEL", None),
        "ADAPTER_KEY": getattr(module, "ADAPTER_KEY", None),
        "EXECUTION_ORDER": getattr(module, "EXECUTION_ORDER", None),
    }
    expected = {
        "FXTM_DOCTRINE_CONTRACT": metadata.contract,
        "SCRIPT_KEY": metadata.script_key,
        "VERSION_LABEL": metadata.version_label,
        "ADAPTER_KEY": metadata.adapter_key,
        "EXECUTION_ORDER": metadata.execution_order,
    }
    if runtime != expected:
        raise DoctrinePackageError("Runtime metadata differs from validated metadata.")
    entry = getattr(module, "run", None)
    if not callable(entry):
        raise DoctrinePackageError("Doctrine package run(context) is not callable.")
    parameters = list(inspect.signature(entry).parameters.values())
    if len(parameters) != 1 or parameters[0].kind not in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }:
        raise DoctrinePackageError("run must accept exactly one context argument.")
    return entry
