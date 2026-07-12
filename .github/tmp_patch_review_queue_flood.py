from pathlib import Path
import re

queue_path = Path("python/range_library_memory/structure_review_queue.py")
text = queue_path.read_text(encoding="utf-8")

validation_block = r'''def collect_validation_items(connection: sqlite3.Connection, now: str) -> list[dict[str, Any]]:
    """Surface only current error-level validation faults.

    Import warnings remain available in validation_issues for audit, but they do not
    become chart tasks. Repeated imports of the same raw record collapse to one
    current root cause.
    """
    rows = connection.execute(
        """
        SELECT issue.*
        FROM validation_issues AS issue
        WHERE issue.resolved_at_utc IS NULL
          AND issue.id = (
              SELECT MAX(candidate.id)
              FROM validation_issues AS candidate
              WHERE candidate.resolved_at_utc IS NULL
                AND COALESCE(candidate.raw_range_id, -1) = COALESCE(issue.raw_range_id, -1)
                AND COALESCE(candidate.raw_event_id, -1) = COALESCE(issue.raw_event_id, -1)
                AND candidate.issue_code = issue.issue_code
          )
        ORDER BY issue.id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        severity = normalize_severity(row["severity"])
        if severity not in {"CRITICAL", "HIGH"}:
            continue
        if not validation_issue_is_current(connection, row):
            continue

        ref = raw_reference(
            connection,
            raw_range_id=row["raw_range_id"],
            raw_event_id=row["raw_event_id"],
        )
        subject_key = (
            ref.get("event_source_id")
            or ref.get("range_source_id")
            or f"raw-range-{row['raw_range_id']}"
            if row["raw_range_id"] is not None
            else f"raw-event-{row['raw_event_id']}"
        )
        items.append(
            item_payload(
                review_key=f"validation:{row['issue_code']}:{subject_key}",
                now=now,
                actionability=ACTION_REQUIRED,
                priority=8,
                severity=severity,
                item_type="VALIDATION_ISSUE",
                root_cause_code=str(row["issue_code"]),
                source_table="validation_issues",
                source_row_id=row["id"],
                case_ref=ref.get("case_ref"),
                symbol=ref.get("symbol"),
                structure_layer=ref.get("structure_layer"),
                source_timeframe=ref.get("source_timeframe"),
                range_source_id=ref.get("range_source_id"),
                event_source_id=ref.get("event_source_id"),
                candidate_range_ids=[],
                reason_codes=[str(row["issue_code"])],
                chart_time=ref.get("event_time") or ref.get("range_time"),
                chart_start_time=ref.get("range_start_time"),
                chart_end_time=ref.get("range_end_time"),
                title=f"Validation: {str(row['issue_code']).replace('_', ' ').title()}",
                trader_summary=str(row["message"]),
                suggested_action="Open the linked range or event and correct the invalid structural fact.",
            )
        )
    return items


def validation_issue_is_current(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> bool:
    if row["raw_range_id"] is not None and not raw_record_is_latest(
        connection, "raw_ranges", int(row["raw_range_id"])
    ):
        return False
    if row["raw_event_id"] is not None and not raw_record_is_latest(
        connection, "raw_events", int(row["raw_event_id"])
    ):
        return False
    return True
'''

text, count = re.subn(
    r"def collect_validation_items\(.*?\n\n\ndef collect_duplicate_items",
    validation_block + "\n\ndef collect_duplicate_items",
    text,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"Expected one validation collector block, replaced {count}")

