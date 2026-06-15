"""Phase C tests: reclaim, abandon, rotation, sequence, outcome classifier.

Fixture geometry reminder (parent 100: 1560-1700):
- child 200: 1590-1650, BROKEN UP @ 2020-03-06 by event 5001 -> new range 201
- child 201: 1640-1692, ACTIVE
- candles D1 2020-03-02 .. 2020-03-11, lows after the BOS all above 1650
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyst.io.input_loader import load_input_package
from analyst.models.bos_abandon import build_bos_abandon_report
from analyst.models.bos_reclaim import build_bos_reclaim_report, classify_reclaim_depth
from analyst.models.derived_fields import compute_derived_fields
from analyst.models.outcome import build_outcome_summary, classify_pair_outcome
from analyst.models.records import RangeRecord
from analyst.models.rotation import build_rotation_report
from analyst.pipeline import run_year

FIXTURE = Path(__file__).parent / "fixtures" / "XAUUSD_2020_fixture.json"


def _load(path=FIXTURE):
    package, warnings = load_input_package(path)
    derived = {}
    for rng in package.ranges:
        der = compute_derived_fields(rng, warnings)
        if rng.range_id is not None:
            derived[rng.range_id] = der
    return package, derived, warnings


def _fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path, payload, name="modified.json"):
    target = tmp_path / name
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


# --- 1. BOS + reclaim ---------------------------------------------------


def test_reclaim_depth_classes():
    assert classify_reclaim_depth(0.1) == "SHALLOW"
    assert classify_reclaim_depth(0.33) == "MID"
    assert classify_reclaim_depth(0.66) == "DEEP"
    assert classify_reclaim_depth(None) is None


def test_reclaim_no_pullback_fixture():
    package, _, warnings = _load()
    rows, stats = build_bos_reclaim_report(package, warnings)

    assert len(rows) == 1
    row = rows[0]
    assert row["range_id"] == "200"
    assert row["bos_direction"] == "UP"
    # Lows after the BOS (1655/1660/1670) never dip below broken level 1650.
    assert row["reclaim_occurred"] is False
    assert row["reclaim_time"] is None
    assert stats == {
        "bos_count": 1,
        "reclaim_true": 0,
        "reclaim_false": 1,
        "unresolved": 0,
        "reclaim_rate": 0.0,
        "class_counts": {},
        "continuation_after_reclaim": 0,
    }


def test_reclaim_detected_synthetic(tmp_path):
    payload = _fixture_payload()
    # 2020-03-09 dips below the broken level (1650) and closes back above it.
    candle = payload["data"]["candles"]["D1"][5]
    assert candle["time"] == "2020-03-09 00:00:00"
    candle["low"] = 1645.0
    candle["close"] = 1656.0

    package, _, warnings = _load(_write(tmp_path, payload))
    rows, stats = build_bos_reclaim_report(package, warnings)

    row = rows[0]
    assert row["reclaim_occurred"] is True
    assert row["reclaim_time"] == "2020-03-09T00:00:00Z"
    assert row["reclaim_candle_count_after_bos"] == 1
    # depth = (1650 - 1645) / 52 (new range 201 span)
    assert row["reclaim_depth_percent"] == pytest.approx(0.096154, abs=1e-6)
    assert row["reclaim_class"] == "SHALLOW"
    # New range 201 is still unbroken: continuation unresolved.
    assert row["continuation_after_reclaim"] is None
    assert stats["reclaim_true"] == 1


def test_reclaim_missing_candles_unresolved(tmp_path):
    payload = _fixture_payload()
    payload["data"]["candles"] = {}
    package, _, warnings = _load(_write(tmp_path, payload))
    rows, stats = build_bos_reclaim_report(package, warnings)

    assert rows[0]["reclaim_occurred"] is None
    assert stats["unresolved"] == 1
    assert "RECLAIM_CANDLES_MISSING" in {w.code for w in warnings}


# --- 2. BOS + abandon ---------------------------------------------------


def test_abandon_unresolved_fixture():
    package, _, warnings = _load()
    rows, stats = build_bos_abandon_report(package, warnings)

    assert len(rows) == 1
    row = rows[0]
    assert row["old_range_id"] == "200"
    assert row["new_range_id"] == "201"
    assert row["abandoned"] is None
    assert row["abandon_reason"] == "UNRESOLVED"
    assert stats["unresolved"] == 1


def test_abandon_status_abandoned(tmp_path):
    payload = _fixture_payload()
    payload["data"]["ranges"][2]["status"] = "ABANDONED"  # range 201
    payload["data"]["ranges"][2]["inactive_from_time"] = "2020-03-11 00:00:00"

    package, _, warnings = _load(_write(tmp_path, payload))
    rows, stats = build_bos_abandon_report(package, warnings)

    row = rows[0]
    assert row["abandoned"] is True
    assert row["abandon_reason"] == "STATUS_ABANDONED"
    assert row["opposite_break_time"] == "2020-03-11T00:00:00Z"
    assert stats["abandoned"] == 1


def test_abandon_price_rule(tmp_path):
    payload = _fixture_payload()
    # New candle closes below new range low (1640) before any continuation.
    payload["data"]["candles"]["D1"].append(
        {"symbol": "XAUUSD", "timeframe": "D1", "time": "2020-03-12 00:00:00",
         "open": 1675.0, "high": 1676.0, "low": 1630.0, "close": 1635.0, "volume": 900}
    )

    package, _, warnings = _load(_write(tmp_path, payload))
    rows, stats = build_bos_abandon_report(package, warnings)

    row = rows[0]
    assert row["abandoned"] is True
    assert row["abandon_reason"] == "PRICE_BROKE_NEW_RANGE_LOW"
    assert row["opposite_break_time"] == "2020-03-12T00:00:00Z"
    assert row["candles_before_abandon"] == 4  # 03-09, 03-10, 03-11, 03-12
    assert stats["reason_counts"] == {"PRICE_BROKE_NEW_RANGE_LOW": 1}


# --- 3. Extreme rotation ------------------------------------------------


def test_rotation_fixture():
    package, derived, warnings = _load()
    rows, stats = build_rotation_report(package, derived, warnings)

    assert len(rows) == 1
    row = rows[0]
    assert row["parent_range_id"] == "100"
    assert row["parent_layer"] == "WEEKLY"
    assert row["child_layer"] == "DAILY"
    # Thresholds: discount <= 1606.2, premium >= 1652.4.
    # 03-02/03-03 touch discount (one episode), 03-06..03-11 touch premium.
    assert row["discount_touches"] == 1
    assert row["premium_touches"] == 1
    assert row["rotations_count"] == 1  # discount -> premium
    assert row["final_break_direction"] is None  # parent still active
    assert row["child_count_before_break"] == 2

    assert stats["discount_to_premium"] == 1
    assert stats["premium_to_discount"] == 0


# --- 4. Impulse / retest sequence ----------------------------------------


def test_sequence_fixture(tmp_path):
    result = run_year(FIXTURE, tmp_path / "out")
    rows = result["rule_report_rows"]["impulse_retest_sequence.csv"]

    assert len(rows) == 1
    row = rows[0]
    assert row["parent_range_id"] == "100"
    assert row["child_range_id"] == "200"
    assert row["layer"] == "DAILY"
    assert row["sequence_direction"] == "UP"
    assert row["impulse_index"] == 1
    assert row["retest_index"] == 1  # retracement measured (DEEP)
    assert row["bos_event_id"] == "5001"
    assert row["reclaim_detected"] is False
    assert row["retracement_class"] == "DEEP"
    assert row["next_outcome"] == "UNRESOLVED"


def test_sequence_two_impulses_same_direction(tmp_path):
    payload = _fixture_payload()
    # Range 201 breaks UP too and creates range 202: impulse_2 in the run.
    payload["data"]["ranges"][2].update(
        {"status": "BROKEN", "direction_of_break": "UP", "broken_by_event_id": 5002,
         "inactive_from_time": "2020-03-10 00:00:00", "new_range_id": 202}
    )
    payload["data"]["ranges"].append(
        {"id": 202, "case_ref": "raw:c0ffee11-2222-3333-4444-555555555555",
         "symbol": "XAUUSD", "structure_layer": "DAILY", "source_timeframe": "D1",
         "chart_timeframe": "H4", "parent_range_id": 100, "old_range_id": 201,
         "status": "ACTIVE", "range_high_price": 1700.0, "range_low_price": 1660.0,
         "range_high_time": "2020-03-11 00:00:00", "range_low_time": "2020-03-10 00:00:00",
         "active_from_time": "2020-03-10 00:00:00"}
    )

    result = run_year(_write(tmp_path, payload), tmp_path / "out")
    rows = result["rule_report_rows"]["impulse_retest_sequence.csv"]

    assert [(r["child_range_id"], r["impulse_index"]) for r in rows] == [("200", 1), ("201", 2)]
    assert all(r["sequence_direction"] == "UP" for r in rows)
    assert rows[0]["next_outcome"] == "CONTINUED"  # 201 broke in BOS direction
    assert rows[1]["next_outcome"] == "UNRESOLVED"  # 202 still open

    stats = result["yearly_stats"]["rule_stats"]["sequence"]
    assert stats["chains"] == 1
    assert stats["impulses"] == 2
    assert stats["max_impulse_index"] == 2


# --- 5. Outcome classifier -----------------------------------------------


def _range(**overrides) -> RangeRecord:
    base = {"id": "X", "status": "ACTIVE"}
    base.update(overrides)
    return RangeRecord.from_dict(base)


def test_outcome_classifier_unit():
    assert classify_pair_outcome(None, "UP") == "UNRESOLVED"
    assert classify_pair_outcome(_range(status="ABANDONED"), "UP") == "ABANDONED"
    assert classify_pair_outcome(_range(), "UP", price_abandoned=True) == "ABANDONED"
    assert classify_pair_outcome(_range(status="BROKEN", direction_of_break="UP"), "UP") == "CONTINUED"
    assert classify_pair_outcome(_range(status="BROKEN", direction_of_break="DOWN"), "UP") == "FAILED"

    parent_up = _range(id="P", status="BROKEN", direction_of_break="UP")
    parent_down = _range(id="P", status="BROKEN", direction_of_break="DOWN")
    assert classify_pair_outcome(_range(), "UP", parent_range=parent_up) == "PARENT_BOS"
    assert classify_pair_outcome(_range(), "UP", parent_range=parent_down) == "OPPOSITE_BOS"
    assert classify_pair_outcome(_range(), "UP", parent_range=_range(id="P")) == "UNRESOLVED"


def test_outcome_summary_fixture():
    package, _, warnings = _load()
    abandon_rows, _ = build_bos_abandon_report(package, warnings)
    outcome_by_id, stats = build_outcome_summary(package, abandon_rows)

    assert outcome_by_id == {"201": "UNRESOLVED"}
    assert stats == {"pairs": 1, "counts": {"UNRESOLVED": 1}}


def test_outcome_summary_uses_price_abandon(tmp_path):
    payload = _fixture_payload()
    payload["data"]["candles"]["D1"].append(
        {"symbol": "XAUUSD", "timeframe": "D1", "time": "2020-03-12 00:00:00",
         "open": 1675.0, "high": 1676.0, "low": 1630.0, "close": 1635.0, "volume": 900}
    )
    package, _, warnings = _load(_write(tmp_path, payload))
    abandon_rows, _ = build_bos_abandon_report(package, warnings)
    outcome_by_id, stats = build_outcome_summary(package, abandon_rows)

    assert outcome_by_id == {"201": "ABANDONED"}
    assert stats["counts"] == {"ABANDONED": 1}


# --- End to end ----------------------------------------------------------


def test_run_year_phase_c_rule_stats(tmp_path):
    result = run_year(FIXTURE, tmp_path / "out")
    rule_stats = result["yearly_stats"]["rule_stats"]

    assert rule_stats["bos_reclaim"]["bos_count"] == 1
    assert rule_stats["bos_reclaim"]["reclaim_false"] == 1
    assert rule_stats["bos_abandon"]["pairs"] == 1
    assert rule_stats["bos_abandon"]["reason_counts"] == {"UNRESOLVED": 1}
    assert rule_stats["rotation"]["parents"] == 1
    assert rule_stats["rotation"]["rotations"] == 1
    assert rule_stats["sequence"]["impulses"] == 1
    assert rule_stats["outcomes"] == {"pairs": 1, "counts": {"UNRESOLVED": 1}}

    report_md = (tmp_path / "out" / "reports" / "analyst_report.md").read_text(encoding="utf-8")
    for fragment in ("BOS reclaim", "BOS abandon", "Extreme rotation", "Impulse/retest", "Outcomes"):
        assert fragment in report_md, fragment
