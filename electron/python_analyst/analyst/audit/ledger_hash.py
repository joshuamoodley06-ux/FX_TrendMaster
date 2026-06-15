"""Raw ledger hash verification.

Mirrors the backend fingerprint contract exactly:

    event_id:created_order:is_deleted:supersedes_event_id_or_empty

joined with '|' over sequence_by_intent sorted by created_order only
(no event_id tie-breaker), all fields normalized to strings,
null supersedes becomes empty string. sha256 hex digest.
"""

from __future__ import annotations

import hashlib
from typing import Any

from analyst.audit.audit_warnings import AuditWarning


def compute_ledger_hash(sequence_by_intent: list[dict[str, Any]]) -> str:
    ordered = sorted(
        sequence_by_intent,
        key=lambda r: _order_key(r.get("created_order")),
    )
    parts = []
    for row in ordered:
        event_id = "" if row.get("event_id") is None else str(row.get("event_id"))
        created_order = "" if row.get("created_order") is None else str(row.get("created_order"))
        is_deleted = "" if row.get("is_deleted") is None else str(row.get("is_deleted"))
        supersedes = row.get("supersedes_event_id")
        supersedes_text = "" if supersedes is None else str(supersedes)
        parts.append(f"{event_id}:{created_order}:{is_deleted}:{supersedes_text}")
    fingerprint = "|".join(parts)
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _order_key(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def verify_raw_ledgers(
    raw_ledgers: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[AuditWarning]]:
    """Recompute each embedded ledger hash and compare against the export meta."""
    results: list[dict[str, Any]] = []
    warnings: list[AuditWarning] = []
    for case_ref, export in (raw_ledgers or {}).items():
        meta = export.get("meta") or {}
        expected = meta.get("ledger_hash")
        sequence = export.get("sequence_by_intent")
        if not isinstance(sequence, list):
            warnings.append(
                AuditWarning(
                    code="LEDGER_EXPORT_INCOMPLETE",
                    message="raw ledger export has no sequence_by_intent",
                    case_ref=case_ref,
                )
            )
            results.append({"case_ref": case_ref, "status": "INCOMPLETE", "expected": expected, "recomputed": None})
            continue
        recomputed = compute_ledger_hash(sequence)
        match = bool(expected) and recomputed == str(expected)
        if not match:
            warnings.append(
                AuditWarning(
                    code="LEDGER_HASH_MISMATCH",
                    message=f"recomputed ledger hash {recomputed} does not match export meta {expected}",
                    case_ref=case_ref,
                )
            )
        results.append(
            {
                "case_ref": case_ref,
                "status": "OK" if match else "MISMATCH",
                "expected": expected,
                "recomputed": recomputed,
                "event_count": len(sequence),
            }
        )
    return results, warnings