duplicate_block = r'''def collect_duplicate_items(connection: sqlite3.Connection, now: str) -> list[dict[str, Any]]:
    """Surface only current, distinct, high-confidence duplicate records.

    Low-confidence overlapping windows and successive versions of the same source id
    remain audit evidence. They are not actionable chart tasks.
    """
    rows = connection.execute(
        """
        SELECT candidate.*
        FROM duplicate_candidates AS candidate
        WHERE candidate.review_status = 'open'
          AND LOWER(candidate.confidence) IN ('exact', 'high')
          AND candidate.rule_code IN ('same_range_window', 'same_event_signature')
          AND candidate.id = (
              SELECT MAX(newer.id)
              FROM duplicate_candidates AS newer
              WHERE newer.review_status = 'open'
                AND newer.rule_code = candidate.rule_code
                AND COALESCE(newer.left_raw_range_id, -1) = COALESCE(candidate.left_raw_range_id, -1)
                AND COALESCE(newer.right_raw_range_id, -1) = COALESCE(candidate.right_raw_range_id, -1)
                AND COALESCE(newer.left_raw_event_id, -1) = COALESCE(candidate.left_raw_event_id, -1)
                AND COALESCE(newer.right_raw_event_id, -1) = COALESCE(candidate.right_raw_event_id, -1)
          )
        ORDER BY candidate.id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not duplicate_pair_is_current_distinct(connection, row):
            continue

        left = raw_reference(
            connection,
            raw_range_id=row["left_raw_range_id"],
            raw_event_id=row["left_raw_event_id"],
        )
        right = raw_reference(
            connection,
            raw_range_id=row["right_raw_range_id"],
            raw_event_id=row["right_raw_event_id"],
        )
        candidate_ranges = [
            value
            for value in (left.get("range_source_id"), right.get("range_source_id"))
            if value
        ]
        logical_ids = sorted(
            {
                str(value)
                for value in (
                    left.get("range_source_id") or left.get("event_source_id"),
                    right.get("range_source_id") or right.get("event_source_id"),
                )
                if value
            },
            key=source_sort_key,
        )
        logical_key = ":".join(logical_ids) or str(row["id"])
        items.append(
            item_payload(
                review_key=(
                    f"duplicate:{str(row['candidate_type']).lower()}:"
                    f"{row['rule_code']}:{logical_key}"
                ),
                now=now,
                actionability=ACTION_REQUIRED,
                priority=18,
                severity="HIGH",
                item_type="DUPLICATE_CANDIDATE",
                root_cause_code=str(row["rule_code"]),
                source_table="duplicate_candidates",
                source_row_id=row["id"],
                case_ref=left.get("case_ref") or right.get("case_ref"),
                symbol=left.get("symbol") or right.get("symbol"),
                structure_layer=left.get("structure_layer") or right.get("structure_layer"),
                source_timeframe=left.get("source_timeframe") or right.get("source_timeframe"),
                range_source_id=left.get("range_source_id") or right.get("range_source_id"),
                event_source_id=left.get("event_source_id") or right.get("event_source_id"),
                candidate_range_ids=candidate_ranges,
                reason_codes=[str(row["rule_code"])],
                chart_time=left.get("event_time") or right.get("event_time"),
                chart_start_time=left.get("range_start_time") or right.get("range_start_time"),
                chart_end_time=left.get("range_end_time") or right.get("range_end_time"),
                title=f"Possible Duplicate: {str(row['candidate_type']).replace('_', ' ').title()}",
                trader_summary=str(row["reason"]),
                suggested_action="Compare both current mapped records and mark duplicate or not duplicate.",
            )
        )
    return items


def duplicate_pair_is_current_distinct(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> bool:
    candidate_type = str(row["candidate_type"] or "").lower()
    if candidate_type == "range":
        table = "raw_ranges"
        left_id = row["left_raw_range_id"]
        right_id = row["right_raw_range_id"]
    elif candidate_type == "event":
        table = "raw_events"
        left_id = row["left_raw_event_id"]
        right_id = row["right_raw_event_id"]
    else:
        return False

    if left_id is None or right_id is None:
        return False
    if not raw_record_is_latest(connection, table, int(left_id)):
        return False
    if not raw_record_is_latest(connection, table, int(right_id)):
        return False

    source_rows = connection.execute(
        f"SELECT id, source_record_id FROM {table} WHERE id IN (?, ?)",
        (int(left_id), int(right_id)),
    ).fetchall()
    if len(source_rows) != 2:
        return False
    source_ids = [row_value["source_record_id"] for row_value in source_rows]
    if any(value in (None, "") for value in source_ids):
        return False
    return str(source_ids[0]) != str(source_ids[1])


def raw_record_is_latest(
    connection: sqlite3.Connection,
    table: str,
    raw_id: int,
) -> bool:
    if table not in {"raw_ranges", "raw_events"}:
        raise ValueError(f"Unsupported raw table: {table}")
    row = connection.execute(
        f"SELECT source_record_id FROM {table} WHERE id = ?",
        (raw_id,),
    ).fetchone()
    if row is None:
        return False
    source_id = row["source_record_id"]
    if source_id in (None, ""):
        return True
    latest = connection.execute(
        f"SELECT MAX(id) FROM {table} WHERE source_record_id = ?",
        (source_id,),
    ).fetchone()[0]
    return int(latest) == raw_id
'''

text, count = re.subn(
    r"def collect_duplicate_items\(.*?\n\n\ndef collect_daily_fallback_items",
    duplicate_block + "\n\ndef collect_daily_fallback_items",
    text,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"Expected one duplicate collector block, replaced {count}")

queue_path.write_text(text, encoding="utf-8")

test_path = Path("python/range_library_memory/tests/test_structure_review_queue.py")
tests = test_path.read_text(encoding="utf-8")
tests = tests.replace('"SAME_BOUNDARIES",\n                "high",', '"same_range_window",\n                "high",')

append = r'''


def test_importer_overlap_noise_does_not_become_chart_work(tmp_path: Path) -> None:
    db = tmp_path / "noise.sqlite3"
    import_source(
        db,
        write_source(
            tmp_path,
            [
                weekly_range("419"),
                weekly_range("425", range_high_price=2200.0, range_low_price=1900.0),
            ],
        ),
        "fixture",
    )

    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM duplicate_candidates WHERE rule_code='overlapping_range_window'"
        ).fetchone()[0] > 0

    result = build_structure_review_queue(db)
    assert result["action_required_count"] == 0
    assert list_structure_review_queue(db) == []


def test_validation_queue_ignores_warnings_and_superseded_versions(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419")])
    old = raw_range_row(db, "419")
    now = "2026-07-12T00:00:00Z"

    revised = weekly_range("419", range_high_price=2110.0)
    import_source(db, write_source(tmp_path, [revised]), "fixture-revision")
    latest = raw_range_row(db, "419")
    assert latest["id"] != old["id"]

    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO validation_issues(
                import_run_id, raw_range_id, severity, issue_code, message,
                field_name, created_at_utc
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                old["import_run_id"], old["id"], "error", "OLD_INVALID",
                "Old revision issue.", "high", now,
            ),
        )
        connection.execute(
            """
            INSERT INTO validation_issues(
                import_run_id, raw_range_id, severity, issue_code, message,
                field_name, created_at_utc
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                latest["import_run_id"], latest["id"], "warning", "CURRENT_WARNING",
                "Current warning only.", "timeframe", now,
            ),
        )

    result = build_structure_review_queue(db)
    assert result["action_required_count"] == 0
    assert list_structure_review_queue(db) == []
'''

if "test_importer_overlap_noise_does_not_become_chart_work" not in tests:
    tests += append

test_path.write_text(tests, encoding="utf-8")
