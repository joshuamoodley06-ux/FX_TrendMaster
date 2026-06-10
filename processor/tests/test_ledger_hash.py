import hashlib

from processor.core.ledger_hash import compute_ledger_hash, fingerprint_segment


def test_fingerprint_null_supersedes_event_id_becomes_empty_string():
    row = {
        "event_id": "evt-1",
        "created_order": 1,
        "is_deleted": 0,
        "supersedes_event_id": None,
    }
    assert fingerprint_segment(row) == "evt-1:1:0:"


def test_compute_ledger_hash_matches_backend_formula_with_null_supersedes():
    rows = [
        {
            "event_id": "aaa",
            "created_order": 2,
            "is_deleted": 0,
            "supersedes_event_id": None,
        },
        {
            "event_id": "bbb",
            "created_order": 1,
            "is_deleted": 0,
            "supersedes_event_id": "",
        },
    ]
    ordered = "bbb:1:0:|aaa:2:0:"
    expected = hashlib.sha256(ordered.encode("utf-8")).hexdigest()
    assert compute_ledger_hash(rows) == expected
