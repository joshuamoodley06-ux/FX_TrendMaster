"""Regression harness for 2025 XAUUSD W1 detector audit (run 4750e5ac).

Establishes baseline before detector fixes. Many tests are expected to FAIL until
boundary/seed/lifecycle work lands — that is intentional.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.range_state import EXPANSION_OWNER_BOS_CANDLE
from detector.pipeline import run_detector_v1
from tests.detector_audit_fixture import (
    DETECTION_RUN_ID,
    PRICE_TOLERANCE,
    AuditWeekRow,
    build_gold_rows,
    fixture_paths,
    load_audit_fixture,
    range_candidate_from_result,
    replay_context_for_week,
    rl_failure_kind,
)


def _load_xauusd_w1_candles() -> list[dict] | None:
    try:
        import candle_store

        payload = candle_store.get_candles(symbol="XAUUSD", timeframe="W1", limit=5000)
        candles = list(payload.get("candles") or [])
        return candles if len(candles) >= 200 else None
    except Exception:
        return None


def _assert_price_close(
    testcase: unittest.TestCase,
    label: str,
    actual: float | None,
    expected: float | None,
    *,
    week: str,
) -> None:
    if expected is None:
        testcase.skipTest(f"{week}: no expected {label}")
    if actual is None:
        testcase.fail(f"{week}: detector produced no {label}; expected {expected}")
    testcase.assertIsNotNone(expected)
    testcase.assertAlmostEqual(
        float(actual),
        float(expected),
        delta=PRICE_TOLERANCE,
        msg=f"{week} {label}: got {actual}, expected {expected}",
    )


class DetectorAuditGoldBaselineTests(unittest.TestCase):
    """Fixture-only baseline — runs without candle DB."""

    def test_edit_weeks_show_detector_josh_gap(self) -> None:
        rows = build_gold_rows()
        edits = [r for r in rows if r.audit_action == "EDIT"]
        mismatches = [
            r
            for r in edits
            if not (
                _price_close(r.detector_rh, r.josh_rh)
                and _price_close(r.detector_rl, r.josh_rl)
            )
        ]
        self.assertEqual(len(edits), 12)
        self.assertGreaterEqual(len(mismatches), 10, "baseline: most EDIT weeks differ from Josh gold")

    def test_rl_retracement_coupling_documented(self) -> None:
        rows = build_gold_rows()
        coupled = [r for r in rows if rl_failure_kind(r)]
        self.assertEqual(len(coupled), 14)

    def test_all_weeks_use_last_opposite_swing_before_bos(self) -> None:
        rows = build_gold_rows()
        for row in rows:
            with self.subTest(week=row.week):
                self.assertEqual(
                    row.boundary_selection_reason,
                    "LAST_OPPOSITE_SWING_BEFORE_BOS",
                )


def _price_close(a: float | None, b: float | None, tol: float = PRICE_TOLERANCE) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


class DetectorAuditFixtureTests(unittest.TestCase):
    def test_fixture_paths_exist_and_load(self) -> None:
        for path in fixture_paths():
            with self.subTest(path=str(path)):
                self.assertTrue(path.is_file(), f"missing fixture: {path}")
                data = load_audit_fixture(path)
                self.assertTrue(data.get("ok"))
                self.assertEqual(data.get("detection_run_id"), DETECTION_RUN_ID)
                self.assertEqual(data.get("schema"), "detection_run_audit_v1")

    def test_fixture_has_fourteen_reviewed_weeks(self) -> None:
        data = load_audit_fixture()
        self.assertEqual(len(data.get("suggestions") or []), 14)
        self.assertEqual(len(data.get("corrections") or []), 14)
        rows = build_gold_rows(data)
        self.assertEqual(len(rows), 14)
        actions = {r.audit_action for r in rows}
        self.assertIn("EDIT", actions)
        self.assertIn("REJECT", actions)


class DetectorAuditBoundaryDecouplingTests(unittest.TestCase):
    """After Phase 1, live replay must not couple RH/RL to retracement impulse fields."""

    _candles: list[dict] | None = None
    _gold: list[AuditWeekRow] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls._gold = build_gold_rows()
        cls._candles = _load_xauusd_w1_candles()

    def setUp(self) -> None:
        if self._candles is None:
            self.skipTest("XAUUSD W1 candles unavailable in local candle_store DB")

    def test_rh_not_equal_retracement_impulse_high(self) -> None:
        coupled = 0
        for row in self._gold:
            with self.subTest(week=row.week):
                ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                if draft is None or row.retracement_impulse_high is None:
                    continue
                meta = draft.meta_json or {}
                imp_h = meta.get("retracement_impulse_high")
                if draft.suggested_rh is not None and imp_h is not None:
                    if abs(float(draft.suggested_rh) - float(imp_h)) <= PRICE_TOLERANCE:
                        coupled += 1
        self.assertEqual(coupled, 0, "RH must not blindly equal retracement_impulse_high")

    def test_rl_not_equal_retracement_impulse_low(self) -> None:
        coupled = 0
        for row in self._gold:
            with self.subTest(week=row.week):
                ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                if draft is None or row.retracement_impulse_low is None:
                    continue
                meta = draft.meta_json or {}
                imp_l = meta.get("retracement_impulse_low")
                if draft.suggested_rl is not None and imp_l is not None:
                    if abs(float(draft.suggested_rl) - float(imp_l)) <= PRICE_TOLERANCE:
                        coupled += 1
        self.assertEqual(coupled, 0, "RL must not blindly equal retracement_impulse_low")

    def test_june_22_rl_not_retrace_low(self) -> None:
        row = next(r for r in self._gold if r.week == "2025-06-22")
        ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        draft = range_candidate_from_result(result)
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertAlmostEqual(float(draft.suggested_rl), 3120.81, delta=PRICE_TOLERANCE)
        self.assertNotAlmostEqual(float(draft.suggested_rl), 3293.35, delta=PRICE_TOLERANCE)


class DetectorAuditMarketTimeTests(unittest.TestCase):
    """Phase 2 — audit replay uses market-time keys, not fixed window indices."""

    _candles: list[dict] | None = None
    _gold: list[AuditWeekRow] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls._gold = build_gold_rows()
        cls._candles = _load_xauusd_w1_candles()

    def setUp(self) -> None:
        if self._candles is None:
            self.skipTest("XAUUSD W1 candles unavailable in local candle_store DB")

    def test_replay_includes_market_time_meta(self) -> None:
        distinct_bos_times: set[int] = set()
        for row in self._gold:
            with self.subTest(week=row.week):
                ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                self.assertIsNotNone(draft)
                assert draft is not None
                meta = draft.meta_json or {}
                self.assertEqual(meta.get("candle_index_scope"), "replay_window")
                self.assertIsNotNone(meta.get("bos_time_ms"))
                self.assertIsNotNone(meta.get("reclaim_time_ms"))
                bos_idx = meta.get("bos_candle_index")
                reclaim_idx = meta.get("reclaim_candle_index")
                if bos_idx is not None:
                    self.assertEqual(meta["bos_time_ms"], ctx.candles[int(bos_idx)].time_ms)
                if reclaim_idx is not None:
                    self.assertEqual(meta["reclaim_time_ms"], ctx.candles[int(reclaim_idx)].time_ms)
                self.assertLessEqual(int(meta["bos_time_ms"]), row.replay_until_time_ms)
                self.assertLessEqual(int(meta["reclaim_time_ms"]), row.replay_until_time_ms)
                distinct_bos_times.add(int(meta["bos_time_ms"]))
        self.assertGreater(len(distinct_bos_times), 1, "bos_time_ms must vary across audited weeks")

    def test_boundary_times_present_when_structural_range(self) -> None:
        row = next(r for r in self._gold if r.week == "2025-06-22")
        ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        draft = range_candidate_from_result(result)
        self.assertIsNotNone(draft)
        assert draft is not None
        meta = draft.meta_json or {}
        self.assertIsNotNone(meta.get("rh_boundary_time_ms"))
        self.assertIsNotNone(meta.get("rl_boundary_time_ms"))


class DetectorAuditLegDoctrineTests(unittest.TestCase):
    """Leg-based HTF boundary selection vs Josh gold (12 EDIT weeks)."""

    _candles: list[dict] | None = None
    _gold: list[AuditWeekRow] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls._gold = build_gold_rows()
        cls._candles = _load_xauusd_w1_candles()

    def setUp(self) -> None:
        if self._candles is None:
            self.skipTest("XAUUSD W1 candles unavailable in local candle_store DB")

    def _replay_draft(self, row: AuditWeekRow):
        ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        return range_candidate_from_result(result)

    def test_htf_leg_trace_present_on_edit_weeks(self) -> None:
        edits = [r for r in self._gold if r.audit_action == "EDIT"]
        self.assertEqual(len(edits), 12)
        for row in edits:
            with self.subTest(week=row.week):
                draft = self._replay_draft(row)
                self.assertIsNotNone(draft)
                assert draft is not None
                leg = (draft.meta_json or {}).get("htf_leg_trace") or {}
                self.assertIn("expansion_extreme_price", leg)
                self.assertIn("expansion_extreme_time_ms", leg)
                self.assertIn("expansion_extreme_owner", leg)
                self.assertIn("opposite_anchor_price", leg)
                self.assertIn("opposite_anchor_time_ms", leg)

    def test_rh_not_bos_bar_unless_owner_bos_candle(self) -> None:
        for row in self._gold:
            if row.audit_action != "EDIT":
                continue
            with self.subTest(week=row.week):
                draft = self._replay_draft(row)
                self.assertIsNotNone(draft)
                assert draft is not None
                meta = draft.meta_json or {}
                leg = meta.get("htf_leg_trace") or {}
                owner = leg.get("expansion_extreme_owner")
                imp_h = meta.get("retracement_impulse_high")
                if (
                    draft.suggested_rh is not None
                    and imp_h is not None
                    and abs(float(draft.suggested_rh) - float(imp_h)) <= PRICE_TOLERANCE
                ):
                    self.assertEqual(
                        owner,
                        EXPANSION_OWNER_BOS_CANDLE,
                        f"{row.week}: RH equals BOS bar but owner is {owner}",
                    )

    def test_rl_not_retrace_low_unless_opposite_anchor(self) -> None:
        for row in self._gold:
            if row.audit_action != "EDIT":
                continue
            with self.subTest(week=row.week):
                draft = self._replay_draft(row)
                self.assertIsNotNone(draft)
                assert draft is not None
                meta = draft.meta_json or {}
                leg = meta.get("htf_leg_trace") or {}
                opp = leg.get("opposite_anchor_price")
                imp_l = meta.get("retracement_impulse_low")
                if (
                    draft.suggested_rl is not None
                    and imp_l is not None
                    and opp is not None
                    and abs(float(draft.suggested_rl) - float(imp_l)) <= PRICE_TOLERANCE
                    and abs(float(draft.suggested_rl) - float(opp)) > PRICE_TOLERANCE
                ):
                    self.fail(
                        f"{row.week}: RL equals retrace low {imp_l} but not opposite anchor {opp}"
                    )

    def test_edit_weeks_match_josh_gold_rh_rl(self) -> None:
        rh_hits = 0
        rl_hits = 0
        full_hits = 0
        edits = [r for r in self._gold if r.audit_action == "EDIT"]
        for row in edits:
            with self.subTest(week=row.week):
                draft = self._replay_draft(row)
                self.assertIsNotNone(draft)
                assert draft is not None
                rh_ok = _price_close(draft.suggested_rh, row.josh_rh)
                rl_ok = _price_close(draft.suggested_rl, row.josh_rl)
                if rh_ok:
                    rh_hits += 1
                if rl_ok:
                    rl_hits += 1
                if rh_ok and rl_ok:
                    full_hits += 1
                _assert_price_close(self, "RH", draft.suggested_rh, row.josh_rh, week=row.week)
                _assert_price_close(self, "RL", draft.suggested_rl, row.josh_rl, week=row.week)
        self.assertEqual(len(edits), 12)


class DetectorAuditRegressionTests(unittest.TestCase):
    """Replay + detector vs Josh gold labels (expected failures = baseline)."""

    _candles: list[dict] | None = None
    _gold: list[AuditWeekRow] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls._gold = build_gold_rows()
        cls._candles = _load_xauusd_w1_candles()

    def setUp(self) -> None:
        if self._candles is None:
            self.skipTest("XAUUSD W1 candles unavailable in local candle_store DB")

    def test_replay_produces_range_candidate_each_week(self) -> None:
        for row in self._gold:
            with self.subTest(week=row.week):
                ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                self.assertIsNotNone(draft, f"{row.week}: no RANGE_CANDIDATE draft")

    def test_replay_improved_vs_frozen_fixture_baseline(self) -> None:
        """Post-leg detector should differ from pre-leg frozen fixture on most EDIT weeks."""
        edits = [r for r in self._gold if r.audit_action == "EDIT"]
        improved = 0
        for row in edits:
            with self.subTest(week=row.week):
                ctx, _ = replay_context_for_week(all_candles=self._candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                self.assertIsNotNone(draft)
                assert draft is not None
                rh_changed = not _price_close(draft.suggested_rh, row.detector_rh)
                rl_changed = not _price_close(draft.suggested_rl, row.detector_rl)
                if rh_changed or rl_changed:
                    improved += 1
        self.assertGreaterEqual(improved, 8, "leg doctrine should change most EDIT-week boundaries")


if __name__ == "__main__":
    unittest.main()
