"""Pull closed OHLC from MT5 into market_memory DB. Raw candles only — no structure."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover
    mt5 = None  # type: ignore

import candle_store

TF_MAP: dict[str, int] = {}
if mt5 is not None:
    TF_MAP = {
        "MN1": mt5.TIMEFRAME_MN1,
        "W1": mt5.TIMEFRAME_W1,
        "D1": mt5.TIMEFRAME_D1,
        "H4": mt5.TIMEFRAME_H4,
        "H1": mt5.TIMEFRAME_H1,
        "M15": mt5.TIMEFRAME_M15,
        "M5": mt5.TIMEFRAME_M5,
    }

DEFAULT_TIMEFRAMES = ["MN1", "W1", "D1", "H4", "H1", "M15"]

# Deep history on first sync / when DB is thin.
BACKFILL_BARS: dict[str, int] = {
    "MN1": 120,
    "W1": 600,
    "D1": 8000,
    "H4": 30000,
    "H1": 50000,
    "M15": 50000,
    "M5": 50000,
}

# Minimum rows before we treat a series as "warm enough" for incremental-only pulls.
MIN_WARM_BARS: dict[str, int] = {
    "MN1": 24,
    "W1": 104,
    "D1": 500,
    "H4": 1000,
    "H1": 2000,
    "M15": 2000,
    "M5": 2000,
}

# Latest-bar refresh every scheduler tick.
INCREMENTAL_BARS: dict[str, int] = {
    "MN1": 24,
    "W1": 52,
    "D1": 120,
    "H4": 500,
    "H1": 1000,
    "M15": 2000,
    "M5": 2000,
}

MT5_MAX_BARS = 100_000
SOURCE = "mt5-sync"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "enabled": os.environ.get("CANDLE_SYNC_ENABLED", "1").strip() not in {"0", "false", "False", "no"},
    "interval_sec": max(60, int(os.environ.get("CANDLE_SYNC_INTERVAL_SEC", "900") or 900)),
    "symbols": [s.strip() for s in os.environ.get("CANDLE_SYNC_SYMBOLS", "XAUUSD").split(",") if s.strip()],
    "timeframes": DEFAULT_TIMEFRAMES,
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_ok": None,
    "last_error": None,
    "last_result": None,
    "runs": 0,
}


def sync_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_mt5_time(ts: int | float) -> str:
    """Canonical DB time string (matches MT5 EA CSV exports)."""
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return dt.strftime("%Y.%m.%d %H:%M")


def _ensure_mt5() -> tuple[bool, str | None]:
    if mt5 is None:
        return False, "MetaTrader5 package not installed"
    if mt5.initialize():
        return True, None
    return False, f"MT5 initialize failed: {mt5.last_error()}"


def _db_stats(symbol: str, timeframe: str) -> dict[str, Any]:
    candle_store.init_db()
    tf = candle_store.normalise_timeframe(timeframe)
    with candle_store.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count, MIN(time) AS first_time, MAX(time) AS last_time
            FROM candles WHERE symbol=? AND timeframe=?
            """,
            (symbol, tf),
        ).fetchone()
    return dict(row) if row else {"count": 0, "first_time": None, "last_time": None}


def _rates_to_rows(rates: Any, symbol: str, timeframe: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in rates or []:
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "time": format_mt5_time(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r.get("tick_volume") or r.get("real_volume") or 0),
            }
        )
    return rows


def _resolve_bar_count(timeframe: str, db_count: int, *, force_backfill: bool = False) -> tuple[int, str]:
    tf = candle_store.normalise_timeframe(timeframe)
    warm = MIN_WARM_BARS.get(tf, 500)
    if force_backfill or db_count < warm:
        return min(BACKFILL_BARS.get(tf, 5000), MT5_MAX_BARS), "backfill"
    return min(INCREMENTAL_BARS.get(tf, 500), MT5_MAX_BARS), "incremental"


