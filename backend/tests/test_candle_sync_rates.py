from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_sync


class AmbiguousRates:
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def __bool__(self):
        raise ValueError("ambiguous truth value")


def test_rates_to_rows_does_not_truth_test_array_like_rates():
    rates = AmbiguousRates([
        {
            "time": 1_704_067_200,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 12,
        }
    ])

    rows = candle_sync._rates_to_rows(rates, "XAUUSD", "H1")

    assert rows == [
        {
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "time": "2024.01.01 00:00",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 12,
        }
    ]


def test_rates_to_rows_supports_numpy_structured_rows_without_get():
    numpy = pytest.importorskip("numpy")
    rates = numpy.array(
        [
            (
                1_704_067_200,
                1.0,
                2.0,
                0.5,
                1.5,
                12,
                3,
                4,
            )
        ],
        dtype=[
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i8"),
            ("real_volume", "i8"),
        ],
    )

    rows = candle_sync._rates_to_rows(rates, "XAUUSD", "H1")

    assert rows == [
        {
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "time": "2024.01.01 00:00",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 12,
        }
    ]


def test_rates_to_rows_still_supports_dict_rows_and_real_volume_fallback():
    rates = AmbiguousRates([
        {
            "time": 1_704_067_200,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "real_volume": 7,
        }
    ])

    rows = candle_sync._rates_to_rows(rates, "XAUUSD", "H1")

    assert rows[0]["volume"] == 7


def test_rates_to_rows_handles_none_and_empty_rates():
    assert candle_sync._rates_to_rows(None, "XAUUSD", "H1") == []
    assert candle_sync._rates_to_rows(AmbiguousRates([]), "XAUUSD", "H1") == []
