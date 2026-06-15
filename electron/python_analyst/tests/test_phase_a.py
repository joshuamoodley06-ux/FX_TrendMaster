"""Phase A smoke tests: fixture loads, derives, audits, writes, combines."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analyst.io.input_loader import load_input_package
from analyst.models.derived_fields import compute_derived_fields
from analyst.pipeline import run_year
from analyst.storage.combined import rebuild_combined
from analyst.util.timeparse import parse_time_to_ms

FIXTURE = Path(__file__).parent / "fixtures" / "XAUUSD_2020_fixture.json"


def test_loader_parses_fixture():
    package, warnings = load_input_package(FIXTURE)
    assert package.symbol == "XAUUSD"
    assert package.year == 2020
    assert len(package.case_refs) == 2
    assert len(package.ranges) == 4
    assert len(package.events) == 3
    assert package.candle_count_total == 8

    weekly = next(r for r in package.ranges if r.range_id == "100")
    assert weekly.parent_range_id is None
    assert weekly.range_high_price == 1700.0
    assert weekly.active_from_time_ms == parse_time_to_ms("2020-02-03 00:00:00")

    broken = next(r for r in package.ranges if r.range_id == "200")
    assert broken.status == "BROKEN"
    assert broken.direction_of_break == "UP"
    assert broken.broken_by_event_id == "5001"
    assert broken.new_range_id == "201"


def test_time_parsing_vps_formats():
    # MT5 CSV candles on the VPS use dotted dates.
    assert parse_time_to_ms("2026.06.11 00:00") == parse_time_to_ms("2026-06-11T00:00:00Z")
    # Map rows use ISO with Z suffix.
    assert parse_time_to_ms("2020-03-08T00:00:00.000Z") == parse_time_to_ms("2020-03-08 00:00:00")


def test_event_id_prefers_map_row_id():
    # VPS ranges reference events via the numeric map row id, so it must win
    # over the UUID event_id field for join stability.
    from analyst.models.records import EventRecord

    event = EventRecord.from_dict(
        {"id": "569", "event_id": "3c7f1a3b-872e-4def-9d1c-5bdeaf74d89d", "event_type": "BOS"}
    )
    assert event.event_id == "569"


def test_derived_fields():
    package, _ = load_input_package(FIXTURE)
    warnings = []
    broken = next(r for r in package.ranges if r.range_id == "200")
    der = compute_derived_fields(broken, warnings)
    assert der.anchor_start_ms == parse_time_to_ms("2020-03-02 00:00:00")
    assert der.anchor_end_ms == parse_time_to_ms("2020-03-05 00:00:00")
    assert der.lifecycle_start_ms == broken.active_from_time_ms
    assert der.lifecycle_end_ms == parse_time_to_ms("2020-03-06 00:00:00")
    assert der.price_span == 60.0
    assert warnings == []


def test_run_year_outputs(tmp_path):
    out_dir = tmp_path / "workspace" / "XAUUSD" / "2020"
    result = run_year(FIXTURE, out_dir)

    for name in (
        "input_snapshot.json",
        "normalized_ranges.parquet",
        "normalized_events.parquet",
        "yearly_stats.json",
    ):
        assert (out_dir / name).is_file(), name

    reports = out_dir / "reports"
    for name in (
        "analyst_summary.json",
        "analyst_report.md",
        "audit_warnings.csv",
        "hierarchy_completeness.csv",
        "yearly_summary.csv",
        "range_zone_position.csv",
        "retracement_stats.csv",
        "bos_reclaim_report.csv",
        "bos_abandon_report.csv",
        "extreme_rotation_report.csv",
        "impulse_retest_sequence.csv",
    ):
        assert (reports / name).is_file(), name

    codes = {w.code for w in result["warnings"]}
    assert "WRONG_PARENT_LINK" in codes  # range 300 -> missing parent 999
    assert "LEDGER_HASH_MISMATCH" not in codes  # fixture hash is valid

    ledger_results = result["summary"]["ledger_results"]
    assert ledger_results[0]["status"] == "OK"

    ranges_df = pd.read_parquet(out_dir / "normalized_ranges.parquet")
    assert len(ranges_df) == 4
    assert "anchor_start_ms" in ranges_df.columns
    assert "price_span" in ranges_df.columns

    # Weekly root accepted when Macro absent.
    hierarchy = (reports / "hierarchy_completeness.csv").read_text(encoding="utf-8")
    weekly_row = next(line for line in hierarchy.splitlines() if line.split(",")[1] == "100")
    assert weekly_row.endswith("true,true")  # is_root, root_accepted

    # Combined rebuilt automatically because output dir is workspace/SYMBOL/YEAR.
    combined_dir = tmp_path / "workspace" / "XAUUSD" / "combined"
    assert (combined_dir / "XAUUSD_combined_stats.json").is_file()
    assert (combined_dir / "XAUUSD_year_comparison.csv").is_file()
    assert (combined_dir / "XAUUSD_combined_report.md").is_file()


def test_combined_updates_after_second_year(tmp_path):
    workspace = tmp_path / "workspace"
    run_year(FIXTURE, workspace / "XAUUSD" / "2020")

    # Hand-make a second year from the same fixture.
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["year"] = 2021
    payload["label"] = "XAUUSD_2021_fixture"
    second = tmp_path / "XAUUSD_2021.json"
    second.write_text(json.dumps(payload), encoding="utf-8")
    run_year(second, workspace / "XAUUSD" / "2021")

    result = rebuild_combined(workspace, "XAUUSD")
    assert result["years"] == 2
    comparison = (workspace / "XAUUSD" / "combined" / "XAUUSD_year_comparison.csv").read_text(
        encoding="utf-8"
    )
    assert "2020" in comparison and "2021" in comparison


def test_tampered_ledger_warns(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ledger_key = "raw:c0ffee11-2222-3333-4444-555555555555"
    payload["data"]["raw_ledgers"][ledger_key]["meta"]["ledger_hash"] = "deadbeef"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    result = run_year(tampered, tmp_path / "out")
    codes = {w.code for w in result["warnings"]}
    assert "LEDGER_HASH_MISMATCH" in codes
