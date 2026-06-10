from __future__ import annotations

import hashlib
from typing import Any

from processor.models.raw_event import RawEvent


def intent_sequence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror backend export ordering: sort by created_order only."""
    return sorted(rows, key=lambda row: int(row.get("created_order") or 0))


def fingerprint_segment(row: dict[str, Any] | RawEvent) -> str:
    if isinstance(row, RawEvent):
        event_id = row.event_id
        created_order = row.created_order
        is_deleted = row.is_deleted
        supersedes_event_id = row.supersedes_event_id
    else:
        event_id = row.get("event_id")
        created_order = row.get("created_order")
        is_deleted = row.get("is_deleted")
        supersedes_event_id = row.get("supersedes_event_id")

    return (
        f"{str(event_id)}:"
        f"{str(created_order)}:"
        f"{str(is_deleted)}:"
        f"{supersedes_event_id or ''}"
    )


def compute_ledger_hash(rows: list[dict[str, Any]]) -> str:
    """Recompute ledger_hash exactly as backend/candle_store.export_raw_mapping_events."""
    ordered = intent_sequence(rows)
    fingerprint = "|".join(fingerprint_segment(row) for row in ordered)
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
