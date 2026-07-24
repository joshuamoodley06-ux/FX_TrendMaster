"""Literal contract for uploaded FXTM doctrine packages."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

PACKAGE_ADAPTER = "doctrine_package_v1"
PACKAGE_CONTRACT = "fxtm_doctrine_package_v1"
CONTEXT_CONTRACT = "fxtm_doctrine_context_v1"
ALLOWED_PROCESSING_STATUSES = frozenset({"COMPLETE", "PENDING", "NEEDS_REVIEW"})
_SCRIPT_KEY = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_REQUIRED = {
    "FXTM_DOCTRINE_CONTRACT", "SCRIPT_KEY", "VERSION_LABEL",
    "ADAPTER_KEY", "EXECUTION_ORDER",
}


class DoctrinePackageError(RuntimeError):
    """Raised when a doctrine package violates its runtime contract."""


@dataclass(frozen=True)
class DoctrinePackageMetadata:
    contract: str
    script_key: str
    version_label: str
    adapter_key: str
    execution_order: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "script_key": self.script_key,
            "version_label": self.version_label,
            "adapter_key": self.adapter_key,
            "execution_order": self.execution_order,
        }


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_sha(value: str | Any) -> str:
    raw = value if isinstance(value, str) else stable_json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_source(source: str) -> str:
    text = str(source).replace("\r\n", "\n").replace("\r", "\n").strip()
    return "\n".join(line.rstrip() for line in text.split("\n")) + "\n"


def _literal_metadata(source: str) -> tuple[dict[str, Any], set[str]]:
    try:
        tree = ast.parse(source, filename="<fxtm-doctrine-package>")
    except SyntaxError as exc:
        raise DoctrinePackageError(
            f"Doctrine package syntax is invalid: {exc.msg} (line {exc.lineno})."
        ) from exc
    values: dict[str, Any] = {}
    functions: set[str] = set()
    duplicates: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
            continue
        target = None
        value_node = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value_node = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value_node = node.target, node.value
        if target is None or value_node is None or target.id not in _REQUIRED:
            continue
        if target.id in values:
            duplicates.add(target.id)
            continue
        try:
            values[target.id] = ast.literal_eval(value_node)
        except (TypeError, ValueError) as exc:
            raise DoctrinePackageError(
                f"Doctrine package constant {target.id} must be literal."
            ) from exc
    if duplicates:
        raise DoctrinePackageError(
            "Doctrine package metadata constants may appear only once: "
            + ", ".join(sorted(duplicates))
        )
    missing = sorted(_REQUIRED.difference(values))
    if missing:
        raise DoctrinePackageError(
            "Doctrine package metadata is missing: " + ", ".join(missing)
        )
    return values, functions


def inspect_package(
    source: str,
    *,
    expected_script_key: str | None = None,
    expected_version_label: str | None = None,
    expected_execution_order: int | None = None,
) -> DoctrinePackageMetadata:
    """Validate metadata without executing uploaded source."""
    values, functions = _literal_metadata(normalize_source(source))
    if "run" not in functions:
        raise DoctrinePackageError("Doctrine package must define run(context).")
    contract = str(values["FXTM_DOCTRINE_CONTRACT"] or "").strip()
    key = str(values["SCRIPT_KEY"] or "").strip().lower()
    label = str(values["VERSION_LABEL"] or "").strip()
    adapter = str(values["ADAPTER_KEY"] or "").strip()
    order = values["EXECUTION_ORDER"]
    if contract != PACKAGE_CONTRACT:
        raise DoctrinePackageError(f"Expected package contract {PACKAGE_CONTRACT}.")
    if not _SCRIPT_KEY.fullmatch(key):
        raise DoctrinePackageError("SCRIPT_KEY must be 2-64 lower-case key characters.")
    if not label or len(label) > 64:
        raise DoctrinePackageError("VERSION_LABEL must be 1-64 characters long.")
    if adapter != PACKAGE_ADAPTER:
        raise DoctrinePackageError(f"ADAPTER_KEY must be {PACKAGE_ADAPTER}.")
    if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order <= 10_000:
        raise DoctrinePackageError("EXECUTION_ORDER must be an integer from 0 to 10000.")
    metadata = DoctrinePackageMetadata(contract, key, label, adapter, order)
    expected = {
        "SCRIPT_KEY": (expected_script_key.lower() if expected_script_key else None, key),
        "VERSION_LABEL": (expected_version_label, label),
        "EXECUTION_ORDER": (expected_execution_order, order),
    }
    mismatches = [
        f"{name} package={actual!r} form={wanted!r}"
        for name, (wanted, actual) in expected.items()
        if wanted is not None and wanted != actual
    ]
    if mismatches:
        raise DoctrinePackageError(
            "Doctrine package metadata does not match the insertion form: "
            + "; ".join(mismatches)
        )
    return metadata
