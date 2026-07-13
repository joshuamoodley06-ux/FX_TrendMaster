from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_parent_conflict_resolver() -> None:
    path = ROOT / "python/range_library_memory/parent_conflict_resolver.py"

    replace_once(
        path,
        """@dataclass(frozen=True)\nclass LifecycleSnapshot:\n    range_source_id: str\n""",
        """@dataclass(frozen=True)\nclass LifecycleSnapshot:\n    case_ref: str | None\n    range_source_id: str\n""",
    )

    replace_once(
        path,
        """        selected_ids = {daily.row.source_record_id for daily in selected}\n        rows = [\n            resolve_daily(\n                daily,\n                weeklies,\n                lifecycles,\n                existing.get(daily.row.source_record_id),\n                timestamp=timestamp,\n            )\n            for daily in selected\n        ]\n""",
        """        selected_ids = {\n            range_identity(daily.row.case_ref, daily.row.source_record_id)\n            for daily in selected\n        }\n        rows = [\n            resolve_daily(\n                daily,\n                weeklies,\n                lifecycles,\n                existing.get(range_identity(daily.row.case_ref, daily.row.source_record_id)),\n                timestamp=timestamp,\n            )\n            for daily in selected\n        ]\n""",
    )

    replace_once(
        path,
        """    lifecycles: dict[str, LifecycleSnapshot],\n""",
        """    lifecycles: dict[tuple[str | None, str], LifecycleSnapshot],\n""",
    )
    replace_once(
        path,
        """    assessments: dict[str, CandidateAssessment] = {}\n\n    for weekly in weeklies:\n        assessment = assess_candidate(daily, weekly, lifecycles.get(weekly.row.source_record_id))\n        assessments[weekly.row.source_record_id] = assessment\n""",
        """    assessments: dict[tuple[str | None, str], CandidateAssessment] = {}\n\n    for weekly in weeklies:\n        weekly_key = range_identity(weekly.row.case_ref, weekly.row.source_record_id)\n        assessment = assess_candidate(daily, weekly, lifecycles.get(weekly_key))\n        assessments[weekly_key] = assessment\n""",
    )
    replace_once(
        path,
        """            assessments.get(preferred_id),\n""",
        """            assessments.get(range_identity(daily.row.case_ref, preferred_id)),\n""",
    )

    replace_once(
        path,
        """          AND id IN (\n              SELECT MAX(id)\n              FROM raw_ranges\n              GROUP BY source_record_id\n          )\n""",
        """          AND id IN (\n              SELECT MAX(id)\n              FROM raw_ranges\n              GROUP BY\n                  COALESCE(\n                      json_extract(raw_payload_json, '$.case_ref'),\n                      json_extract(raw_payload_json, '$.raw_case_id'),\n                      json_extract(raw_payload_json, '$.case_id'),\n                      ''\n                  ),\n                  source_record_id\n          )\n""",
    )

    old_lifecycles = """def load_latest_weekly_lifecycles(\n    connection: sqlite3.Connection,\n) -> dict[str, LifecycleSnapshot]:\n    rows = connection.execute(\n        \"\"\"\n        SELECT lifecycle.*\n        FROM resolved_range_lifecycles AS lifecycle\n        JOIN (\n            SELECT range_source_id, MAX(id) AS max_id\n            FROM resolved_range_lifecycles\n            WHERE structure_layer = 'WEEKLY'\n            GROUP BY range_source_id\n        ) AS latest ON latest.max_id = lifecycle.id\n        WHERE lifecycle.structure_layer = 'WEEKLY'\n        \"\"\"\n    ).fetchall()\n    return {\n        str(row[\"range_source_id\"]): LifecycleSnapshot(\n            range_source_id=str(row[\"range_source_id\"]),\n            effective_status=str(row[\"effective_status\"] or \"UNKNOWN\").upper(),\n            effective_active_from_time=optional_text(row[\"effective_active_from_time\"]),\n            effective_inactive_from_time=optional_text(row[\"effective_inactive_from_time\"]),\n            resolution_status=str(row[\"resolution_status\"] or \"UNRESOLVED\").upper(),\n            resolution_confidence=str(row[\"resolution_confidence\"] or \"low\"),\n        )\n        for row in rows\n    }\n"""
    new_lifecycles = """def load_latest_weekly_lifecycles(\n    connection: sqlite3.Connection,\n) -> dict[tuple[str | None, str], LifecycleSnapshot]:\n    rows = connection.execute(\n        \"\"\"\n        SELECT lifecycle.*\n        FROM resolved_range_lifecycles AS lifecycle\n        JOIN (\n            SELECT case_ref, range_source_id, MAX(id) AS max_id\n            FROM resolved_range_lifecycles\n            WHERE structure_layer = 'WEEKLY'\n            GROUP BY case_ref, range_source_id\n        ) AS latest ON latest.max_id = lifecycle.id\n        WHERE lifecycle.structure_layer = 'WEEKLY'\n        \"\"\"\n    ).fetchall()\n    return {\n        range_identity(row[\"case_ref\"], str(row[\"range_source_id\"])): LifecycleSnapshot(\n            case_ref=optional_text(row[\"case_ref\"]),\n            range_source_id=str(row[\"range_source_id\"]),\n            effective_status=str(row[\"effective_status\"] or \"UNKNOWN\").upper(),\n            effective_active_from_time=optional_text(row[\"effective_active_from_time\"]),\n            effective_inactive_from_time=optional_text(row[\"effective_inactive_from_time\"]),\n            resolution_status=str(row[\"resolution_status\"] or \"UNRESOLVED\").upper(),\n            resolution_confidence=str(row[\"resolution_confidence\"] or \"low\"),\n        )\n        for row in rows\n    }\n"""
    replace_once(path, old_lifecycles, new_lifecycles)

    old_relationships = """def load_latest_relationships(\n    connection: sqlite3.Connection,\n) -> dict[str, sqlite3.Row]:\n    rows = connection.execute(\n        \"\"\"\n        SELECT relationship.*\n        FROM parent_child_relationships AS relationship\n        JOIN (\n            SELECT child_range_id, MAX(id) AS max_id\n            FROM parent_child_relationships\n            WHERE relationship_type = ?\n            GROUP BY child_range_id\n        ) AS latest ON latest.max_id = relationship.id\n        WHERE relationship.relationship_type = ?\n        \"\"\",\n        (RELATIONSHIP_TYPE, RELATIONSHIP_TYPE),\n    ).fetchall()\n    return {\n        str(row[\"child_range_id\"]): row\n        for row in rows\n        if row[\"child_range_id\"] is not None\n    }\n"""
    new_relationships = """def load_latest_relationships(\n    connection: sqlite3.Connection,\n) -> dict[tuple[str | None, str], sqlite3.Row]:\n    rows = connection.execute(\n        \"\"\"\n        SELECT relationship.*\n        FROM parent_child_relationships AS relationship\n        JOIN (\n            SELECT case_ref, child_range_id, MAX(id) AS max_id\n            FROM parent_child_relationships\n            WHERE relationship_type = ?\n            GROUP BY case_ref, child_range_id\n        ) AS latest ON latest.max_id = relationship.id\n        WHERE relationship.relationship_type = ?\n        \"\"\",\n        (RELATIONSHIP_TYPE, RELATIONSHIP_TYPE),\n    ).fetchall()\n    return {\n        range_identity(row[\"case_ref\"], str(row[\"child_range_id\"])): row\n        for row in rows\n        if row[\"child_range_id\"] is not None\n    }\n"""
    replace_once(path, old_relationships, new_relationships)

    old_clear = """def clear_selected_relationships(\n    connection: sqlite3.Connection,\n    child_ids: set[str],\n) -> None:\n    if not child_ids:\n        return\n    ordered = sorted(child_ids, key=source_sort_key)\n    placeholders = \",\".join(\"?\" for _ in ordered)\n    connection.execute(\n        f\"\"\"\n        DELETE FROM parent_child_relationships\n        WHERE relationship_type = ?\n          AND child_range_id IN ({placeholders})\n        \"\"\",\n        (RELATIONSHIP_TYPE, *ordered),\n    )\n"""
    new_clear = """def clear_selected_relationships(\n    connection: sqlite3.Connection,\n    child_ids: set[tuple[str | None, str]],\n) -> None:\n    for case_ref, child_id in sorted(\n        child_ids,\n        key=lambda value: (value[0] or \"\", source_sort_key(value[1])),\n    ):\n        if case_ref is None:\n            connection.execute(\n                \"\"\"\n                DELETE FROM parent_child_relationships\n                WHERE relationship_type = ?\n                  AND case_ref IS NULL\n                  AND child_range_id = ?\n                \"\"\",\n                (RELATIONSHIP_TYPE, child_id),\n            )\n        else:\n            connection.execute(\n                \"\"\"\n                DELETE FROM parent_child_relationships\n                WHERE relationship_type = ?\n                  AND case_ref = ?\n                  AND child_range_id = ?\n                \"\"\",\n                (RELATIONSHIP_TYPE, case_ref, child_id),\n            )\n"""
    replace_once(path, old_clear, new_clear)

    replace_once(
        path,
        """def source_sort_key(value: str) -> tuple[int, int | str]:\n""",
        """def range_identity(case_ref: Any, source_record_id: Any) -> tuple[str | None, str]:\n    return optional_text(case_ref), str(source_record_id)\n\n\ndef source_sort_key(value: str) -> tuple[int, int | str]:\n""",
    )


