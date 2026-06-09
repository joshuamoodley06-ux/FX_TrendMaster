from __future__ import annotations

from typing import Any
from models.audit_result import LedgerResolveResult


def resolve_ledger(export_payload: dict[str, Any]) -> LedgerResolveResult:
    """Resolve append-only raw mapping ledger into currently visible events.

    First version intentionally handles the core rule only:
    DELETE_RECORD hides its supersedes_event_id target. Later versions should
    support delete-of-delete undo chains and adjustment chains with full audit output.
    """
    events = list(export_payload.get("sequence_by_intent") or [])
    events.sort(key=lambda row: int(row.get("created_order") or 0))

    hidden: set[str] = set()
    warnings: list[str] = []

    by_id = {str(row.get("event_id")): row for row in events if row.get("event_id")}

    for row in events:
        if row.get("event_type") == "DELETE_RECORD":
            target = row.get("supersedes_event_id")
            if not target:
                warnings.append(f"DELETE_RECORD {row.get('event_id')} has no supersedes_event_id")
                continue
            if target not in by_id:
                warnings.append(f"DELETE_RECORD {row.get('event_id')} targets missing event {target}")
                continue
            hidden.add(str(target))

    visible = [
        row for row in events
        if row.get("event_type") != "DELETE_RECORD"
        and str(row.get("event_id")) not in hidden
        and int(row.get("is_deleted") or 0) == 0
    ]

    return LedgerResolveResult(visible_events=visible, hidden_event_ids=hidden, warnings=warnings)
