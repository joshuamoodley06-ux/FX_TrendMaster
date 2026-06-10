from processor.core.ledger_resolver import (
    CRITICAL_ORPHAN_DELETE,
    MISSING_DELETE_TARGET,
    NON_DELETE_IS_DELETED_FLAG,
    resolve_ledger,
)


def _payload(*events: dict) -> dict:
    return {"sequence_by_intent": list(events)}


def test_simple_delete_hides_normal_event():
    result = resolve_ledger(
        _payload(
            {
                "event_id": "a",
                "created_order": 1,
                "event_type": "SET_ANCHOR",
                "is_deleted": 0,
            },
            {
                "event_id": "b",
                "created_order": 2,
                "event_type": "DELETE_RECORD",
                "supersedes_event_id": "a",
                "is_deleted": 0,
            },
        )
    )
    assert result.visible_events == []
    assert result.hidden_event_ids == ["a"]
    assert result.delete_record_count == 1
    assert result.delete_effects == {"b": "a"}


def test_delete_targeting_delete_restores_original_event():
    result = resolve_ledger(
        _payload(
            {
                "event_id": "a",
                "created_order": 1,
                "event_type": "SET_ANCHOR",
                "is_deleted": 0,
            },
            {
                "event_id": "b",
                "created_order": 2,
                "event_type": "DELETE_RECORD",
                "supersedes_event_id": "a",
                "is_deleted": 0,
            },
            {
                "event_id": "c",
                "created_order": 3,
                "event_type": "DELETE_RECORD",
                "supersedes_event_id": "b",
                "is_deleted": 0,
            },
        )
    )
    assert [event["event_id"] for event in result.visible_events] == ["a"]
    assert result.hidden_event_ids == []
    assert result.delete_effects["b"] == "a"
    assert result.delete_effects["c"] == "a"


def test_orphan_delete_produces_critical_orphan_delete_and_no_visibility_change():
    result = resolve_ledger(
        _payload(
            {
                "event_id": "a",
                "created_order": 1,
                "event_type": "SET_ANCHOR",
                "is_deleted": 0,
            },
            {
                "event_id": "b",
                "created_order": 2,
                "event_type": "DELETE_RECORD",
                "supersedes_event_id": "missing",
                "is_deleted": 0,
            },
        )
    )
    assert [event["event_id"] for event in result.visible_events] == ["a"]
    assert result.hidden_event_ids == []
    assert result.orphaned_delete_count == 1
    assert result.orphaned_delete_ids == ["b"]
    assert any(warning.code == CRITICAL_ORPHAN_DELETE for warning in result.warnings)


def test_missing_delete_target_warning():
    result = resolve_ledger(
        _payload(
            {
                "event_id": "d",
                "created_order": 1,
                "event_type": "DELETE_RECORD",
                "is_deleted": 0,
            },
        )
    )
    assert result.visible_events == []
    assert any(warning.code == MISSING_DELETE_TARGET for warning in result.warnings)


def test_non_delete_with_is_deleted_flag_warns_but_stays_visibility_controlled_by_chain():
    result = resolve_ledger(
        _payload(
            {
                "event_id": "a",
                "created_order": 1,
                "event_type": "SET_ANCHOR",
                "is_deleted": 1,
            },
            {
                "event_id": "b",
                "created_order": 2,
                "event_type": "DELETE_RECORD",
                "supersedes_event_id": "a",
                "is_deleted": 0,
            },
        )
    )
    assert [event["event_id"] for event in result.visible_events] == []
    assert result.hidden_event_ids == ["a"]
    assert any(warning.code == NON_DELETE_IS_DELETED_FLAG for warning in result.warnings)
