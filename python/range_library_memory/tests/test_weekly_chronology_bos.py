from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import pytest
from contextlib import closing
from pathlib import Path

from range_library_memory.weekly_chronology_bos import (
    TABLE,
    RUN_TABLE,
    SAMPLE_TABLE,
    VERSION,
    build_weekly_chronology_bos,
    project_stored_results,
    review_weekly_script1_run,
)


def node(
    canonical_id: str,
    *,
    high: float = 2000,
    low: float = 1900,
    high_time: str | None = "2026-01-12T00:00:00Z",
    low_time: str | None = "2026-01-05T00:00:00Z",
    direction: str | None = None,
    navigation: str = "TRUSTED",
    statistics: str = "ELIGIBLE",
    case_ref: str = "case:live",
) -> dict:
    return {
        "node_type": "RANGE",
        "id": canonical_id,
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "direction_of_break": direction,
        "navigation_status": navigation,
        "statistics_status": statistics,
        "direct_parent_link_status": "ROOT",
        "source_refs": [{"raw_id": int(canonical_id.rsplit("-", 1)[-1]), "source_record_id": canonical_id, "case_ref": case_ref}],
        "children": [],
    }


def symbol_root(children: list[dict], suffix: str = "") -> dict:
    return {
        "node_type": "SYMBOL",
        "id": f"symbol:XAUUSD{suffix}",
        "label": "XAUUSD",
        "children": children,
        "unlinked_review_children": [],
    }


def write_range_db(path: Path, trusted: list[dict], review: list[dict] | None = None) -> None:
    review = review or []
    trusted_copy = copy.deepcopy(trusted)
    review_copy = copy.deepcopy(review)
    master_map = {
        "schema_version": "xauusd_master_map_v0.1",
        "build_id": "fixture-build",
        "built_at_utc": "2026-03-01T00:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "stable-structural-hash",
        "root": symbol_root(copy.deepcopy(trusted + review)),
        "trusted_root": symbol_root(trusted_copy, ":trusted"),
        "review_root": symbol_root(review_copy, ":review"),
        "statistics": {},
    }
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE master_map_outputs (
                symbol TEXT PRIMARY KEY, build_id TEXT NOT NULL, schema_version TEXT NOT NULL,
                built_at_utc TEXT NOT NULL, structural_content_hash TEXT NOT NULL, output_json TEXT NOT NULL
            );
            CREATE TABLE master_map_ranges (
                canonical_range_id TEXT PRIMARY KEY, canonical_payload_json TEXT NOT NULL
            );
            CREATE TABLE raw_ranges (id INTEGER PRIMARY KEY, marker TEXT NOT NULL);
            CREATE TABLE raw_events (id INTEGER PRIMARY KEY, marker TEXT NOT NULL);
            INSERT INTO raw_ranges VALUES (1, 'raw-range-unchanged');
            INSERT INTO raw_events VALUES (1, 'raw-event-unchanged');
            """
        )
        connection.execute(
            "INSERT INTO master_map_outputs VALUES (?,?,?,?,?,?)",
            ("XAUUSD", "fixture-build", "xauusd_master_map_v0.1", "2026-03-01T00:00:00Z",
             "stable-structural-hash", json.dumps(master_map, sort_keys=True)),
        )
        for item in trusted + review:
            connection.execute(
                "INSERT INTO master_map_ranges VALUES (?,?)",
                (item["id"], json.dumps(item, sort_keys=True)),
            )
        connection.commit()


def write_source_db(path: Path, candles: list[tuple]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE candles (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL, time TEXT NOT NULL,
                open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
                volume REAL, source TEXT
            );
            CREATE TABLE map_ranges (id INTEGER PRIMARY KEY);
            """
        )
        connection.executemany(
            "INSERT INTO candles(symbol,timeframe,time,open,high,low,close,volume,source) "
            "VALUES ('XAUUSD','W1',?,?,?,?,?,?, 'fixture')",
            candles,
        )
        connection.commit()


