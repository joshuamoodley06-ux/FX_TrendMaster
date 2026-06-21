"""Reviewed-truth seed policy for historical range scan."""

from __future__ import annotations

import gc
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_promotion import review_suggestion
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import DetectorSuggestion, insert_suggestion, utc_now_ms
from detector.models import DetectionContext
from detector.range_seed import (
    SEED_SOURCE_PROMOTED_RANGE,
    SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE,
    load_latest_promoted_range_seed,
)
from detector.range_state import RangeSeedContext
from detector.range_step_seed import (
    SEED_POLICY_DEFAULT,
    SEED_POLICY_REVIEWED_TRUTH_ONLY,
    resolve_historical_scan_step_seed,
)
from detector.versions import ENGINE_SOURCE, RANGE_V2
from tests.test_historical_range_chain import _chain_fixture_rows, _candles_from_rows


def _ctx_at(index: int) -> DetectionContext:
    candles = _candles_from_rows(_chain_fixture_rows())
    return DetectionContext(
        symbol="XAUUSD",
        source_timeframe="W1",
        structure_layer="WEEKLY",
        candles=candles,
        active_index=index,
        replay_until_time_ms=candles[index].time_ms,
    )


def _insert_suggestion(
    conn: sqlite3.Connection,
    *,
    suggestion_id: str,
    candle_time_ms: int,
    rh: float,
    rl: float,
    status: str = "PENDING",
) -> None:
    now = utc_now_ms()
    insert_suggestion(
        conn,
        DetectorSuggestion(
            suggestion_id=suggestion_id,
            detector_version=RANGE_V2,
            engine_source=ENGINE_SOURCE,
            candidate_kind="RANGE_CANDIDATE",
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            chart_timeframe="W1",
            candle_time_utc_ms=candle_time_ms,
            created_at_utc_ms=now,
            suggested_rh=rh,
            suggested_rl=rl,
            suggested_rh_time_ms=candle_time_ms,
            suggested_rl_time_ms=candle_time_ms - 86_400_000 * 7,
            range_scale="UNKNOWN",
            status=status,
        ),
    )
    if status != "PENDING":
        conn.execute(
            "UPDATE detector_suggestions SET status = ? WHERE suggestion_id = ?",
            (status, suggestion_id),
        )
    conn.commit()


def _promote_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    action: str = "APPROVE",
    edits: dict | None = None,
) -> int:
    out = review_suggestion(conn, suggestion_id, action=action, edits=edits)
    conn.commit()
    range_id = out.get("promoted_range_id")
    assert range_id is not None
    return int(range_id)


class PromotedRangeSeedLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / f"_seed_policy_{uuid.uuid4().hex}.db"
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.candles = _candles_from_rows(_chain_fixture_rows())
        self.t5 = self.candles[5].time_ms
        self.t8 = self.candles[8].time_ms

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def test_approved_map_range_is_promoted_seed(self) -> None:
        _insert_suggestion(self.conn, suggestion_id="sug-a", candle_time_ms=self.t5, rh=110.0, rl=95.0)
        _promote_suggestion(self.conn, "sug-a", action="APPROVE")
        result = load_latest_promoted_range_seed(
            self.conn,
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            before_replay_time_ms=self.t8,
        )
        self.assertIsNotNone(result.seed)
        assert result.seed is not None
        self.assertEqual(result.seed_source, SEED_SOURCE_PROMOTED_RANGE)
        self.assertAlmostEqual(result.seed.range_high, 110.0)
        self.assertAlmostEqual(result.seed.range_low, 95.0)

    def test_edited_map_range_beats_raw_temp_seed(self) -> None:
        _insert_suggestion(self.conn, suggestion_id="sug-e", candle_time_ms=self.t5, rh=110.0, rl=95.0)
        _promote_suggestion(
            self.conn,
            "sug-e",
            action="EDIT",
            edits={"suggested_rh": 112.5, "suggested_rl": 94.0},
        )
        ctx = _ctx_at(8)
        temp = RangeSeedContext(range_high=106.0, range_low=99.0)
        resolved = resolve_historical_scan_step_seed(
            ctx,
            conn=self.conn,
            seed_policy=SEED_POLICY_REVIEWED_TRUTH_ONLY,
            temp_working_seed=temp,
            period_start_ms=None,
            structure_layer="WEEKLY",
            parent_range_id=None,
            scan_chain_index=2,
        )
        self.assertEqual(resolved.seed_source, SEED_SOURCE_PROMOTED_RANGE)
        assert resolved.seed is not None
        self.assertAlmostEqual(resolved.seed.range_high, 112.5)
        self.assertAlmostEqual(resolved.seed.range_low, 94.0)

    def test_rejected_suggestion_never_seeds(self) -> None:
        _insert_suggestion(self.conn, suggestion_id="sug-r", candle_time_ms=self.t5, rh=110.0, rl=95.0)
        review_suggestion(
            self.conn,
            "sug-r",
            action="REJECT",
            error_category="WRONG_RH",
            notes="bad",
        )
        self.conn.commit()
        result = load_latest_promoted_range_seed(
            self.conn,
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            before_replay_time_ms=self.t8,
        )
        self.assertIsNone(result.seed)

    def test_temp_previous_candidate_when_no_promoted_truth(self) -> None:
        ctx = _ctx_at(8)
        temp = RangeSeedContext(range_high=106.0, range_low=99.0)
        resolved = resolve_historical_scan_step_seed(
            ctx,
            conn=self.conn,
            seed_policy=SEED_POLICY_REVIEWED_TRUTH_ONLY,
            temp_working_seed=temp,
            period_start_ms=None,
            structure_layer="WEEKLY",
            parent_range_id=None,
            scan_chain_index=1,
        )
        self.assertEqual(resolved.seed_source, SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE)
        assert resolved.seed is not None
        self.assertAlmostEqual(resolved.seed.range_high, 106.0)

    def test_default_policy_traces_temp_not_previous_range_candidate(self) -> None:
        ctx = _ctx_at(8)
        temp = RangeSeedContext(range_high=106.0, range_low=99.0)
        resolved = resolve_historical_scan_step_seed(
            ctx,
            conn=self.conn,
            seed_policy=SEED_POLICY_DEFAULT,
            temp_working_seed=temp,
            period_start_ms=None,
            structure_layer="WEEKLY",
            parent_range_id=None,
            scan_chain_index=1,
        )
        self.assertEqual(resolved.seed_source, SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE)
        self.assertEqual(resolved.meta.get("seed_source"), SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE)


if __name__ == "__main__":
    unittest.main()