def patch_structure_review_queue() -> None:
    path = ROOT / "python/range_library_memory/structure_review_queue.py"

    replace_once(
        path,
        """    load_latest_weekly_lifecycles,\n)\n""",
        """    load_latest_weekly_lifecycles,\n    range_identity,\n)\n""",
    )

    replace_once(
        path,
        """            SELECT child_range_id, MAX(id) AS max_id\n            FROM parent_child_relationships\n            WHERE relationship_type = 'weekly_daily'\n            GROUP BY child_range_id\n""",
        """            SELECT case_ref, child_range_id, MAX(id) AS max_id\n            FROM parent_child_relationships\n            WHERE relationship_type = 'weekly_daily'\n            GROUP BY case_ref, child_range_id\n""",
    )
    replace_once(
        path,
        """    dailies = {item.row.source_record_id: item for item in load_latest_ranges(connection, \"DAILY\")}\n""",
        """    dailies = {\n        range_identity(item.row.case_ref, item.row.source_record_id): item\n        for item in load_latest_ranges(connection, \"DAILY\")\n    }\n""",
    )
    replace_once(
        path,
        """    covered: set[str] = set()\n    for relationship in rows:\n        daily_id = str(relationship[\"child_range_id\"] or \"\")\n        if not daily_id:\n            continue\n        daily = dailies.get(daily_id)\n""",
        """    covered: set[tuple[str | None, str]] = set()\n    for relationship in rows:\n        daily_id = str(relationship[\"child_range_id\"] or \"\")\n        if not daily_id:\n            continue\n        case_ref = optional_text(relationship[\"case_ref\"])\n        daily_key = range_identity(case_ref, daily_id)\n        daily = dailies.get(daily_key)\n""",
    )
    replace_once(
        path,
        """                    lifecycles.get(weekly.row.source_record_id),\n""",
        """                    lifecycles.get(range_identity(weekly.row.case_ref, weekly.row.source_record_id)),\n""",
    )
    replace_once(
        path,
        """        covered.add(daily_id)\n""",
        """        covered.add(daily_key)\n""",
    )
    replace_once(
        path,
        """                review_key=f\"parent:{daily_id}\",\n""",
        """                review_key=scoped_review_key(\"parent\", case_ref, daily_id),\n""",
    )

    replace_once(
        path,
        """    weeklies = {item.row.source_record_id: item for item in load_latest_ranges(connection, \"WEEKLY\")}\n    items: list[dict[str, Any]] = []\n    covered: set[str] = set()\n    for row in rows:\n        weekly_id = str(row[\"weekly_range_source_id\"])\n        reasons = parse_codes(row[\"reason_codes_json\"])\n        weekly = weeklies.get(weekly_id)\n        covered.add(weekly_id)\n""",
        """    weeklies = {\n        range_identity(item.row.case_ref, item.row.source_record_id): item\n        for item in load_latest_ranges(connection, \"WEEKLY\")\n    }\n    items: list[dict[str, Any]] = []\n    covered: set[tuple[str | None, str]] = set()\n    for row in rows:\n        weekly_id = str(row[\"weekly_range_source_id\"])\n        case_ref = optional_text(row[\"case_ref\"])\n        weekly_key = range_identity(case_ref, weekly_id)\n        reasons = parse_codes(row[\"reason_codes_json\"])\n        weekly = weeklies.get(weekly_key)\n        covered.add(weekly_key)\n""",
    )
    replace_once(
        path,
        """                review_key=f\"weekly-creation:{weekly_id}\",\n""",
        """                review_key=scoped_review_key(\"weekly-creation\", case_ref, weekly_id),\n""",
    )

    replace_once(
        path,
        """            SELECT COALESCE(event_source_id, CAST(id AS TEXT)) AS event_key, MAX(id) AS max_id\n            FROM event_ohlc_evidence\n            GROUP BY COALESCE(event_source_id, CAST(id AS TEXT))\n""",
        """            SELECT case_ref, COALESCE(event_source_id, CAST(id AS TEXT)) AS event_key,\n                   MAX(id) AS max_id\n            FROM event_ohlc_evidence\n            GROUP BY case_ref, COALESCE(event_source_id, CAST(id AS TEXT))\n""",
    )
    replace_once(
        path,
        """                review_key=f\"event-evidence:{event_key}\",\n""",
        """                review_key=scoped_review_key(\"event-evidence\", row[\"case_ref\"], event_key),\n""",
    )
    replace_once(
        path,
        """                review_key=f\"validation:{row['issue_code']}:{subject_key}\",\n""",
        """                review_key=scoped_review_key(\n                    f\"validation:{row['issue_code']}\", ref.get(\"case_ref\"), subject_key\n                ),\n""",
    )

    replace_once(
        path,
        """    covered_daily_ids: set[str],\n    covered_weekly_ids: set[str],\n""",
        """    covered_daily_ids: set[tuple[str | None, str]],\n    covered_weekly_ids: set[tuple[str | None, str]],\n""",
    )
    replace_once(
        path,
        """        LEFT JOIN daily_range_timelines AS timeline\n          ON timeline.daily_range_source_id = relationship.daily_range_source_id\n""",
        """        LEFT JOIN daily_range_timelines AS timeline\n          ON timeline.daily_range_source_id = relationship.daily_range_source_id\n         AND (\n             timeline.case_ref = relationship.case_ref\n             OR (timeline.case_ref IS NULL AND relationship.case_ref IS NULL)\n         )\n""",
    )
    replace_once(
        path,
        """        daily_id = str(row[\"daily_range_source_id\"])\n        weekly_id = str(row[\"parent_weekly_source_id\"] or \"\")\n        if daily_id in covered_daily_ids or (weekly_id and weekly_id in covered_weekly_ids):\n            continue\n""",
        """        daily_id = str(row[\"daily_range_source_id\"])\n        weekly_id = str(row[\"parent_weekly_source_id\"] or \"\")\n        case_ref = optional_text(row[\"case_ref\"])\n        daily_key = range_identity(case_ref, daily_id)\n        weekly_key = range_identity(case_ref, weekly_id) if weekly_id else None\n        if daily_key in covered_daily_ids or (weekly_key and weekly_key in covered_weekly_ids):\n            continue\n""",
    )
    replace_once(
        path,
        """                review_key=f\"daily-trend:{daily_id}\",\n""",
        """                review_key=scoped_review_key(\"daily-trend\", case_ref, daily_id),\n""",
    )

    replace_once(
        path,
        """def upper_or_none(value: Any) -> str | None:\n    return str(value).upper() if value not in (None, \"\") else None\n\n\ndef source_sort_key(value: str) -> tuple[int, int | str]:\n""",
        """def upper_or_none(value: Any) -> str | None:\n    return str(value).upper() if value not in (None, \"\") else None\n\n\ndef optional_text(value: Any) -> str | None:\n    return None if value in (None, \"\") else str(value)\n\n\ndef scoped_review_key(prefix: str, case_ref: Any, subject: Any) -> str:\n    return f\"{prefix}:{optional_text(case_ref) or 'UNKNOWN_CASE'}:{subject}\"\n\n\ndef source_sort_key(value: str) -> tuple[int, int | str]:\n""",
    )


