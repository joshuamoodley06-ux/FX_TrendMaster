from pathlib import Path
import re

queue_path = Path("python/range_library_memory/structure_review_queue.py")
text = queue_path.read_text(encoding="utf-8")
text = text.replace(
    "        items.extend(collect_duplicate_items(connection, now))\n",
    "        items.extend(collect_duplicate_backlog_items(connection, now))\n",
    1,
)

pattern = re.compile(
    r"def collect_duplicate_items\(connection: sqlite3\.Connection, now: str\) -> list\[dict\[str, Any\]\]:.*?\n\ndef duplicate_pair_is_current_distinct\(",
    re.S,
)
replacement = '''def collect_duplicate_backlog_items(
    connection: sqlite3.Connection,
    now: str,
) -> list[dict[str, Any]]:
    """Keep importer duplicate noise out of the trader-facing chart queue.

    The duplicate detector currently records audit candidates from signatures and
    import history. Until logical event/range identity is normalized, individual
    candidates are not trustworthy chart tasks. Preserve one reference-only backlog
    item instead of flooding the review cockpit.
    """
    row = connection.execute(
        """
        SELECT COUNT(*) AS open_count,
               SUM(CASE WHEN LOWER(candidate_type) = 'event' THEN 1 ELSE 0 END) AS event_count,
               SUM(CASE WHEN LOWER(candidate_type) = 'range' THEN 1 ELSE 0 END) AS range_count
        FROM duplicate_candidates
        WHERE review_status = 'open'
        """
    ).fetchone()
    total = int(row["open_count"] or 0)
    if total == 0:
        return []
    event_count = int(row["event_count"] or 0)
    range_count = int(row["range_count"] or 0)
    return [
        item_payload(
            review_key="duplicate-audit:backlog",
            now=now,
            actionability=REFERENCE_ONLY,
            priority=95,
            severity="LOW",
            item_type="DUPLICATE_AUDIT_BACKLOG",
            root_cause_code="DUPLICATE_LOGICAL_IDENTITY_NOT_NORMALIZED",
            source_table="duplicate_candidates",
            source_row_id=None,
            case_ref=None,
            symbol=None,
            structure_layer=None,
            source_timeframe=None,
            range_source_id=None,
            event_source_id=None,
            candidate_range_ids=[],
            reason_codes=["DUPLICATE_AUDIT_BACKLOG"],
            title="Duplicate Audit Backlog",
            trader_summary=(
                f"Importer recorded {total} open duplicate candidates "
                f"({event_count} event, {range_count} range). They are not individual "
                "chart tasks until logical event and range identity is normalized."
            ),
            suggested_action=(
                "No chart action. Resolve duplicate identity in a dedicated Python audit "
                "before surfacing individual records."
            ),
        )
    ]


def duplicate_pair_is_current_distinct('''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"Expected duplicate collector block once, found {count}")
queue_path.write_text(text, encoding="utf-8")

test_path = Path("python/range_library_memory/tests/test_structure_review_queue.py")
tests = test_path.read_text(encoding="utf-8")
old = '''def test_validation_and_duplicate_sources_join_the_same_queue(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419"), weekly_range("425")])
    insert_validation_and_duplicate(db)

    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)
    types = {item["item_type"] for item in items}

    assert result["rows_built"] == 2
    assert types == {"VALIDATION_ISSUE", "DUPLICATE_CANDIDATE"}
    duplicate = next(item for item in items if item["item_type"] == "DUPLICATE_CANDIDATE")
    assert duplicate["candidate_range_ids"] == ["419", "425"]
'''
new = '''def test_validation_and_duplicate_sources_join_the_same_queue(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419"), weekly_range("425")])
    insert_validation_and_duplicate(db)

    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)
    types = {item["item_type"] for item in items}

    assert result["rows_built"] == 2
    assert result["action_required_count"] == 1
    assert result["reference_only_count"] == 1
    assert types == {"VALIDATION_ISSUE", "DUPLICATE_AUDIT_BACKLOG"}
    backlog = next(item for item in items if item["item_type"] == "DUPLICATE_AUDIT_BACKLOG")
    assert backlog["actionability"] == REFERENCE_ONLY
    assert "1 open duplicate candidates" in backlog["trader_summary"]
'''
if old not in tests:
    raise SystemExit("Expected validation/duplicate test block was not found")
tests = tests.replace(old, new, 1)

anchor = '''def test_daily_trend_review_is_used_only_when_no_clearer_root_cause_exists(tmp_path: Path) -> None:
'''
addition = '''def test_many_duplicate_candidates_collapse_to_one_reference_backlog(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419"), weekly_range("425")])
    left = raw_range_row(db, "419")
    right = raw_range_row(db, "425")
    now = "2026-07-12T00:00:00Z"
    with sqlite3.connect(db) as connection:
        for index in range(5):
            connection.execute(
                """
                INSERT INTO duplicate_candidates(
                    import_run_id, candidate_type, left_raw_range_id,
                    right_raw_range_id, rule_code, confidence, reason,
                    created_at_utc, review_status
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    left["import_run_id"],
                    "range",
                    left["id"],
                    right["id"],
                    f"TEST_DUPLICATE_{index}",
                    "high",
                    "Synthetic duplicate audit candidate.",
                    now,
                    "open",
                ),
            )

    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)

    assert result["action_required_count"] == 0
    assert result["reference_only_count"] == 1
    assert len(items) == 1
    assert items[0]["item_type"] == "DUPLICATE_AUDIT_BACKLOG"
    assert "5 open duplicate candidates" in items[0]["trader_summary"]


'''
if anchor not in tests:
    raise SystemExit("Expected daily trend test anchor was not found")
tests = tests.replace(anchor, addition + anchor, 1)

overlap_old = '''    result = build_structure_review_queue(db)
    assert result["action_required_count"] == 0
    assert list_structure_review_queue(db) == []
'''
overlap_new = '''    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)
    assert result["action_required_count"] == 0
    assert result["reference_only_count"] == 1
    assert len(items) == 1
    assert items[0]["item_type"] == "DUPLICATE_AUDIT_BACKLOG"
'''
if overlap_old not in tests:
    raise SystemExit("Expected overlap noise assertions were not found")
tests = tests.replace(overlap_old, overlap_new, 1)

test_path.write_text(tests, encoding="utf-8")