def raw_digest(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        values = [
            connection.execute("SELECT * FROM raw_ranges ORDER BY id").fetchall(),
            connection.execute("SELECT * FROM raw_events ORDER BY id").fetchall(),
        ]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def fixture_candles() -> list[tuple]:
    return [
        ("2026-01-05T00:00:00Z", 1920, 1950, 1900, 1930, 1),
        ("2026-01-12T00:00:00Z", 1930, 2000, 1920, 1980, 1),
        # Exact touch is rejected.
        ("2026-01-19T00:00:00Z", 1980, 2000, 1950, 1990, 1),
        # First strict UP breach.
        ("2026-01-26T00:00:00Z", 1990, 2012, 1970, 2005, 1),
        # Later UP breach must never replace the first.
        ("2026-02-02T00:00:00Z", 2005, 2050, 1940, 2020, 1),
        ("2026-02-09T00:00:00Z", 2020, 2030, 1900, 1920, 1),
        # First strict DOWN breach for the reverse range.
        ("2026-02-16T00:00:00Z", 1920, 1970, 1888, 1900, 1),
        # Later DOWN breach.
        ("2026-02-23T00:00:00Z", 1900, 1940, 1870, 1880, 1),
    ]


def test_trusted_chronology_strict_first_breach_pending_and_review(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    trusted = [
        node("weekly-1"),
        node("weekly-2", high=2030, low=1900, high_time="2026-02-02T00:00:00Z", low_time="2026-02-09T00:00:00Z"),
        node("weekly-3", high=2100, low=1800, high_time="2026-01-12T00:00:00Z", low_time="2026-01-05T00:00:00Z"),
        node("weekly-4", high_time=None),
        node("weekly-5", high_time="2026-01-05T00:00:00Z", low_time="2026-01-05T00:00:00Z"),
    ]
    review = [node("weekly-9", navigation="REVIEW", statistics="EXCLUDED")]
    write_range_db(range_db, trusted, review)
    write_source_db(source_db, fixture_candles())
    before_raw = raw_digest(range_db)

    summary = build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")
    rows = {row["canonical_range_id"]: row for row in summary["rows"]}

    assert summary["weekly_rows_processed"] == 5
    assert "weekly-9" not in rows
    upward = rows["weekly-1"]
    assert upward["chronology_result"] == "RL_TO_RH"
    assert upward["bos_direction"] == "BOS_UP"
    assert upward["reclaim_direction"] == "DOWN"
    assert upward["bos_candle_time"] == "2026-01-26T00:00:00Z"
    assert upward["bos_evidence_price"] == 2012
    assert upward["exact_touch_count"] == 1
    assert upward["exact_touch_examples"][0]["time"] == "2026-01-19T00:00:00Z"

    downward = rows["weekly-2"]
    assert downward["chronology_result"] == "RH_TO_RL"
    assert downward["bos_direction"] == "BOS_DOWN"
    assert downward["reclaim_direction"] == "UP"
    assert downward["bos_candle_time"] == "2026-02-16T00:00:00Z"
    assert downward["bos_evidence_price"] == 1888

    assert rows["weekly-3"]["processing_status"] == "PENDING"
    assert rows["weekly-3"]["bos_direction"] == "PENDING"
    assert rows["weekly-4"]["processing_status"] == "NEEDS_REVIEW"
    assert rows["weekly-4"]["reason_codes"] == ["MISSING_OR_INVALID_ANCHOR_TIME"]
    assert rows["weekly-5"]["reason_codes"] == ["EQUAL_ANCHOR_TIMES"]
    assert raw_digest(range_db) == before_raw


def test_conflicting_aliases_and_derived_direction_conflict_need_review(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    alias_conflict = node("weekly-1", direction="BOS_UP")
    alias_conflict["script1_bos_direction"] = "BOS_DOWN"
    chronology_conflict = node("weekly-2", direction="DOWN")
    write_range_db(range_db, [alias_conflict, chronology_conflict])
    write_source_db(source_db, fixture_candles())

    rows = {
        row["canonical_range_id"]: row
        for row in build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")["rows"]
    }

    assert rows["weekly-1"]["processing_status"] == "NEEDS_REVIEW"
    assert rows["weekly-1"]["reason_codes"] == ["CONFLICTING_DIRECTION_ALIASES"]
    assert rows["weekly-1"]["bos_direction"] == "PENDING"
    assert rows["weekly-2"]["reason_codes"] == ["DERIVED_DIRECTION_CONFLICTS_WITH_STRUCTURAL_ALIAS"]


def test_deterministic_idempotent_versioned_upsert_and_non_deletion(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    write_range_db(range_db, [node("weekly-1"), node("weekly-2", high_time="2026-02-02T00:00:00Z", low_time="2026-02-09T00:00:00Z")])
    write_source_db(source_db, fixture_candles())

    first = build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")
    with closing(sqlite3.connect(range_db)) as connection:
        connection.execute(
            f"INSERT INTO {TABLE} (canonical_range_id,processing_version,run_id,source_range_ids_json,source_refs_json,case_ref,"
            "symbol,structure_layer,source_timeframe,chronology_result,bos_direction,candles_scanned,"
            "exact_touch_count,exact_touch_examples_json,processing_status,reason_codes_json,result_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("unrelated", "older-version", "older-run", "[]", "[]", "case:other", "XAUUSD", "WEEKLY", "W1", "PENDING",
             "PENDING", 0, 0, "[]", "PENDING", "[]", "older-hash"),
        )
        connection.commit()

    second = build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")

    assert first["aggregate_hash"] == second["aggregate_hash"]
    assert first["run_id"] == second["run_id"]
    with closing(sqlite3.connect(range_db)) as connection:
        assert connection.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE processing_version=?", (VERSION,)
        ).fetchone()[0] == 2
        assert connection.execute(
            f"SELECT result_hash FROM {TABLE} WHERE canonical_range_id='unrelated'"
        ).fetchone()[0] == "older-hash"
        connection.execute("BEGIN EXCLUSIVE")
        connection.rollback()
    with closing(sqlite3.connect(source_db)) as connection:
        connection.execute("BEGIN EXCLUSIVE")
        connection.rollback()


def test_projection_preserves_identity_roots_statuses_refs_and_structural_hash(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    trusted = node("weekly-1")
    review = node("weekly-9", navigation="REVIEW", statistics="EXCLUDED")
    write_range_db(range_db, [trusted], [review])
    write_source_db(source_db, fixture_candles())

    build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")
    with closing(sqlite3.connect(range_db)) as connection:
        connection.row_factory = sqlite3.Row
        output = json.loads(connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol='XAUUSD'"
        ).fetchone()["output_json"])
        persisted_hash = connection.execute(
            "SELECT structural_content_hash FROM master_map_outputs WHERE symbol='XAUUSD'"
        ).fetchone()[0]
        payload = json.loads(connection.execute(
            "SELECT canonical_payload_json FROM master_map_ranges WHERE canonical_range_id='weekly-1'"
        ).fetchone()[0])

    projected = output["trusted_root"]["children"][0]
    assert projected["id"] == "weekly-1"
    assert projected["navigation_status"] == "TRUSTED"
    assert projected["statistics_status"] == "ELIGIBLE"
    assert projected["source_refs"] == trusted["source_refs"]
    assert projected["script1_chronology"] == "RL_TO_RH"
    assert projected["script1_bos_direction"] == "BOS_UP"
    assert projected["script1_bos_time"] == "2026-01-26T00:00:00Z"
    assert output["review_root"]["children"][0].get("script1_bos_direction") is None
    assert output["structural_content_hash"] == "stable-structural-hash"
    assert persisted_hash == "stable-structural-hash"
    assert payload["id"] == "weekly-1"
    assert payload["script1_bos_direction"] == "BOS_UP"

    # A canonical rebuild can re-apply the stored derived projection.
    fresh = json.loads(json.dumps(output))
    for root_key in ("root", "trusted_root", "review_root"):
        for item in fresh[root_key]["children"]:
            for key in list(item):
                if key.startswith("script1_"):
                    del item[key]
    fresh.pop("analysis", None)
    with closing(sqlite3.connect(range_db)) as connection:
        connection.row_factory = sqlite3.Row
        results = project_stored_results(connection, fresh, symbol="XAUUSD")
        connection.commit()
    assert len(results) == 1
    assert fresh["trusted_root"]["children"][0]["script1_bos_direction"] == "BOS_UP"
    assert fresh["review_root"]["children"][0].get("script1_bos_direction") is None


def test_cli_requires_explicit_range_and_source_database_paths() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "range_library_memory.weekly_chronology_bos", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "--db-path" in completed.stderr
    assert "--source-db" in completed.stderr


def test_selected_case_scope_excludes_unrelated_weeklies_and_preserves_provenance(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    selected = node("weekly-1", case_ref="case:selected")
    unrelated = node("weekly-2", case_ref="case:other")
    write_range_db(range_db, [selected, unrelated])
    write_source_db(source_db, fixture_candles())

    summary = build_weekly_chronology_bos(
        range_db, source_db=source_db, case_ref="case:selected", symbol="XAUUSD"
    )

    assert [row["canonical_range_id"] for row in summary["rows"]] == ["weekly-1"]
    assert summary["rows"][0]["case_ref"] == "case:selected"
    with pytest.raises(Exception, match="XAUUSD"):
        build_weekly_chronology_bos(
            range_db, source_db=source_db, case_ref="case:selected", symbol="EURUSD"
        )


def test_analysis_run_approval_and_rejection_persist_without_touching_live_inputs(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    write_range_db(range_db, [node("weekly-1")])
    write_source_db(source_db, fixture_candles())
    raw_before = raw_digest(range_db)
    source_before = source_db.read_bytes()
    summary = build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")

    result = review_weekly_script1_run(
        range_db, run_id=summary["run_id"], case_ref="case:live", symbol="XAUUSD",
        canonical_range_id="weekly-1", decision="APPROVED",
    )
    duplicate = review_weekly_script1_run(
        range_db, run_id=summary["run_id"], case_ref="case:live", symbol="XAUUSD",
        canonical_range_id="weekly-1", decision="APPROVED",
    )
    assert result["approval_state"] == "APPROVED"
    assert duplicate["approval_count"] == 1
    with closing(sqlite3.connect(range_db)) as connection:
        publication_status = connection.execute(
            f"SELECT publication_status FROM {RUN_TABLE} WHERE run_id=?", (summary["run_id"],)
        ).fetchone()[0]
        output = json.loads(connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol='XAUUSD'"
        ).fetchone()[0])
    assert publication_status == "PUBLISHED"
    assert output["trusted_root"]["children"][0]["script1_review_status"] == "APPROVED"
    assert output["analysis"]["weekly_script1"]["run_id"] == summary["run_id"]

    assert raw_digest(range_db) == raw_before
    assert source_db.read_bytes() == source_before
    with pytest.raises(Exception, match="missing or stale"):
        review_weekly_script1_run(
            range_db, run_id="missing", case_ref="case:live",
            symbol="XAUUSD", canonical_range_id="weekly-1", decision="APPROVED",
        )


def test_five_sample_gate_publishes_atomically_and_rejection_stays_unpublished(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    write_range_db(range_db, [node(f"weekly-{index}") for index in range(1, 6)])
    write_source_db(source_db, fixture_candles())
    summary = build_weekly_chronology_bos(range_db, source_db=source_db, case_ref="case:live")
    ids = [row["canonical_range_id"] for row in summary["rows"]]
    for index, canonical_id in enumerate(ids):
        result = review_weekly_script1_run(
            range_db, run_id=summary["run_id"], case_ref="case:live", symbol="XAUUSD",
            canonical_range_id=canonical_id, decision="APPROVED",
        )
        assert result["approval_count"] == index + 1
        assert result["publication_status"] == ("PUBLISHED" if index == 4 else "UNPUBLISHED")
    with closing(sqlite3.connect(range_db)) as connection:
        assert connection.execute(
            f"SELECT COUNT(*) FROM {SAMPLE_TABLE} WHERE run_id=?", (summary["run_id"],)
        ).fetchone()[0] == 5