def write_regression_tests() -> None:
    path = ROOT / "python/range_library_memory/tests/test_case_isolation_regressions.py"
    path.write_text(
        '''from __future__ import annotations\n\nimport json\nimport sqlite3\nfrom pathlib import Path\n\nfrom range_library_memory.importer import import_source\nfrom range_library_memory.parent_conflict_resolver import resolve_parent_conflicts\nfrom range_library_memory.structure_review_queue import (\n    build_structure_review_queue,\n    list_structure_review_queue,\n)\n\n\ndef weekly_range(range_id: str, case_ref: str, high: float, low: float) -> dict:\n    return {\n        "range_id": range_id,\n        "case_ref": case_ref,\n        "symbol": "XAUUSD",\n        "structure_layer": "WEEKLY",\n        "source_timeframe": "W1",\n        "range_high_time": "2026-01-01T00:00:00Z",\n        "range_low_time": "2026-01-02T00:00:00Z",\n        "active_from_time": "2026-01-02T00:00:00Z",\n        "range_high_price": high,\n        "range_low_price": low,\n        "status": "ACTIVE",\n    }\n\n\ndef daily_range(range_id: str, case_ref: str, high: float, low: float) -> dict:\n    return {\n        "range_id": range_id,\n        "case_ref": case_ref,\n        "symbol": "XAUUSD",\n        "structure_layer": "DAILY",\n        "source_timeframe": "D1",\n        "range_high_time": "2026-06-17T00:00:00Z",\n        "range_low_time": "2026-06-11T00:00:00Z",\n        "active_from_time": "2026-06-17T00:00:00Z",\n        "range_high_price": high,\n        "range_low_price": low,\n        "status": "ACTIVE",\n    }\n\n\ndef build_duplicate_case_db(tmp_path: Path) -> Path:\n    source = tmp_path / "duplicate-cases.json"\n    source.write_text(\n        json.dumps(\n            {\n                "ranges": [\n                    weekly_range("419", "case:old-copy", 2100.0, 2000.0),\n                    weekly_range("425", "case:old-copy", 2120.0, 1990.0),\n                    daily_range("420", "case:old-copy", 2050.0, 2020.0),\n                    weekly_range("455", "case:live", 3100.0, 3000.0),\n                    weekly_range("488", "case:live", 3120.0, 2990.0),\n                    weekly_range("535", "case:live", 3300.0, 3200.0),\n                    daily_range("420", "case:live", 3050.0, 3020.0),\n                ]\n            }\n        ),\n        encoding="utf-8",\n    )\n    db = tmp_path / "memory.sqlite3"\n    import_source(db, source, "fixture")\n    return db\n\n\ndef relationship_rows(db: Path) -> list[sqlite3.Row]:\n    with sqlite3.connect(db) as connection:\n        connection.row_factory = sqlite3.Row\n        return connection.execute(\n            "SELECT * FROM parent_child_relationships "\n            "WHERE child_range_id='420' ORDER BY case_ref"\n        ).fetchall()\n\n\ndef test_duplicate_case_range_ids_are_resolved_inside_their_own_case(tmp_path: Path) -> None:\n    db = build_duplicate_case_db(tmp_path)\n\n    summary = resolve_parent_conflicts(db)\n    rows = relationship_rows(db)\n\n    assert summary["rows_built"] == 2\n    assert [(row["case_ref"], row["link_status"]) for row in rows] == [\n        ("case:live", "CONFLICT"),\n        ("case:old-copy", "CONFLICT"),\n    ]\n\n    build_structure_review_queue(db)\n    live = list_structure_review_queue(\n        db, case_ref="case:live", item_type="PARENT_CONFLICT"\n    )\n    old = list_structure_review_queue(\n        db, case_ref="case:old-copy", item_type="PARENT_CONFLICT"\n    )\n\n    assert len(live) == 1\n    assert live[0]["range_source_id"] == "420"\n    assert live[0]["candidate_range_ids"] == ["455", "488"]\n    assert len(old) == 1\n    assert old[0]["range_source_id"] == "420"\n    assert old[0]["candidate_range_ids"] == ["419", "425"]\n    assert live[0]["review_key"] != old[0]["review_key"]\n\n\ndef test_scoped_rebuild_does_not_delete_same_range_id_from_another_case(tmp_path: Path) -> None:\n    db = build_duplicate_case_db(tmp_path)\n    resolve_parent_conflicts(db)\n\n    resolve_parent_conflicts(db, case_ref="case:old-copy", daily_source_id="420")\n    rows = relationship_rows(db)\n\n    assert len(rows) == 2\n    assert {row["case_ref"] for row in rows} == {"case:live", "case:old-copy"}\n''',
        encoding="utf-8",
    )


def main() -> None:
    patch_parent_conflict_resolver()
    patch_structure_review_queue()
    write_regression_tests()


if __name__ == "__main__":
    main()
