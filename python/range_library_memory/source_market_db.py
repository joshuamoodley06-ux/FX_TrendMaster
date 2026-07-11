"""Read-only adapter for the original FXTM market memory database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
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
    start = parse_source_timestamp(start_time, symbol=symbol, timeframe=timeframe)
    end = parse_source_timestamp(end_time, symbol=symbol, timeframe=timeframe)
    rows = connection.execute(
        f"""
        SELECT rowid AS source_rowid,
               {columns['symbol']} AS symbol,
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
        ORDER BY source_rowid ASC
        """,
        (symbol, timeframe),
    ).fetchall()
    candles: list[tuple[datetime, int, SourceCandle]] = []
    for row in rows:
        parsed_time = parse_source_timestamp(
            str(row["candle_time"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
        )
        if parsed_time < start or parsed_time > end:
            continue
        candles.append(
            (
                parsed_time,
                int(row["source_rowid"]),
                SourceCandle(
                    symbol=str(row["symbol"]),
                    timeframe=str(row["timeframe"]),
                    time=format_canonical_time(parsed_time),
                    open=float(row["open_price"]),
                    high=float(row["high_price"]),
                    low=float(row["low_price"]),
                    close=float(row["close_price"]),
                    volume=float(row["volume"]) if row["volume"] is not None else None,
                    source=str(row["source"]) if row["source"] is not None else None,
                ),
            )
        )
    return [candle for _parsed, _rowid, candle in sorted(candles, key=lambda item: (item[0], item[1]))]


def latest_candle_time(connection: sqlite3.Connection, *, symbol: str, timeframe: str) -> str | None:
    columns = candle_columns(connection)
    rows = connection.execute(
        f"""
        SELECT rowid AS source_rowid,
               {columns['symbol']} AS symbol,
               {columns['timeframe']} AS timeframe,
               {columns['time']} AS candle_time
        FROM candles
        WHERE {columns['symbol']} = ?
          AND {columns['timeframe']} = ?
        ORDER BY source_rowid ASC
        """,
        (symbol, timeframe),
    ).fetchall()
    latest: datetime | None = None
    for row in rows:
        parsed = parse_source_timestamp(
            str(row["candle_time"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
        )
        latest = parsed if latest is None or parsed > latest else latest
    return format_canonical_time(latest) if latest else None


def parse_source_timestamp(value: str, *, symbol: str, timeframe: str) -> datetime:
    raw = str(value).strip()
    for pattern in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    text = raw
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SourceMarketDbError(
            f"Could not parse candle timestamp for symbol={symbol} timeframe={timeframe}: {raw}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_canonical_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
