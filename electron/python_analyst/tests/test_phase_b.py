"""Phase B tests: factual rule models against the hand-made fixture.

Fixture geometry (parent 100: low 1560, high 1700, span 140):
- child 200: 1590-1650, BROKEN UP by event 5001 @ 1652
- child 201: 1640-1692, ACTIVE, formed from 200 (old_range_id chain)
- range 300: wrong parent 999 (case:7)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyst.io.input_loader import load_input_package
from analyst.models.bos_direction import build_bos_direction_report
from analyst.models.derived_fields import compute_derived_fields
from analyst.models.parent_child import build_parent_child_report
from analyst.models.range_metrics import build_range_metrics_report
from analyst.models.retracement import build_retracement_report, classify_retracement
from analyst.models.zones import build_zone_report, classify_zone
from analyst.pipeline import run_year

FIXTURE = Path(__file__).parent / "fixtures" / "XAUUSD_2020_fixture.json"

DAY_MS = 86_400_000


def _load():
    package, warnings = load_input_package(FIXTURE)
    derived = {}
    for rng in package.ranges:
        der = compute_derived_fields(rng, warnings)
        if rng.range_id is not None:
            derived[rng.range_id] = der
    return package, derived, warnings


def test_zone_classification_boundaries():
    assert classify_zone(0.05) == ("DISCOUNT", "DISCOUNT_M1")
    assert classify_zone(0.214286) == ("DISCOUNT", "DISCOUNT_M2")
    assert classify_zone(0.428571) == ("FAIR", "FAIR_M1")
    assert classify_zone(0.657143) == ("FAIR", "FAIR_M3")
    assert classify_zone(0.757143) == ("PREMIUM", "PREMIUM_M1")
    assert classify_zone(0.942857) == ("PREMIUM", "PREMIUM_M3")
    assert classify_zone(1.0) == ("PREMIUM", "PREMIUM_M3")
    assert classify_zone(-0.1) == ("BELOW_RANGE", "BELOW_RANGE")
    assert classify_zone(1.2) == ("ABOVE_RANGE", "ABOVE_RANGE")
    assert classify_zone(None) == (None, None)


def test_zone_positions():
    package, _, warnings = _load()
    rows, stats = build_zone_report(package, warnings)

    # Range 300 has an unresolvable parent and must be skipped, not crash.
    assert {row["child_range_id"] for row in rows} == {"200", "201"}

    row_200 = next(row for row in rows if row["child_range_id"] == "200")
    assert row_200["rh_position_percent"] == pytest.approx(0.642857, abs=1e-6)
    assert row_200["rl_position_percent"] == pytest.approx(0.214286, abs=1e-6)
    assert row_200["midpoint_position_percent"] == pytest.approx(0.428571, abs=1e-6)
    assert row_200["bos_position_percent"] == pytest.approx(0.657143, abs=1e-6)
    assert row_200["start_zone"] == "FAIR"
    assert row_200["start_zone_third"] == "FAIR_M1"
    assert row_200["break_zone"] == "FAIR"
    assert row_200["break_zone_third"] == "FAIR_M3"

    row_201 = next(row for row in rows if row["child_range_id"] == "201")
    assert row_201["rh_position_percent"] == pytest.approx(0.942857, abs=1e-6)
    assert row_201["start_zone"] == "PREMIUM"
    assert row_201["start_zone_third"] == "PREMIUM_M1"
    assert row_201["bos_position_percent"] is None
    assert row_201["break_zone"] is None

    assert stats["children_classified"] == 2
    assert stats["start_zone_counts"] == {"FAIR": 1, "PREMIUM": 1}
    assert stats["break_zone_counts"] == {"FAIR": 1}


def test_range_metrics():
    package, derived, _ = _load()
    rows, stats = build_range_metrics_report(package, derived)
    assert len(rows) == 4

    row_200 = next(row for row in rows if row["range_id"] == "200")
    assert row_200["anchor_span_ms"] == 3 * DAY_MS
    assert row_200["lifecycle_span_ms"] == 4 * DAY_MS
    assert row_200["price_span"] == 60.0
    assert row_200["price_span_percent_of_parent"] == pytest.approx(0.428571, abs=1e-6)

    # Active ranges have no lifecycle end yet.
    row_201 = next(row for row in rows if row["range_id"] == "201")
    assert row_201["lifecycle_span_ms"] is None

    assert stats["ranges"] == 4
    assert stats["by_layer"]["DAILY"]["count"] == 2
    assert stats["by_layer"]["DAILY"]["avg_lifecycle_span_ms"] == 4 * DAY_MS


def test_parent_child_summary():
    package, _, _ = _load()
    rows, stats = build_parent_child_report(package)

    assert len(rows) == 1
    row = rows[0]
    assert row["parent_range_id"] == "100"
    assert row["parent_layer"] == "WEEKLY"
    assert row["child_count"] == 2
    assert row["child_layers"] == "DAILY"
    assert row["children_broken_up"] == 1
    assert row["children_broken_down"] == 0
    assert row["children_active"] == 1

    assert stats["parents_with_children"] == 1
    assert stats["total_children"] == 2
    assert stats["orphan_children"] == 1  # range 300 -> missing parent 999


def test_bos_direction_stats():
    package, _, _ = _load()
    rows, stats = build_bos_direction_report(package)

    daily = next(row for row in rows if row["structure_layer"] == "DAILY")
    assert daily["range_bos_up"] == 1
    assert daily["event_bos_up"] == 1  # event 5001; RECLAIM 5002 not counted
    assert daily["range_bos_down"] == 0

    intraday = next(row for row in rows if row["structure_layer"] == "INTRADAY")
    assert intraday["case_ref"] == "case:7"
    assert intraday["event_bos_up"] == 1
    assert intraday["range_bos_up"] == 0

    assert stats["totals"]["range_bos_up"] == 1
    assert stats["totals"]["event_bos_up"] == 2
    assert stats["totals"]["range_bos_down"] == 0


def test_retracement_classes():
    assert classify_retracement(0.1) == "SHALLOW"
    assert classify_retracement(0.33) == "MID"
    assert classify_retracement(0.66) == "DEEP"
    assert classify_retracement(1.0) == "DEEP"
    assert classify_retracement(1.01) == "EXTREME"
    assert classify_retracement(None) is None


def test_retracement_report():
    package, _, warnings = _load()
    rows, stats = build_retracement_report(package, warnings)

    assert len(rows) == 1
    row = rows[0]
    assert row["range_id"] == "201"
    assert row["direction_of_break"] == "UP"
    # lowest low after BOS (1655 on 2020-03-09) into impulse 1640-1692:
    # (1692 - 1655) / 52 = 0.711538
    assert row["retracement_percent"] == pytest.approx(0.711538, abs=1e-6)
    assert row["retracement_class"] == "DEEP"
    assert row["retracement_price"] == 1655.0
    assert row["retracement_time"] == "2020-03-09T00:00:00Z"
    assert row["next_bos_direction"] is None
    assert row["outcome"] == "UNRESOLVED"

    assert stats["sequences"] == 1
    assert stats["class_counts"] == {"DEEP": 1}
    assert stats["avg_retracement_percent"] == pytest.approx(0.711538, abs=1e-6)


def test_retracement_missing_candles_warns_not_crashes(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["data"]["candles"] = {}
    stripped = tmp_path / "no_candles.json"
    stripped.write_text(json.dumps(payload), encoding="utf-8")

    result = run_year(stripped, tmp_path / "out")
    codes = {w.code for w in result["warnings"]}
    assert "RETRACEMENT_CANDLES_MISSING" in codes
    retracement = result["yearly_stats"]["rule_stats"]["retracement"]
    assert retracement["sequences"] == 1
    assert retracement["classified"] == 0


def test_run_year_fills_reports_and_rule_stats(tmp_path):
    out_dir = tmp_path / "workspace" / "XAUUSD" / "2020"
    result = run_year(FIXTURE, out_dir)

    rule_stats = result["yearly_stats"]["rule_stats"]
    assert rule_stats["zones"]["children_classified"] == 2
    assert rule_stats["range_metrics"]["ranges"] == 4
    assert rule_stats["parent_child"]["total_children"] == 2
    assert rule_stats["bos_direction"]["totals"]["event_bos_up"] == 2
    assert rule_stats["retracement"]["sequences"] == 1
    # Phase C models filled too (details in test_phase_c).
    for key in ("bos_reclaim", "bos_abandon", "rotation", "sequence", "outcomes"):
        assert rule_stats[key] is not None

    reports = out_dir / "reports"
    filled = {
        "range_zone_position.csv": 2,
        "range_duration_size.csv": 4,
        "parent_child_summary.csv": 1,
        "bos_direction_stats.csv": 2,
        "retracement_stats.csv": 1,
        "bos_reclaim_report.csv": 1,
        "bos_abandon_report.csv": 1,
        "extreme_rotation_report.csv": 1,
        "impulse_retest_sequence.csv": 1,
    }
    for name, expected_rows in filled.items():
        lines = (reports / name).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1 + expected_rows, name

    # yearly_stats.json on disk carries the same rule_stats.
    stored = json.loads((out_dir / "yearly_stats.json").read_text(encoding="utf-8"))
    assert stored["rule_stats"]["zones"]["children_classified"] == 2

    report_md = (reports / "analyst_report.md").read_text(encoding="utf-8")
    assert "Rule model statistics" in report_md
    assert "Retracement" in report_md
