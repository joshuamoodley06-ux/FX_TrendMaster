"""Candle list to pandas DataFrame helpers."""

from __future__ import annotations

import pandas as pd

from analyst.models.records import Candle, InputPackage

CANDLE_COLUMNS = ["symbol", "timeframe", "time_ms", "open", "high", "low", "close", "volume"]


def candles_to_frame(candles: list[Candle]) -> pd.DataFrame:
    rows = [
        {
            "symbol": c.symbol,
            "timeframe": c.timeframe,
            "time_ms": c.time_ms,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    frame = pd.DataFrame(rows, columns=CANDLE_COLUMNS)
    return frame.sort_values("time_ms", kind="stable").reset_index(drop=True)


def frames_by_timeframe(package: InputPackage) -> dict[str, pd.DataFrame]:
    return {tf: candles_to_frame(rows) for tf, rows in package.candles.items()}
