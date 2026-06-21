"""CLI wiring for historical_range_scan --seed-policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import historical_range_scan as scan_cli
from detector.range_seed import SEED_POLICY_DEFAULT, SEED_POLICY_REVIEWED_TRUTH_ONLY
from detector.range_scan_runner import HistoricalRangeScanConfig, HistoricalRangeScanResult


def _mock_scan_result() -> HistoricalRangeScanResult:
    return HistoricalRangeScanResult(
        symbol="XAUUSD",
        source_timeframe="W1",
        structure_layer="WEEKLY",
        date_from_ms=1_735_689_600_000,
        date_to_ms=1_767_225_600_000,
        detection_run_id="test-run",
        candles_scanned=1,
        suggestions_created=0,
        dry_run=True,
    )


class HistoricalRangeScanCliSeedPolicyTests(unittest.TestCase):
    def test_parser_default_seed_policy(self) -> None:
        args = scan_cli.build_parser().parse_args(
            ["--from", "2025-01-01", "--to", "2025-12-31"],
        )
        self.assertEqual(args.seed_policy, SEED_POLICY_DEFAULT)

    def test_parser_reviewed_truth_only_flag(self) -> None:
        args = scan_cli.build_parser().parse_args(
            [
                "--from",
                "2025-01-01",
                "--to",
                "2025-12-31",
                "--seed-policy",
                SEED_POLICY_REVIEWED_TRUTH_ONLY,
            ],
        )
        self.assertEqual(args.seed_policy, SEED_POLICY_REVIEWED_TRUTH_ONLY)

    @patch("historical_range_scan.run_historical_range_scan", return_value=_mock_scan_result())
    def test_main_default_seed_policy_unchanged(self, mock_run) -> None:
        rc = scan_cli.main(
            [
                "--from",
                "2025-01-01",
                "--to",
                "2025-01-31",
                "--dry-run",
            ],
        )
        self.assertEqual(rc, 0)
        _conn, config = mock_run.call_args[0]
        self.assertIsInstance(config, HistoricalRangeScanConfig)
        self.assertEqual(config.seed_policy, SEED_POLICY_DEFAULT)

    @patch("historical_range_scan.run_historical_range_scan", return_value=_mock_scan_result())
    def test_main_passes_seed_policy_to_scan_config(self, mock_run) -> None:
        rc = scan_cli.main(
            [
                "--from",
                "2025-01-01",
                "--to",
                "2025-01-31",
                "--dry-run",
                "--seed-policy",
                SEED_POLICY_REVIEWED_TRUTH_ONLY,
            ],
        )
        self.assertEqual(rc, 0)
        _conn, config = mock_run.call_args[0]
        self.assertIsInstance(config, HistoricalRangeScanConfig)
        self.assertEqual(config.seed_policy, SEED_POLICY_REVIEWED_TRUTH_ONLY)


if __name__ == "__main__":
    unittest.main()