def sync_symbol_timeframe(
    symbol: str,
    timeframe: str,
    *,
    force_backfill: bool = False,
) -> dict[str, Any]:
    tf = candle_store.normalise_timeframe(timeframe)
    if tf not in TF_MAP:
        return {"ok": False, "symbol": symbol, "timeframe": tf, "error": f"Unsupported timeframe for MT5 sync: {tf}"}

    ok, err = _ensure_mt5()
    if not ok:
        return {"ok": False, "symbol": symbol, "timeframe": tf, "error": err}

    if not mt5.symbol_select(symbol, True):
        return {"ok": False, "symbol": symbol, "timeframe": tf, "error": f"MT5 symbol_select failed: {mt5.last_error()}"}

    before = _db_stats(symbol, tf)
    db_count = int(before.get("count") or 0)
    bar_count, mode = _resolve_bar_count(tf, db_count, force_backfill=force_backfill)

    rates = mt5.copy_rates_from_pos(symbol, TF_MAP[tf], 0, bar_count)
    if rates is None:
        return {
            "ok": False,
            "symbol": symbol,
            "timeframe": tf,
            "mode": mode,
            "error": f"No MT5 candles: {mt5.last_error()}",
        }

    rows = _rates_to_rows(rates, symbol, tf)
    upsert = candle_store.upsert_candles(rows, source=SOURCE)
    after = _db_stats(symbol, tf)

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": tf,
        "mode": mode,
        "requested_bars": bar_count,
        "fetched_bars": len(rows),
        "db_before": before,
        "db_after": after,
        "upsert": upsert,
    }


def sync_all(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    *,
    force_backfill: bool = False,
) -> dict[str, Any]:
    syms = [s.strip() for s in (symbols or _state["symbols"]) if s and s.strip()]
    tfs = [candle_store.normalise_timeframe(t) for t in (timeframes or _state["timeframes"])]
    started = _utc_now_iso()
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    if mt5 is None:
        out = {"ok": False, "started_at": started, "finished_at": _utc_now_iso(), "error": "MetaTrader5 not available", "results": []}
        with _lock:
            _state["last_result"] = out
            _state["last_ok"] = False
            _state["last_error"] = out["error"]
            _state["last_finished_at"] = out["finished_at"]
        return out

    for symbol in syms:
        for tf in tfs:
            try:
                row = sync_symbol_timeframe(symbol, tf, force_backfill=force_backfill)
            except Exception as exc:
                row = {"ok": False, "symbol": symbol, "timeframe": tf, "error": repr(exc)}
            results.append(row)
            if not row.get("ok"):
                errors.append(f"{symbol}/{tf}: {row.get('error')}")

    finished = _utc_now_iso()
    out = {
        "ok": not errors,
        "started_at": started,
        "finished_at": finished,
        "symbols": syms,
        "timeframes": tfs,
        "force_backfill": force_backfill,
        "results": results,
        "errors": errors,
        "db": str(candle_store.DB_PATH),
    }
    with _lock:
        _state["last_result"] = out
        _state["last_ok"] = out["ok"]
        _state["last_error"] = errors[0] if errors else None
        _state["last_finished_at"] = finished
        _state["runs"] = int(_state.get("runs") or 0) + 1
    return out


def ensure_fresh(
    symbol: str,
    timeframe: str,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Pull latest MT5 bars into DB when the stored series is stale. Returns sync row or None."""
    tf = candle_store.normalise_timeframe(timeframe)
    stats = _db_stats(symbol, tf)
    db_count = int(stats.get("count") or 0)
    last_time = stats.get("last_time")
    if not force and db_count > 0 and not _is_stale(tf, last_time):
        return None
    return sync_symbol_timeframe(symbol, tf, force_backfill=force or db_count < MIN_WARM_BARS.get(tf, 500))


def _is_stale(timeframe: str, last_time: str | None) -> bool:
    if not last_time:
        return True
    try:
        dt = datetime.strptime(str(last_time).strip(), "%Y.%m.%d %H:%M").replace(tzinfo=timezone.utc)
    except Exception:
        return True
    age_sec = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    tf = candle_store.normalise_timeframe(timeframe)
    thresholds = {
        "M5": 6 * 60,
        "M15": 20 * 60,
        "H1": 70 * 60,
        "H4": 5 * 3600,
        "D1": 26 * 3600,
        "W1": 8 * 86400,
        "MN1": 35 * 86400,
    }
    return age_sec > thresholds.get(tf, 3600)


def run_scheduled_sync(
    *,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    force_backfill: bool = False,
) -> dict[str, Any]:
    with _lock:
        if _state.get("running"):
            return {"ok": False, "skipped": True, "reason": "sync already running"}
        _state["running"] = True
        _state["last_started_at"] = _utc_now_iso()
    try:
        return sync_all(symbols=symbols, timeframes=timeframes, force_backfill=force_backfill)
    finally:
        with _lock:
            _state["running"] = False
