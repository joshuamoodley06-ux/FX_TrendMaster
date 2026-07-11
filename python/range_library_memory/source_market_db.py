"""Read-only adapter for the original FXTM market memory database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SourceMarketDbError(RuntimeError):
    """Raised when the source market database cannot be read safely."""


@dataclass(frozen=True)
class SourceCandle:
    symbol: str
    timeframe: str
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str | None


def open_source_market_db(source_db: str | Path) -> sqlite3.Connection:
    path = Path(source_db)
    if not path.is_file():
        raise SourceMarketDbError(f"Source database does not exist: {path}")

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
        except sqlite3.DatabaseError:
            pass
        require_source_tables(connection)
        return connection
    except Exception:
        connection.close()
        raise


def require_source_tables(connection: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        ).fetchall()
    }
    for table in ("candles", "map_ranges"):
        if table not in existing:
            raise SourceMarketDbError(f"Source database is missing required table: {table}")


def load_candles(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    timeframe: str,
    start_time: str,
    end_time: str,
) -> list[SourceCandle]:
    columns = candle_columns(connection)
    rows = connection.execute(
        f"""
        SELECT {columns['symbol']} AS symbol,
               {columns['timeframe']} AS timeframe,
               {columns['time']} AS candle_time,
               {columns['open']} AS open_price,
               {columns['high']} AS high_price,
               {columns['low']} AS low_price,
               {columns['close']} AS close_price,
               {columns['volume']} AS volume,
               {columns['source']} AS source
        FROM candles
        WHERE {columns['symbol']} = ?
          AND {columns['timeframe']} = ?
          AND {columns['time']} >= ?
          AND {columns['time']} <= ?
        ORDER BY {columns['time']} ASC
        """,
        (symbol, timeframe, start_time, end_time),
    ).fetchall()
    return [
        SourceCandle(
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
            time=str(row["candle_time"]),
            open=float(row["open_price"]),
            high=float(row["high_price"]),
            low=float(row["low_price"]),
            close=float(row["close_price"]),
            volume=float(row["volume"]) if row["volume"] is not None else None,
            source=str(row["source"]) if row["source"] is not None else None,
        )
        for row in rows
    ]


def candle_columns(connection: sqlite3.Connection) -> dict[str, str]:
    available = {row["name"] for row in connection.execute("PRAGMA table_info(candles)").fetchall()}
    required = {
        "symbol": ("symbol",),
        "timeframe": ("timeframe", "source_timeframe"),
        "time": ("time", "candle_time", "timestamp"),
        "open": ("open", "open_price"),
        "high": ("high", "high_price"),
        "low": ("low", "low_price"),
        "close": ("close", "close_price"),
    }
    resolved: dict[str, str] = {}
    for target, candidates in required.items():
        match = first_available(available, candidates)
        if match is None:
            raise SourceMarketDbError(f"Source candles table is missing required column for: {target}")
        resolved[target] = quote_identifier(match)

    volume = first_available(available, ("volume",))
    source = first_available(available, ("source", "feed_source"))
    resolved["volume"] = quote_identifier(volume) if volume else "NULL"
    resolved["source"] = quote_identifier(source) if source else "NULL"
    return resolved


def first_available(available: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
