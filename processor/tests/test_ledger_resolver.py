from core.ledger_resolver import resolve_ledger


def test_delete_record_hides_target():
    payload = {
        "sequence_by_intent": [
            {"event_id": "a", "created_order": 1, "event_type": "SET_ANCHOR", "is_deleted": 0},
            {"event_id": "b", "created_order": 2, "event_type": "DELETE_RECORD", "supersedes_event_id": "a", "is_deleted": 0},
        ]
    }
    result = resolve_ledger(payload)
    assert result.visible_events == []
    assert "a" in result.hidden_event_ids
