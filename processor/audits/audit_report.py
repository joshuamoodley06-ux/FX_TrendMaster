from __future__ import annotations

import time
from typing import Any

from processor.models.audit_result import LedgerResolveResult

SCHEMA_VERSION = "raw_mapping_v1"


def assert_schema_version(meta: dict[str, Any]) -> None:
    schema_version = meta.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version: {schema_version!r} (expected {SCHEMA_VERSION!r})"
        )


def build_audit_report(
    export_payload: dict[str, Any],
    resolve_result: LedgerResolveResult,
    *,
    backend_ledger_hash: str,
    local_ledger_hash: str,
) -> dict[str, Any]:
    meta = export_payload.get("meta") or {}
    ledger_hash_match = backend_ledger_hash == local_ledger_hash

    return {
        "generated_at_utc_ms": int(time.time() * 1000),
        "case_id": meta.get("case_id"),
        "schema_version": meta.get("schema_version"),
        "backend_ledger_hash": backend_ledger_hash,
        "local_ledger_hash": local_ledger_hash,
        "ledger_hash_match": ledger_hash_match,
        "raw_record_count": resolve_result.raw_record_count,
        "delete_record_count": resolve_result.delete_record_count,
        "visible_record_count": resolve_result.visible_record_count,
        "hidden_event_ids": resolve_result.hidden_event_ids,
        "orphaned_delete_count": resolve_result.orphaned_delete_count,
        "orphaned_delete_ids": resolve_result.orphaned_delete_ids,
        "warnings": [warning.to_dict() for warning in resolve_result.warnings],
        "delete_trail": resolve_result.delete_trail,
        "visible_events": resolve_result.visible_events,
        "delete_effects": dict(resolve_result.delete_effects),
    }
