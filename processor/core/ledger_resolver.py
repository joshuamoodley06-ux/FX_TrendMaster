from __future__ import annotations

from typing import Any

from processor.core.ledger_hash import intent_sequence
from processor.models.audit_result import AuditWarning, LedgerResolveResult
from processor.models.raw_event import RawEvent

DELETE_RECORD = "DELETE_RECORD"
MISSING_DELETE_TARGET = "MISSING_DELETE_TARGET"
CRITICAL_ORPHAN_DELETE = "CRITICAL_ORPHAN_DELETE"
MISSING_DELETE_EFFECT = "MISSING_DELETE_EFFECT"
NON_DELETE_IS_DELETED_FLAG = "NON_DELETE_IS_DELETED_FLAG"


def resolve_ledger(export_payload: dict[str, Any]) -> LedgerResolveResult:
    """Resolve append-only raw mapping ledger into currently visible events."""
    raw_rows = list(export_payload.get("sequence_by_intent") or [])
    ordered_rows = intent_sequence(raw_rows)
    events = [RawEvent.from_payload(row) for row in ordered_rows]

    by_id: dict[str, RawEvent] = {
        event.event_id: event for event in events if event.event_id
    }

    visibility_by_id: dict[str, bool] = {}
    delete_effects: dict[str, str] = {}
    warnings: list[AuditWarning] = []
    orphaned_delete_ids: list[str] = []
    delete_trail: list[dict[str, Any]] = []

    for event in events:
        if event.event_type == DELETE_RECORD:
            continue
        visibility_by_id[event.event_id] = True
        if event.is_deleted == 1:
            warnings.append(
                AuditWarning(
                    code=NON_DELETE_IS_DELETED_FLAG,
                    message=(
                        f"Non-delete event {event.event_id} has is_deleted=1; "
                        "visibility is controlled by DELETE_RECORD chain only"
                    ),
                    event_id=event.event_id,
                )
            )

    for event in events:
        if event.event_type != DELETE_RECORD:
            continue

        delete_trail.append(event.raw)

        if not event.supersedes_event_id:
            warnings.append(
                AuditWarning(
                    code=MISSING_DELETE_TARGET,
                    message=f"DELETE_RECORD {event.event_id} has no supersedes_event_id",
                    event_id=event.event_id,
                )
            )
            continue

        target_id = event.supersedes_event_id
        target = by_id.get(target_id)
        if target is None:
            warnings.append(
                AuditWarning(
                    code=CRITICAL_ORPHAN_DELETE,
                    message=f"DELETE_RECORD {event.event_id} targets missing event {target_id}",
                    event_id=event.event_id,
                )
            )
            orphaned_delete_ids.append(event.event_id)
            continue

        if target.event_type == DELETE_RECORD:
            original_id = delete_effects.get(target_id)
            if original_id is None:
                warnings.append(
                    AuditWarning(
                        code=MISSING_DELETE_EFFECT,
                        message=(
                            f"DELETE_RECORD {event.event_id} targets DELETE_RECORD {target_id} "
                            "with no recorded delete effect"
                        ),
                        event_id=event.event_id,
                    )
                )
                continue
        else:
            original_id = target_id

        visibility_by_id[original_id] = not visibility_by_id.get(original_id, True)
        delete_effects[event.event_id] = original_id

    visible_events = [
        event.raw
        for event in events
        if event.event_type != DELETE_RECORD and visibility_by_id.get(event.event_id, False)
    ]
    hidden_event_ids = sorted(
        event_id
        for event_id, is_visible in visibility_by_id.items()
        if not is_visible
    )

    delete_record_count = len(delete_trail)

    return LedgerResolveResult(
        visible_events=visible_events,
        delete_trail=delete_trail,
        hidden_event_ids=hidden_event_ids,
        warnings=warnings,
        delete_effects=delete_effects,
        orphaned_delete_ids=orphaned_delete_ids,
        raw_record_count=len(events),
        delete_record_count=delete_record_count,
        visible_record_count=len(visible_events),
        orphaned_delete_count=len(orphaned_delete_ids),
    )
