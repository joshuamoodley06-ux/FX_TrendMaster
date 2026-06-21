"""Tests for candle_store DB_PATH normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store


class CandleStoreDbPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_path = candle_store.DB_PATH

    def tearDown(self) -> None:
        candle_store.DB_PATH = self.old_path

    def test_ensure_db_path_coerces_string_assignment(self) -> None:
        candle_store.DB_PATH = r"C:\Users\test\Documents\FXTM_Research\raw_mapping_v159.db"
        path = candle_store.ensure_db_path()
        self.assertIsInstance(candle_store.DB_PATH, Path)
        self.assertIsInstance(path, Path)
        self.assertTrue(path.parent.name == "FXTM_Research")


if __name__ == "__main__":
    unittest.main()
