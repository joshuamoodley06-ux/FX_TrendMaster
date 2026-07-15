from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from range_library_memory import xauusd_mapping_assistant as assistant


def source_ref(source_id: str) -> dict[str, object]:
    return {
        "raw_id": 1,
        "case_ref": "CASE-1",
        "source_record_id": source_id,
        "payload_sha256": "a" * 64,
    }


def range_node(
    range_id: str,
    layer: str,
    *,
    high: float,
    low: float,
    high_time: str,
    low_time: str,
    active_from: str,
    children: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "node_type": "RANGE",
        "id": range_id,
        "structure_layer": layer,
        "source_timeframe": {"WEEKLY": "W1", "DAILY": "D1", "INTRADAY": "H1"}[layer],
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": active_from,
        "inactive_from_time": None,
        "status": "ACTIVE",
        "direction_of_break": None,
        "navigation_status": "TRUSTED",
        "statistics_status": "ELIGIBLE",
        "ancestor_review_status": "CLEAR",
        "direct_parent_link_status": "VALID",
        "review_context_only": False,
        "source_count": 1,
        "source_refs": [source_ref(range_id)],
        "events": [],
        "children": children or [],
    }


def master_map_fixture() -> dict[str, object]:
    child = range_node(
        "mm:range:daily-1",
        "DAILY",
        high=2500.0,
        low=2400.0,
        high_time="2026-01-18T00:00:00Z",
        low_time="2026-01-12T00:00:00Z",
        active_from="2026-01-18T00:00:00Z",
    )
    parent = range_node(
        "mm:range:weekly-1",
        "WEEKLY",
        high=2600.0,
        low=2200.0,
        high_time="2026-01-25T00:00:00Z",
        low_time="2025-12-28T00:00:00Z",
        active_from="2026-01-25T00:00:00Z",
        children=[child],
    )
    root = {
        "node_type": "SYMBOL",
        "id": "mm:root:xauusd",
        "label": "XAUUSD",
        "children": [parent],
        "unlinked_review_children": [],
    }
    return {
        "schema_version": "xauusd_master_map_v0.1",
        "build_id": "fixture",
        "built_at_utc": "1970-01-01T00:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "b" * 64,
        "root": root,
        "trusted_root": root,
        "review_root": {**root, "children": []},
        "statistics": {},
        "review_items": [],
    }


def doctrine_report_fixture() -> dict[str, object]:
    return {
        "summary": {
            "unique_weekly_parent_count": 1,
            "structure_query_ready_count": 0,
            "confirmation_query_ready_count": 0,
            "outcome_query_ready_count": 0,
            "overall_first_query_ready_count": 0,
        },
        "states": [
            {
                "candidate_state_id": "candidate-1",
                "child_range_id": "mm:range:daily-1",
                "freeze_at": "2026-02-02T00:00:00Z",
                "confirming_event_id": "mm:event:bos-1",
                "source_timeframe": "D1",
            }
        ],
        "weekly_parent_priority_queue": [
            {
                "weekly_parent_range_id": "mm:range:weekly-1",
                "priority_rank": 1,
                "blocked_candidate_count": 1,
                "candidate_state_ids": ["candidate-1"],
                "earliest_candidate_freeze": "2026-02-02T00:00:00Z",
                "latest_candidate_freeze": "2026-02-02T00:00:00Z",
                "exact_missing_evidence": ["APPROVED_PREFREEZE_WEEKLY_DIRECTION_EVIDENCE"],
                "recommended_mapping_action": "MAP_WEEKLY_FORMATION_BOS",
                "evidence_already_present": [],
            }
        ],
    }


def test_projects_trader_readable_gap_and_exact_navigation() -> None:
    result = assistant.project_mapping_assistant_snapshot(
        master_map_fixture(),
        doctrine_report_fixture(),
        generated_at_utc="2026-07-15T00:00:00Z",
    )

    assert result["schema_version"] == assistant.SNAPSHOT_SCHEMA_VERSION
    assert result["summary"] == {
        "research_gap_count": 1,
        "blocked_candidate_count": 1,
        "unique_weekly_parent_count": 1,
        "structure_query_ready_count": 0,
        "confirmation_query_ready_count": 0,
        "outcome_query_ready_count": 0,
        "overall_first_query_ready_count": 0,
    }
    gap = result["gaps"][0]
    assert gap["parent"]["canonical_range_id"] == "mm:range:weekly-1"
    assert gap["requirement"]["trader_title"] == "Weekly direction evidence missing"
    assert gap["requirement"]["recommended_action_code"] == "MAP_WEEKLY_FORMATION_BOS"
    assert gap["research_impact"]["blocked_candidate_ids"] == ["candidate-1"]
    assert gap["navigation"]["open_structure"]["target_timeframe"] == "W1"
    assert gap["navigation"]["open_structure"]["canonical_range_id"] == "mm:range:weekly-1"
    assert gap["navigation"]["show_first_candidate"] == {
        "canonical_range_id": "mm:range:daily-1",
        "event_id": "mm:event:bos-1",
        "target_layer": "DAILY",
        "target_timeframe": "D1",
        "preferred_anchor_time": "2026-02-02T00:00:00Z",
        "visible_start": "2025-12-08T00:00:00Z",
        "visible_end": "2026-02-16T00:00:00Z",
    }


def test_projection_is_deterministic_when_generated_time_is_fixed() -> None:
    first = assistant.project_mapping_assistant_snapshot(
        master_map_fixture(), doctrine_report_fixture(), generated_at_utc="2026-07-15T00:00:00Z"
    )
    second = assistant.project_mapping_assistant_snapshot(
        master_map_fixture(), doctrine_report_fixture(), generated_at_utc="2026-07-15T00:00:00Z"
    )
    assert first == second


def test_backup_reads_wal_safe_snapshot_without_changing_source(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "snapshot.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE facts(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts(value) VALUES ('weekly')")
        connection.commit()
    before = assistant.sha256_file(source)

    assistant.backup_sqlite_database(source, destination)

    with closing(sqlite3.connect(destination)) as connection:
        assert connection.execute("SELECT value FROM facts").fetchone()[0] == "weekly"
    assert assistant.sha256_file(source) == before
    destination.unlink()
    assert not destination.exists()


def test_full_snapshot_uses_disposable_database_and_preserves_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "range_library.sqlite3"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE raw_ranges(id INTEGER PRIMARY KEY)")
        connection.commit()
    before = assistant.sha256_file(source)
    seen: dict[str, str] = {}

    def fake_build_master_map(db_path: str | Path, **_: object) -> dict[str, object]:
        seen["snapshot"] = str(db_path)
        assert Path(db_path).resolve() != source.resolve()
        return master_map_fixture()

    monkeypatch.setattr(assistant, "build_master_map", fake_build_master_map)
    monkeypatch.setattr(
        assistant,
        "build_first_query_doctrine_report",
        lambda *_args, **_kwargs: doctrine_report_fixture(),
    )

    result = assistant.build_mapping_assistant_snapshot(
        source,
        generated_at_utc="2026-07-15T00:00:00Z",
    )

    assert result["source_integrity"]["unchanged"] is True
    assert result["source_integrity"]["sha256_before"] == before
    assert result["source_integrity"]["sha256_after"] == before
    assert assistant.sha256_file(source) == before
    assert not Path(seen["snapshot"]).exists()


def test_rejects_non_xauusd_projection() -> None:
    source = master_map_fixture()
    source["symbol"] = "EURUSD"
    with pytest.raises(assistant.MappingAssistantError):
        assistant.project_mapping_assistant_snapshot(source, doctrine_report_fixture())
