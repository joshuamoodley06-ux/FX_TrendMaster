from fastapi import FastAPI, Body, Response
from fastapi.middleware.cors import CORSMiddleware
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
import re
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
from trading_gate.models import HTFInput, DailyInput, IntradayInput
from trading_gate.app.schemas import HTFOutput
from trading_gate.app.schemas_intraday import IntradayOutput
from trading_gate.app.engine import TradingGateEngine
from trading_gate.app.intraday_engine import IntradayEngine
from trading_gate.app.state_store import load_state, save_state

# Optional backend helpers used by Android execution / journal / bridge.
# These imports stay soft so the API can still boot while one helper file is being replaced.
try:
    from mt5_bridge import (
        write_execute_command,
        read_live_trade_status,
        read_trade_result,
        bridge_status as mt5_bridge_status,
        write_close_half_command,
        write_close_full_command,
        read_heartbeat,
    )
except Exception:  # pragma: no cover - runtime safety on VPS
    write_execute_command = None
    read_live_trade_status = None
    read_trade_result = None
    mt5_bridge_status = None
    write_close_half_command = None
    write_close_full_command = None
    read_heartbeat = None

try:
    from journal import (
        log_event,
        daily_budget_summary,
        log_execute_sent,
        log_management_event,
    )
except Exception:  # pragma: no cover - runtime safety on VPS
    log_event = None
    daily_budget_summary = None
    log_execute_sent = None
    log_management_event = None

try:
    from sql_journal import (
        init_db as sql_init_db,
        db_status as sql_db_status,
        log_execute_attempt as sql_log_execute_attempt,
        log_trade_opened as sql_log_trade_opened,
        log_trade_event as sql_log_trade_event,
        log_blocked_attempt as sql_log_blocked_attempt,
        log_context_snapshot as sql_log_context_snapshot,
        log_backtest_sample as sql_log_backtest_sample,
        recent_trades as sql_recent_trades,
        recent_events as sql_recent_events,
        recent_blocked as sql_recent_blocked,
        recent_context as sql_recent_context,
        recent_backtest_samples as sql_recent_backtest_samples,
        log_execution_event_flat as sql_log_execution_event_flat,
        events_for_trade as sql_events_for_trade,
        trade_context as sql_trade_context,
        get_event_by_idempotency_key as sql_get_event_by_idempotency_key,
        trade_idea_risk_total as sql_trade_idea_risk_total,
        save_map_state_structured as sql_save_map_state_structured,
        save_lifecycle_snapshot_structured as sql_save_lifecycle_snapshot_structured,
        save_trade_idea_structured as sql_save_trade_idea_structured,
        journal_report_summary as sql_journal_report_summary,
        recent_structured_journal as sql_recent_structured_journal,
        save_trade_memory_record as sql_save_trade_memory_record,
        detailed_trade_rows as sql_detailed_trade_rows,
        trade_detail as sql_trade_detail,
        update_trade_memory_record as sql_update_trade_memory_record,
        save_lifecycle_scenario_test as sql_save_lifecycle_scenario_test,
        save_historical_lifecycle_bundle as sql_save_historical_lifecycle_bundle,
        historical_lifecycle_bundles as sql_historical_lifecycle_bundles,
        resolve_context_by_date as sql_resolve_context_by_date,
    )
    sql_init_db()
except Exception:  # pragma: no cover - runtime safety on VPS
    sql_init_db = None
    sql_db_status = None
    sql_log_execute_attempt = None
    sql_log_trade_opened = None
    sql_log_trade_event = None
    sql_log_blocked_attempt = None
    sql_log_context_snapshot = None
    sql_log_backtest_sample = None
    sql_recent_trades = None
    sql_recent_events = None
    sql_recent_blocked = None
    sql_recent_context = None
    sql_recent_backtest_samples = None
    sql_log_execution_event_flat = None
    sql_events_for_trade = None
    sql_trade_context = None
    sql_get_event_by_idempotency_key = None
    sql_trade_idea_risk_total = None
    sql_save_map_state_structured = None
    sql_save_lifecycle_snapshot_structured = None
    sql_save_trade_idea_structured = None
    sql_journal_report_summary = None
    sql_recent_structured_journal = None
    sql_save_trade_memory_record = None
    sql_detailed_trade_rows = None
    sql_trade_detail = None
    sql_update_trade_memory_record = None
    sql_save_lifecycle_scenario_test = None
    sql_save_historical_lifecycle_bundle = None
    sql_historical_lifecycle_bundles = None
    sql_resolve_context_by_date = None


try:
    from lifecycle_engine.reducer import reduce_trade_state
    from lifecycle_engine.compliance import check_compliance_violation
    from lifecycle_engine.close_lock import close_lock_unlock_threshold
except Exception:  # pragma: no cover - runtime safety on VPS
    reduce_trade_state = None
    check_compliance_violation = None
    close_lock_unlock_threshold = None


try:
    from trading_gate.app.risk_guard import (
        daily_lock_summary,
        validate_execution_allowed,
        record_execution_utilised,
    )
except Exception:  # pragma: no cover - runtime safety on VPS
    daily_lock_summary = None
    validate_execution_allowed = None
    record_execution_utilised = None

app = FastAPI(title="Trading Gate HTF + Intraday Module")

# CORS for Electron/Vite development and local desktop cockpit access.
# Keep this explicit instead of using "*" so the VPS does not become a public buffet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "app://.",
        "file://",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SUPPORTED_SYMBOLS = {"XAUUSD", "US500.cash", "US100.cash", "US30.cash"}


PRICE_CACHE_FILE = Path(__file__).resolve().parent / "price_cache.json"
NOTIFICATION_STATE_FILE = Path(__file__).resolve().parent / "notification_state.json"
MAP_STATE_FILE = Path(__file__).resolve().parent / "map_state_store.json"


def _now_sast_iso() -> str:
    return datetime.now(timezone(timedelta(hours=2))).isoformat(timespec="seconds")


def _load_price_cache() -> dict[str, Any]:
    try:
        if PRICE_CACHE_FILE.exists():
            raw = PRICE_CACHE_FILE.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_price_cache(cache: dict[str, Any]) -> None:
    try:
        PRICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PRICE_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass



def _load_map_state_store() -> dict[str, Any]:
    try:
        if MAP_STATE_FILE.exists():
            raw = MAP_STATE_FILE.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_map_state_store(store: dict[str, Any]) -> None:
    try:
        MAP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        MAP_STATE_FILE.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _normalise_symbol(symbol: str) -> str:
    symbol = (symbol or "XAUUSD").strip()
    return symbol if symbol in SUPPORTED_SYMBOLS else "XAUUSD"


def _ensure_mt5_ready() -> tuple[bool, str | None]:
    """Initialise the local MT5 terminal for live price reads and trade management."""
    if mt5.initialize():
        return True, None
    return False, f"MT5 initialize failed: {mt5.last_error()}"


def _get_mt5_tick(symbol: str):
    """Select symbol if needed and return its latest MT5 tick."""
    if not mt5.symbol_select(symbol, True):
        return None, f"MT5 symbol_select failed for {symbol}: {mt5.last_error()}"

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None, f"No tick data for {symbol}: {mt5.last_error()}"

    return tick, None


@app.get("/")
def home():
    return {"message": "Trading Gate HTF + Intraday Module is alive"}


def _as_percent(value, fallback=50.0) -> float:
    try:
        if value is None:
            return fallback
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _format_label(value) -> str:
    if value is None:
        return "Unknown"
    return str(value).replace("_", " ").title()


def _default_layer(symbol: str, layer: str, fib: float = 50.0) -> dict:
    return {
        "symbol": symbol,
        "layer": layer,
        "framework": "waiting",
        "fib_position": fib,
        "location": "unknown",
        "location_label": "Unknown",
        "trajectory": "neutral",
        "trajectory_start_percent": fib,
        "discount_touch_state": "fresh",
        "premium_touch_state": "fresh",
        "current_state": f"{layer.upper()}: Waiting for saved inputs",
    }


def _normalise_htf_output(output: HTFOutput) -> dict:
    return {
        "symbol": output.symbol,
        "layer": output.layer.value,
        "framework": output.framework.value,
        "fib_position": _as_percent(output.fib_position_percent),
        "location": output.location.value,
        "location_label": _format_label(output.location.value),
        "trajectory": output.trajectory.value,
        "trajectory_start_percent": _as_percent(output.trajectory_start_percent * 100.0),
        "current_state": output.current_state,
    }


def _normalise_intraday_output(output: IntradayOutput) -> dict:
    execution_allowed = bool(output.reversal_allowed or output.continuation_allowed)
    return {
        "symbol": output.symbol,
        "direction": output.direction.value,
        "phase": output.phase_state.value,
        "phase_label": _format_label(output.phase_state.value),
        "profile": output.profile_state.value,
        "profile_label": output.profile_state.value.upper(),
        "retrace_percent": output.retrace_percent,
        "trade_type": output.trade_type.value,
        "reversal_allowed": output.reversal_allowed,
        "continuation_armed": output.continuation_armed,
        "continuation_allowed": output.continuation_allowed,
        "execution_allowed": execution_allowed,
        "blocked_reason": output.blocked_reason,
        "phase_reasons": output.phase_reasons,
        "current_state": output.current_state,
    }


def _read_symbol_state(symbol: str) -> dict:
    state = load_state()
    symbols = state.get("symbols", {})
    return symbols.get(symbol, {})


def _write_symbol_state(symbol: str, key: str, payload: dict) -> None:
    state = load_state()
    state.setdefault("symbols", {})
    state["symbols"].setdefault(symbol, {})
    state["symbols"][symbol][key] = payload
    save_state(state)


@app.post("/analyze-htf", response_model=HTFOutput)
def analyze_htf(payload: dict = Body(...)):
    data = DailyInput(**payload) if payload.get("layer") == "daily" else HTFInput(**payload)
    result = TradingGateEngine.classify_htf(data)

    symbol_state_key = f"{data.layer.value}_input"
    _write_symbol_state(data.symbol, symbol_state_key, payload)
    return result


@app.post("/analyze-intraday", response_model=IntradayOutput)
def analyze_intraday(payload: dict = Body(...)):
    data = IntradayInput(**payload)
    result = IntradayEngine.analyze(data)

    _write_symbol_state(data.symbol, "intraday_input", payload)
    return result


@app.post("/set-intraday")
def set_intraday(payload: dict = Body(...)):
    """
    Mobile cockpit manual intraday update.

    This stores Josh's discretionary intraday state from Android:
    direction, session, sweep, CHoCH, phase, profile, trade type, entry model, and notes.
    """
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))

    intraday_payload = {
        "symbol": symbol,
        "direction": payload.get("direction", "neutral"),
        "session": payload.get("session", "London"),
        "sweep": payload.get("sweep", "None"),
        "choch_confirmed": bool(payload.get("choch_confirmed", False)),
        "phase": payload.get("phase", "None"),
        "profile": payload.get("profile", "S&D"),
        "trade_type": payload.get("trade_type", "Daily Correction P2"),
        "entry_model": payload.get("entry_model", "15m CHoCH S&D"),
        "notes": payload.get("notes", ""),
        "updated_at": datetime.utcnow().isoformat(),
    }

    _write_symbol_state(symbol, "mobile_intraday", intraday_payload)

    return {
        "status": "ok",
        "message": "Intraday state saved",
        "symbol": symbol,
        "intraday": intraday_payload,
    }


# =============================
# SESSION DETECTION - SAST
# =============================
def _detect_session(now: datetime | None = None) -> dict[str, Any]:
    """Auto-detect trading session using South African time (SAST / UTC+2).

    Designed for quick cockpit context, not exchange-official settlement timing.
    """
    now = now or datetime.now(SAST)
    minutes = now.hour * 60 + now.minute

    if 0 <= minutes < 9 * 60:
        session = "ASIA"
        phase = "Asia / pre-London"
    elif 9 * 60 <= minutes < 14 * 60:
        session = "LONDON"
        phase = "London session"
    elif 14 * 60 <= minutes < 15 * 60 + 30:
        session = "NY AM"
        phase = "New York pre-NYSE"
    elif 15 * 60 + 30 <= minutes < 19 * 60:
        session = "NYSE"
        phase = "NYSE active"
    elif 19 * 60 <= minutes < 22 * 60:
        session = "NY PM"
        phase = "New York afternoon"
    else:
        session = "AFTER HOURS"
        phase = "After hours / rollover risk"

    return {
        "session": session,
        "phase": phase,
        "day": now.strftime("%A"),
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "timezone": "Africa/Johannesburg",
    }


@app.get("/session")
def get_session():
    return _detect_session()


@app.get("/price")
def get_price(symbol: str = "XAUUSD"):
    requested_symbol = symbol
    symbol = _normalise_symbol(symbol)
    cache = _load_price_cache()

    ok, error = _ensure_mt5_ready()
    if ok:
        tick, tick_error = _get_mt5_tick(symbol)
        if tick and not tick_error:
            mid = None
            if tick.bid and tick.ask:
                mid = (float(tick.bid) + float(tick.ask)) / 2.0

            payload = {
                "ok": True,
                "requested_symbol": requested_symbol,
                "symbol": symbol,
                "bid": float(tick.bid),
                "ask": float(tick.ask),
                "mid": mid,
                "last": float(tick.last) if tick.last is not None else None,
                "volume": int(tick.volume) if tick.volume is not None else None,
                "time": int(tick.time) if tick.time is not None else None,
                "source": "live",
                "price_source": "live",
                "cached": False,
                "saved_at": _now_sast_iso(),
            }

            cache[symbol] = payload
            _save_price_cache(cache)
            return payload

        error = tick_error or "MT5 tick unavailable"

    cached_payload = cache.get(symbol)
    if isinstance(cached_payload, dict):
        fallback = dict(cached_payload)
        fallback["ok"] = True
        fallback["requested_symbol"] = requested_symbol
        fallback["symbol"] = symbol
        fallback["source"] = "cache"
        fallback["price_source"] = "cache"
        fallback["cached"] = True
        fallback["warning"] = error or "Live price unavailable; using last saved price."
        return fallback

    return {
        "ok": False,
        "requested_symbol": requested_symbol,
        "symbol": symbol,
        "error": error or "No live or cached price available.",
        "source": "none",
        "price_source": "none",
        "cached": False,
    }


TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}

@app.get("/candles")
def get_candles(symbol: str = "XAUUSD", tf: str = "H1", limit: int = 40):
    requested_symbol = symbol
    symbol = _normalise_symbol(symbol)
    tf_key = (tf or "H1").upper().strip()
    timeframe = TF_MAP.get(tf_key, mt5.TIMEFRAME_H1)
    limit = max(5, min(int(limit or 40), 300))

    ok, error = _ensure_mt5_ready()
    if not ok:
        return {"ok": False, "symbol": symbol, "requested_symbol": requested_symbol, "tf": tf_key, "error": error, "candles": []}

    if not mt5.symbol_select(symbol, True):
        return {"ok": False, "symbol": symbol, "requested_symbol": requested_symbol, "tf": tf_key, "error": f"MT5 symbol_select failed: {mt5.last_error()}", "candles": []}

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, limit)
    if rates is None:
        return {"ok": False, "symbol": symbol, "requested_symbol": requested_symbol, "tf": tf_key, "error": f"No MT5 candles: {mt5.last_error()}", "candles": []}

    candles = []
    for r in rates:
        candles.append({
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "tick_volume": int(r["tick_volume"]),
        })
    candles = sorted(candles, key=lambda x: x.get("time", 0))
    tick = mt5.symbol_info_tick(symbol)
    live = None
    if tick is not None:
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        live = (bid + ask) / 2 if bid and ask else (bid or ask or None)
    return {"ok": True, "symbol": symbol, "requested_symbol": requested_symbol, "tf": tf_key, "limit": limit, "count": len(candles), "live": live, "candles": candles, "source": "mt5"}

@app.get("/candles/bulk")
def get_candles_bulk(symbol: str = "XAUUSD"):
    """Return real MT5 OHLC for the cockpit cards in one call."""
    out = {}
    for tf_key, limit in (("W1", 14), ("D1", 16), ("H1", 30), ("H2", 28), ("H4", 24)):
        out[tf_key] = get_candles(symbol=symbol, tf=tf_key, limit=limit)
    return {"ok": True, "symbol": _normalise_symbol(symbol), "source": "mt5", "timeframes": out}


@app.get("/state")
def get_state(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    symbol_state = _read_symbol_state(symbol)

    layers: dict[str, dict] = {}
    for layer in ("macro", "weekly", "daily"):
        saved_payload = symbol_state.get(f"{layer}_input")
        if not saved_payload:
            layers[layer] = _default_layer(symbol, layer)
            continue

        try:
            data = DailyInput(**saved_payload) if layer == "daily" else HTFInput(**saved_payload)
            output = TradingGateEngine.classify_htf(data)
            layer_state = _normalise_htf_output(output)
            layer_state["discount_touch_state"] = data.discount_touch_state.value
            layer_state["premium_touch_state"] = data.premium_touch_state.value
            layers[layer] = layer_state
        except Exception as exc:
            fallback = _default_layer(symbol, layer)
            fallback["error"] = str(exc)
            layers[layer] = fallback

    intraday_payload = symbol_state.get("intraday_input")
    if intraday_payload:
        try:
            intraday_output = IntradayEngine.analyze(IntradayInput(**intraday_payload))
            intraday = _normalise_intraday_output(intraday_output)
        except Exception as exc:
            intraday = {
                "symbol": symbol,
                "direction": "neutral",
                "phase": "none",
                "phase_label": "None",
                "profile": "neutral",
                "profile_label": "NEUTRAL",
                "trade_type": "blocked",
                "execution_allowed": False,
                "blocked_reason": str(exc),
                "current_state": "INTRADAY: Input error",
            }
    else:
        intraday = {
            "symbol": symbol,
            "direction": "neutral",
            "phase": "none",
            "phase_label": "None",
            "profile": "neutral",
            "profile_label": "NEUTRAL",
            "trade_type": "blocked",
            "execution_allowed": False,
            "blocked_reason": "Waiting for saved intraday inputs",
            "current_state": "INTRADAY: Waiting for saved inputs",
        }

    mobile_intraday = symbol_state.get("mobile_intraday", {})
    execution_allowed = bool(intraday.get("execution_allowed"))

    return {
        "symbol": symbol,
        "current_session": _detect_session(),
        "session": _detect_session().get("session"),
        "macro": layers["macro"],
        "weekly": layers["weekly"],
        "daily": layers["daily"],
        "intraday": intraday,
        "mobile_intraday": mobile_intraday,
        "intraday_mobile": mobile_intraday,
        "execution_allowed": execution_allowed,
        "mobile_structure": symbol_state.get("mobile_structure", {}),
        "engine": _load_engine_state(symbol),
        "engine_gate": _engine_gate_status(symbol),
    }


@app.post("/set-structure")
def set_structure(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))

    structure_payload = {
        "symbol": symbol,
        "macro_high": payload.get("macro_high"),
        "macro_low": payload.get("macro_low"),
        "weekly_high": payload.get("weekly_high"),
        "weekly_low": payload.get("weekly_low"),
        "daily_high": payload.get("daily_high"),
        "daily_low": payload.get("daily_low"),
        "current_price": payload.get("current_price"),
        "macro_trajectory_start": payload.get("macro_trajectory_start"),
        "weekly_trajectory_start": payload.get("weekly_trajectory_start"),
        "daily_trajectory_start": payload.get("daily_trajectory_start"),
        "profile": payload.get("profile", "SD"),
        "updated_at": datetime.utcnow().isoformat(),
    }

    _write_symbol_state(symbol, "mobile_structure", structure_payload)

    return {"status": "ok", "message": "Structure saved", "symbol": symbol, "structure": structure_payload}




# =============================
# MANUAL CONTEXT ENGINES - WEEKLY / DAILY / INTRADAY GATE
# =============================
ENGINE_PHASES_BLOCKED = {"P3", "P3 Blocked", "Continuation Exhausted", "Stand Down"}
DAILY_BLOCK_SCENARIOS = {"Stand Down"}


HTF_LAYERS = ("macro", "weekly", "daily")
HTF_ZONE_OPTIONS = [
    "Fresh",
    "Mitigation 1",
    "Mitigation 2",
    "Mitigated",
]
HTF_TRAJECTORY_OPTIONS = [
    "Bullish from Deep Discount",
    "Bullish from Discount",
    "Bullish from External Low",
    "Bearish from Deep Premium",
    "Bearish from Premium",
    "Bearish from External High",
    "Neutral / Waiting",
]
HTF_CURRENT_POSITION_OPTIONS = [
    "At Origin",
    "Moving to Fair Price",
    "At Fair Price",
    "Moving to Objective",
    "Objective Hit",
    "Stand Down",
]
HTF_OBJECTIVE_OPTIONS = [
    "Fair Price",
    "Discount",
    "Deep Discount",
    "Premium",
    "Deep Premium",
    "External Low",
    "External High",
    "Opposite Extreme",
    "Stand Down",
]


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _get_current_price_for_symbol(symbol: str, mobile: dict[str, Any] | None = None) -> float | None:
    mobile = mobile or {}
    price = _to_float_or_none(mobile.get("current_price"))
    if price is not None:
        return price
    try:
        payload = _price_payload(symbol)
        for key in ("mid", "price", "bid", "ask"):
            price = _to_float_or_none(payload.get(key))
            if price is not None:
                return price
    except Exception:
        return None
    return None


def _location_from_price(price: float | None, low: float | None, high: float | None) -> dict[str, Any]:
    if price is None or low is None or high is None or high == low:
        return {
            "location": "Not Available",
            "position_percent": None,
            "price": price,
            "range_low": low,
            "range_high": high,
        }

    lo, hi = min(low, high), max(low, high)
    pct = ((price - lo) / (hi - lo)) * 100.0

    # Josh's saved range buckets. These must match the Android overview exactly.
    if pct < 0:
        loc = "External Low"
    elif pct < 25:
        loc = "Deep Discount"
    elif pct < 45:
        loc = "Discount"
    elif pct < 65:
        loc = "Fair Price"
    elif pct < 75:
        loc = "Premium"
    elif pct <= 100:
        loc = "Deep Premium"
    else:
        loc = "External High"

    return {
        "location": loc,
        "position_percent": round(pct, 2),
        "price": price,
        "range_low": lo,
        "range_high": hi,
    }



def _zone_from_trajectory(trajectory: Any) -> str | None:
    """Infer the origin zone from a saved trajectory label.

    Examples:
    - Bullish from External Low -> External Low
    - Bearish from Deep Premium -> Deep Premium
    """
    t = str(trajectory or "").lower()
    if "external low" in t:
        return "External Low"
    if "deep discount" in t:
        return "Deep Discount"
    if "discount" in t:
        return "Discount"
    if "external high" in t:
        return "External High"
    if "deep premium" in t:
        return "Deep Premium"
    if "premium" in t:
        return "Premium"
    return None


def _normalise_zone_label(value: Any) -> str | None:
    v = str(value or "").strip()
    allowed = {
        "external low": "External Low",
        "deep discount": "Deep Discount",
        "discount": "Discount",
        "fair price": "Fair Price",
        "premium": "Premium",
        "deep premium": "Deep Premium",
        "external high": "External High",
    }
    return allowed.get(v.lower())


def _initial_live_leg_from(payload: dict[str, Any]) -> str:
    return (
        _normalise_zone_label(payload.get("live_leg_from"))
        or _normalise_zone_label(payload.get("confirmed_leg_to"))
        or _zone_from_trajectory(payload.get("trajectory"))
        or "Fair Price"
    )


def _mitigation_key_for_location(location: str | None) -> str | None:
    loc = str(location or "").lower()
    if loc == "external low":
        return "external_low_mitigation"
    if loc in {"deep discount", "discount"}:
        return "discount_mitigation"
    if loc in {"premium", "deep premium"}:
        return "premium_mitigation"
    if loc == "external high":
        return "external_high_mitigation"
    return None


def _advance_mitigation_state(value: Any) -> str:
    v = str(value or "Fresh").strip().lower()
    if v in {"fresh", "none", "not set", ""}:
        return "Mitigation 1"
    if v in {"m1", "mitigation 1"}:
        return "Mitigation 2"
    if v in {"m2", "mitigation 2"}:
        return "Mitigated"
    return "Mitigated"


def _auto_update_htf_mitigations(symbol: str, symbol_state: dict[str, Any], mobile: dict[str, Any], price: float | None) -> tuple[dict[str, Any], bool]:
    """Auto-mitigate HTF zones when live price touches them.

    Wicks are good enough on HTF for Josh's model, so this is automatic.
    Debounce rule: one advancement per zone visit. If price stays inside the same
    zone, we do not keep walking Fresh -> M1 -> M2 -> Mitigated every refresh.
    Once price leaves that zone group, the next touch can advance it again.
    """
    changed = False
    updated = dict(symbol_state or {})
    for layer in HTF_LAYERS:
        key = f"{layer}_engine"
        payload = dict(updated.get(key, {}) or {})

        high = _to_float_or_none(payload.get("range_high"))
        low = _to_float_or_none(payload.get("range_low"))
        if high is None:
            high = _to_float_or_none(mobile.get(f"{layer}_high"))
        if low is None:
            low = _to_float_or_none(mobile.get(f"{layer}_low"))

        loc = _location_from_price(price, low, high)
        mit_key = _mitigation_key_for_location(loc.get("location"))
        last_key = payload.get("auto_mitigation_last_key")

        if mit_key is None:
            if last_key:
                payload["auto_mitigation_last_key"] = None
                payload["auto_mitigation_last_location"] = loc.get("location")
                payload["auto_mitigation_last_seen"] = _now_sast_iso()
                updated[key] = payload
                changed = True
            continue

        if last_key != mit_key:
            before = payload.get(mit_key, "Fresh")
            after = _advance_mitigation_state(before)
            touched_zone = loc.get("location") or "Unknown"

            # Trajectory memory: once a zone is touched/mitigated, the current
            # dotted/live leg becomes the confirmed solid leg. A new dotted leg
            # then starts from the mitigated zone toward live price.
            live_from = _initial_live_leg_from(payload)
            payload["confirmed_leg_from"] = live_from
            payload["confirmed_leg_to"] = touched_zone
            payload["confirmed_leg_reason"] = f"{touched_zone} {after}"
            payload["confirmed_leg_updated_at"] = _now_sast_iso()
            payload["live_leg_from"] = touched_zone
            payload["live_leg_to"] = "Live Price"
            payload["live_leg_started_at"] = _now_sast_iso()

            payload[mit_key] = after
            payload["auto_mitigation_last_key"] = mit_key
            payload["auto_mitigation_last_location"] = touched_zone
            payload["auto_mitigation_last_seen"] = _now_sast_iso()
            payload["updated_at"] = _now_sast_iso()
            updated[key] = payload
            changed = True

    return updated, changed


def _normalise_htf_layer_state(symbol: str, layer: str, payload: dict[str, Any] | None, mobile: dict[str, Any], price: float | None) -> dict[str, Any]:
    payload = payload or {}
    high = _to_float_or_none(payload.get("range_high"))
    low = _to_float_or_none(payload.get("range_low"))

    if high is None:
        high = _to_float_or_none(mobile.get(f"{layer}_high"))
    if low is None:
        low = _to_float_or_none(mobile.get(f"{layer}_low"))

    loc = _location_from_price(price, low, high)
    trajectory = payload.get("trajectory", "Neutral / Waiting")
    objective = payload.get("objective", "Stand Down")

    direction = "neutral"
    if str(trajectory).lower().startswith("bullish") or objective in {"Premium", "Deep Premium", "External High"}:
        direction = "bullish"
    elif str(trajectory).lower().startswith("bearish") or objective in {"Discount", "Deep Discount", "External Low"}:
        direction = "bearish"

    return {
        "symbol": symbol,
        "layer": layer,
        "range_high": high,
        "range_low": low,
        "auto_location": loc.get("location"),
        "position_percent": loc.get("position_percent"),
        "price": loc.get("price"),
        "discount_mitigation": payload.get("discount_mitigation", "Fresh"),
        "premium_mitigation": payload.get("premium_mitigation", "Fresh"),
        "external_low_mitigation": payload.get("external_low_mitigation", "Fresh"),
        "external_high_mitigation": payload.get("external_high_mitigation", "Fresh"),
        "trajectory": trajectory,
        "current_position": payload.get("current_position", "At Origin"),
        "objective": objective,
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "directional_permission": direction,
        "notes": payload.get("notes", ""),
        "updated_at": payload.get("updated_at"),
    }


def _infer_objective_direction(objective: str) -> str:
    o = str(objective or "").lower()
    if any(x in o for x in ["premium", "external high"]):
        return "BUY"
    if any(x in o for x in ["discount", "external low"]):
        return "SELL"
    return "NEUTRAL"


def _daily_objective_message(objective: str) -> str:
    direction = _infer_objective_direction(objective)
    if direction == "BUY":
        return "Daily objective points upward. Favor bullish intraday phase logic toward premium/external high."
    if direction == "SELL":
        return "Daily objective points downward. Favor bearish intraday phase logic toward discount/external low."
    return "Daily objective neutral or not set. Do not force directional trades."



def _allowed_models_from_daily(payload: dict[str, Any]) -> list[str]:
    models = payload.get("allowed_models")
    if isinstance(models, list):
        return [str(x) for x in models if x]
    raw = str(payload.get("allowed_model") or "").strip()
    if raw:
        return [raw]
    scenario = str(payload.get("scenario") or "")
    if "Abandoned" in scenario:
        return ["ProTrend Sweep"]
    if "Squeeze" in scenario:
        return ["A+ Reversal", "P1 Continuation", "P2 Continuation"]
    if "External" in scenario or "BOS" in scenario:
        return ["A+ Reversal", "P2 Continuation"]
    return ["A+ Reversal", "P1 Continuation", "P2 Continuation"]


def _load_engine_state(symbol: str) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    s = _read_symbol_state(symbol)
    mobile = s.get("mobile_structure", {}) or {}
    price = _get_current_price_for_symbol(symbol, mobile)

    # Auto-mitigate HTF zones from live price touches. Wicks/touches are enough.
    updated_state, mitigation_changed = _auto_update_htf_mitigations(symbol, s, mobile, price)
    if mitigation_changed:
        full_state = load_state()
        full_state.setdefault("symbols", {})
        full_state["symbols"][symbol] = updated_state
        save_state(full_state)
        s = updated_state

    raw_macro = s.get("macro_engine", {}) or {}
    raw_weekly = s.get("weekly_engine", {}) or {}
    raw_daily = s.get("daily_engine", {}) or {}

    htf_map = {
        "macro": _normalise_htf_layer_state(symbol, "macro", raw_macro, mobile, price),
        "weekly": _normalise_htf_layer_state(symbol, "weekly", raw_weekly, mobile, price),
        "daily": _normalise_htf_layer_state(symbol, "daily", raw_daily, mobile, price),
    }

    return {
        "symbol": symbol,
        "macro_engine": raw_macro,
        "weekly_engine": raw_weekly,
        "daily_engine": raw_daily,
        "intraday_engine": s.get("intraday_engine", {}),
        "htf_map": htf_map,
        "current_price": price,
        "updated_at": _now_sast_iso(),
    }


def _engine_gate_status(symbol: str = "XAUUSD", trade_type: str | None = None) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    state = _load_engine_state(symbol)
    htf_map = state.get("htf_map", {}) or {}
    macro_map = htf_map.get("macro", {}) or {}
    weekly_map = htf_map.get("weekly", {}) or {}
    daily_map = htf_map.get("daily", {}) or {}

    weekly = state.get("weekly_engine", {}) or {}
    daily = state.get("daily_engine", {}) or {}
    intraday = state.get("intraday_engine", {}) or {}

    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    daily_scenario = str(daily.get("scenario") or "Not Set")
    daily_status = str(daily.get("gate_status") or "Active")
    daily_objective = str(daily.get("objective") or daily_map.get("objective") or "Not Set")
    objective_direction = _infer_objective_direction(daily_objective)
    allowed_models = _allowed_models_from_daily(daily)

    intraday_phase = str(intraday.get("phase") or intraday.get("sequence_phase") or "Not Set")
    intraday_profile = str(intraday.get("profile") or "Unknown")
    p3_blocked = bool(intraday.get("p3_blocked", True))

    if daily_status.lower() in {"blocked", "stand down", "stand_down"} or daily_scenario in DAILY_BLOCK_SCENARIOS:
        blockers.append({"code": "DAILY_GATE_BLOCK", "message": f"Daily gate blocked: {daily_scenario}"})

    if p3_blocked and intraday_phase in ENGINE_PHASES_BLOCKED:
        blockers.append({"code": "P3_BLOCKED", "message": "Intraday phase is P3/continuation exhausted. Execution blocked."})

    if objective_direction in {"BUY", "SELL"}:
        warnings.append({"code": "DAILY_OBJECTIVE_DIRECTION", "message": _daily_objective_message(daily_objective)})

    if trade_type:
        t = str(trade_type)
        if allowed_models and t not in allowed_models and "Any" not in allowed_models:
            warnings.append({"code": "MODEL_MISMATCH", "message": f"Trade type '{t}' is not in daily allowed models: {', '.join(allowed_models)}"})

    if daily_scenario in {"Daily BOS External Pending Reclaim", "External Active / Pending Reclaim"}:
        warnings.append({"code": "DAILY_EXTERNAL_UNRESOLVED", "message": "Daily external/BOS is unresolved. Intraday ideas need stronger confirmation."})

    if daily_scenario == "Squeeze" and not daily.get("mitigation_1"):
        warnings.append({"code": "SQUEEZE_SEQUENCE_MISSING", "message": "Squeeze selected but mitigation sequence is incomplete."})

    allowed = len(blockers) == 0
    return {
        "ok": True,
        "symbol": symbol,
        "allowed": allowed,
        "status": "ALLOWED" if allowed else "BLOCKED",
        "blockers": blockers,
        "warnings": warnings,
        "htf_map": htf_map,
        "macro_map": macro_map,
        "weekly_map": weekly_map,
        "daily_map": daily_map,
        "weekly": weekly,
        "daily": {
            **daily,
            "scenario": daily_scenario,
            "gate_status": daily_status,
            "objective": daily_objective,
            "objective_direction": objective_direction,
            "objective_message": _daily_objective_message(daily_objective),
            "allowed_models": allowed_models,
        },
        "intraday": {
            **intraday,
            "phase": intraday_phase,
            "profile": intraday_profile,
            "p3_blocked": p3_blocked,
        },
        "summary": {
            "macro_location": macro_map.get("auto_location", "Not Set"),
            "macro_trajectory": macro_map.get("trajectory", "Not Set"),
            "weekly_location": weekly_map.get("auto_location") or weekly.get("location", "Not Set"),
            "weekly_trajectory": weekly_map.get("trajectory") or weekly.get("trajectory", "Not Set"),
            "daily_location": daily_map.get("auto_location", "Not Set"),
            "daily_trajectory": daily_map.get("trajectory", "Not Set"),
            "daily_scenario": daily_scenario,
            "daily_objective": daily_objective,
            "daily_objective_direction": objective_direction,
            "intraday_phase": intraday_phase,
            "intraday_profile": intraday_profile,
        },
        "last_refresh": _now_sast_iso(),
    }


@app.get("/engine/state")
def engine_state(symbol: str = "XAUUSD"):
    return _load_engine_state(symbol)


@app.get("/engine/gate")
def engine_gate(symbol: str = "XAUUSD", trade_type: str | None = None):
    return _engine_gate_status(symbol=symbol, trade_type=trade_type)


@app.post("/engine/macro")
def save_macro_engine(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    macro = {
        "symbol": symbol,
        "range_high": payload.get("range_high"),
        "range_low": payload.get("range_low"),
        "discount_mitigation": payload.get("discount_mitigation", "Fresh"),
        "premium_mitigation": payload.get("premium_mitigation", "Fresh"),
        "external_low_mitigation": payload.get("external_low_mitigation", "Fresh"),
        "external_high_mitigation": payload.get("external_high_mitigation", "Fresh"),
        "trajectory": payload.get("trajectory", "Neutral / Waiting"),
        "current_position": payload.get("current_position", "At Origin"),
        "objective": payload.get("objective", "Stand Down"),
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "notes": payload.get("notes", ""),
        "updated_at": _now_sast_iso(),
    }
    _write_symbol_state(symbol, "macro_engine", macro)
    return {"ok": True, "message": "Macro engine saved", "symbol": symbol, "macro_engine": macro, "gate": _engine_gate_status(symbol)}


@app.post("/engine/weekly")
def save_weekly_engine(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    weekly = {
        "symbol": symbol,
        "range_high": payload.get("range_high"),
        "range_low": payload.get("range_low"),
        "discount_mitigation": payload.get("discount_mitigation", "Fresh"),
        "premium_mitigation": payload.get("premium_mitigation", "Fresh"),
        "external_low_mitigation": payload.get("external_low_mitigation", "Fresh"),
        "external_high_mitigation": payload.get("external_high_mitigation", "Fresh"),
        "trajectory": payload.get("trajectory", "Neutral / Waiting"),
        "current_position": payload.get("current_position", "At Origin"),
        "objective": payload.get("objective", "Stand Down"),
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "protrend_direction": payload.get("protrend_direction", payload.get("trajectory", "Neutral / Waiting")),
        "notes": payload.get("notes", ""),
        "updated_at": _now_sast_iso(),
    }
    _write_symbol_state(symbol, "weekly_engine", weekly)
    return {"ok": True, "message": "Weekly engine saved", "symbol": symbol, "weekly_engine": weekly, "gate": _engine_gate_status(symbol)}


@app.post("/engine/daily")
def save_daily_engine(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    daily = {
        "symbol": symbol,
        "range_high": payload.get("range_high"),
        "range_low": payload.get("range_low"),
        "discount_mitigation": payload.get("discount_mitigation", "Fresh"),
        "premium_mitigation": payload.get("premium_mitigation", "Fresh"),
        "external_low_mitigation": payload.get("external_low_mitigation", "Fresh"),
        "external_high_mitigation": payload.get("external_high_mitigation", "Fresh"),
        "trajectory": payload.get("trajectory", "Neutral / Waiting"),
        "current_position": payload.get("current_position", "At Origin"),
        "objective": payload.get("objective", "Not Set"),
        "confirmed_leg_from": payload.get("confirmed_leg_from"),
        "confirmed_leg_to": payload.get("confirmed_leg_to"),
        "confirmed_leg_reason": payload.get("confirmed_leg_reason"),
        "live_leg_from": payload.get("live_leg_from"),
        "live_leg_to": payload.get("live_leg_to"),
        "scenario": payload.get("scenario", "Not Set"),
        "bias": payload.get("bias", "Neutral"),
        "mitigation_1": payload.get("mitigation_1", "None"),
        "mitigation_2": payload.get("mitigation_2", "None"),
        "allowed_models": payload.get("allowed_models", []),
        "gate_status": payload.get("gate_status", "Active"),
        "notes": payload.get("notes", ""),
        "updated_at": _now_sast_iso(),
    }
    _write_symbol_state(symbol, "daily_engine", daily)
    return {"ok": True, "message": "Daily engine saved", "symbol": symbol, "daily_engine": daily, "gate": _engine_gate_status(symbol)}


@app.post("/engine/intraday")
def save_intraday_engine(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    intraday = {
        "symbol": symbol,
        "direction": payload.get("direction", "neutral"),
        "phase": payload.get("phase", payload.get("sequence_phase", "CHoCH Pending")),
        "sequence_phase": payload.get("phase", payload.get("sequence_phase", "CHoCH Pending")),
        "breaking_point": payload.get("breaking_point"),
        "p1_high": payload.get("p1_high"),
        "p1_low": payload.get("p1_low"),
        "p2_high": payload.get("p2_high"),
        "p2_low": payload.get("p2_low"),
        "profile": payload.get("profile", "Unknown"),
        "retrace_depth": payload.get("retrace_depth"),
        "p3_blocked": bool(payload.get("p3_blocked", True)),
        "notes": payload.get("notes", ""),
        "updated_at": _now_sast_iso(),
    }
    _write_symbol_state(symbol, "intraday_engine", intraday)
    return {"ok": True, "message": "Intraday engine saved", "symbol": symbol, "intraday_engine": intraday, "gate": _engine_gate_status(symbol)}

@app.post("/engine/micro")
def save_micro_engine(payload: dict = Body(...)):
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    micro = {
        "symbol": symbol,
        "status": payload.get("status", "Waiting"),
        "trigger_timeframe": payload.get("trigger_timeframe", "1M / 5M"),
        "trigger_model": payload.get("trigger_model", "CHoCH / Reclaim"),
        "trigger_level": payload.get("trigger_level"),
        "invalidation": payload.get("invalidation"),
        "notes": payload.get("notes", ""),
        "updated_at": _now_sast_iso(),
    }
    _write_symbol_state(symbol, "micro_engine", micro)
    return {"ok": True, "message": "Micro engine saved", "symbol": symbol, "micro_engine": micro, "gate": _engine_gate_status(symbol)}




# =============================
# NEWS PROVIDER - MANUAL WEEKLY USD NEWS PLAN
# =============================
SAST = timezone(timedelta(hours=2))
NEWS_DATA_DIR = Path(__file__).resolve().parent / "data"
MANUAL_NEWS_FILE = NEWS_DATA_DIR / "manual_news_week.json"

NEWS_EVENT_OPTIONS = [
    "NFP",
    "CPI",
    "Core CPI",
    "PPI",
    "Core PCE",
    "FOMC",
    "Fed Rate Decision",
    "Powell Speech",
    "GDP",
    "Retail Sales",
    "ISM PMI",
    "Jobless Claims",
    "Other USD Medium",
    "Other USD High",
]

CRITICAL_NEWS_KEYWORDS = (
    "nfp", "nonfarm", "non-farm", "cpi", "core cpi", "fomc",
    "fed rate", "fed interest", "interest rate", "powell",
)

HIGH_OVERRIDE_KEYWORDS = (
    "nfp", "nonfarm", "non-farm", "payroll", "employment situation",
    "unemployment", "average hourly", "cpi", "core cpi", "ppi",
    "core pce", "pce", "fomc", "fed rate", "fed interest",
    "powell", "gdp", "retail sales", "ism", "jobless claims",
)


def _week_start_sast(now: datetime | None = None) -> datetime:
    now = now or datetime.now(SAST)
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_days_sast(now: datetime | None = None) -> list[dict[str, str]]:
    start = _week_start_sast(now)
    return [
        {
            "day": (start + timedelta(days=i)).strftime("%A"),
            "date": (start + timedelta(days=i)).date().isoformat(),
        }
        for i in range(5)
    ]


def _load_manual_news_state() -> dict[str, Any]:
    try:
        if MANUAL_NEWS_FILE.exists():
            raw = MANUAL_NEWS_FILE.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"events": [], "last_updated": None, "source": "manual_weekly"}


def _save_manual_news_state(state: dict[str, Any]) -> None:
    NEWS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_NEWS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _normalise_news_impact(title: str, impact: str | None = None) -> str:
    title_l = (title or "").lower()
    if any(k in title_l for k in HIGH_OVERRIDE_KEYWORDS):
        return "High"
    impact_l = (impact or "").lower()
    if "high" in impact_l:
        return "High"
    return "Medium"


def _is_critical_news(title: str) -> bool:
    title_l = (title or "").lower()
    return any(k in title_l for k in CRITICAL_NEWS_KEYWORDS)


def _normalise_manual_event(ev: dict[str, Any], idx: int = 0) -> dict[str, Any] | None:
    title = str(ev.get("title") or ev.get("event") or ev.get("event_key") or "").strip()
    date_s = str(ev.get("date") or "").strip()
    time_s = str(ev.get("time") or "").strip()
    if not title or not date_s or not time_s:
        return None

    if title not in NEWS_EVENT_OPTIONS and title.lower() not in ("other", "other usd medium", "other usd high"):
        # Keep custom titles, but still force USD-only cockpit behavior.
        pass

    try:
        event_dt = datetime.fromisoformat(f"{date_s}T{time_s}:00").replace(tzinfo=SAST)
    except Exception:
        return None

    impact = _normalise_news_impact(title, ev.get("impact"))
    critical = bool(ev.get("critical", False)) or _is_critical_news(title)
    block_type = str(ev.get("block_type") or ("block" if impact == "High" else "warning")).lower()
    if block_type not in {"block", "warning"}:
        block_type = "block" if impact == "High" else "warning"

    block_before = int(ev.get("block_before_minutes") or (60 if critical else 30 if impact == "High" else 0))
    block_after = int(ev.get("block_after_minutes") or (30 if critical else 15 if impact == "High" else 0))

    return {
        "id": ev.get("id") or f"manual-{date_s}-{time_s}-{idx}",
        "title": title,
        "event": title,
        "event_key": ev.get("event_key") or title,
        "currency": "USD",
        "impact": impact,
        "critical": critical,
        "block_type": block_type,
        "block_before_minutes": block_before,
        "block_after_minutes": block_after,
        "datetime": event_dt.isoformat(),
        "date": date_s,
        "time": time_s,
        "day": event_dt.strftime("%A"),
        "source": "Manual Weekly Plan",
    }


def _manual_news_events_for_week() -> list[dict[str, Any]]:
    state = _load_manual_news_state()
    start = _week_start_sast()
    end = start + timedelta(days=7)
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(state.get("events") or []):
        ev = _normalise_manual_event(raw, idx)
        if not ev:
            continue
        try:
            event_dt = datetime.fromisoformat(ev["datetime"])
        except Exception:
            continue
        if start <= event_dt < end:
            events.append(ev)
    events.sort(key=lambda e: (e.get("date") or "9999-99-99", e.get("time") or "99:99", e.get("title") or ""))
    return events


def _manual_news_update_status() -> dict[str, Any]:
    now = datetime.now(SAST)
    week_start = _week_start_sast(now)
    due = week_start + timedelta(minutes=5)  # Monday 00:05 SAST
    state = _load_manual_news_state()
    last_updated_raw = state.get("last_updated")
    last_updated = None
    try:
        if last_updated_raw:
            last_updated = datetime.fromisoformat(last_updated_raw)
    except Exception:
        last_updated = None

    updated_this_week = bool(last_updated and last_updated >= due)
    needs_update = bool(now >= due and not updated_this_week)
    return {
        "needs_update": needs_update,
        "updated_this_week": updated_this_week,
        "last_updated": last_updated_raw,
        "update_due_at": due.isoformat(),
        "week_start": week_start.date().isoformat(),
        "week_days": _week_days_sast(now),
    }


@app.get("/news/options")
def news_options():
    return {
        "ok": True,
        "events": NEWS_EVENT_OPTIONS,
        "impacts": ["Medium", "High"],
        "block_types": ["warning", "block"],
        "critical_events": ["NFP", "CPI", "Core CPI", "FOMC", "Fed Rate Decision", "Powell Speech"],
        "week_days": _week_days_sast(),
        "last_refresh": _now_sast_iso(),
    }


@app.get("/news/today")
def news_today(symbol: str = "XAUUSD"):
    data = news_week(symbol=symbol)
    today = datetime.now(SAST).date().isoformat()
    data["events"] = [e for e in data.get("events", []) if e.get("date") == today]
    data["window"] = "today"
    return data


@app.get("/news/week")
def news_week(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    update_status = _manual_news_update_status()
    events = _manual_news_events_for_week()
    return {
        "ok": True,
        "symbol": symbol,
        "mode": "manual_weekly",
        "source": "Manual Weekly USD News Plan",
        "timezone": "Africa/Johannesburg",
        "filter": "USD only / Medium + High",
        "events": events,
        "event_options": NEWS_EVENT_OPTIONS,
        "last_refresh": _now_sast_iso(),
        **update_status,
        "warning": "Weekly USD news not updated. Check Myfxbook before trading." if update_status["needs_update"] else None,
    }


@app.post("/news/manual-week")
def save_manual_news_week(payload: dict = Body(...)):
    events_in = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(events_in, list):
        events_in = []

    clean_events = []
    for idx, raw in enumerate(events_in):
        ev = _normalise_manual_event(raw if isinstance(raw, dict) else {}, idx)
        if ev:
            clean_events.append(ev)

    state = {
        "source": "manual_weekly",
        "last_updated": _now_sast_iso(),
        "events": clean_events,
    }
    _save_manual_news_state(state)
    return {
        "ok": True,
        "message": "Manual weekly USD news saved",
        "events": clean_events,
        "count": len(clean_events),
        "last_updated": state["last_updated"],
    }


def _news_execution_block_status(symbol: str = "XAUUSD") -> dict[str, Any]:
    try:
        data = news_week(symbol=symbol)
        now = datetime.now(SAST)
        active_events = []
        next_events = []
        blocked = False
        warning = None

        for ev in data.get("events", []):
            try:
                event_dt = datetime.fromisoformat(ev["datetime"])
            except Exception:
                continue

            mins = (event_dt - now).total_seconds() / 60.0
            ev2 = {**ev, "minutes_to_event": round(mins, 1)}

            # Upcoming events shown for awareness.
            if -60 <= mins <= 240:
                next_events.append(ev2)

            if ev.get("impact") == "Medium":
                if 0 <= mins <= 60:
                    warning = f"Medium USD news in {round(mins)} min"
                continue

            if ev.get("block_type") != "block":
                continue

            before = float(ev.get("block_before_minutes") or 30)
            after = float(ev.get("block_after_minutes") or 15)
            if -after <= mins <= before:
                blocked = True
                active_events.append(ev2)

        if blocked:
            reason = f"USD news block active: {active_events[0].get('title')}"
        elif data.get("needs_update"):
            reason = "Weekly USD news not updated. Check Myfxbook before trading."
        elif warning:
            reason = warning
        else:
            reason = "No active manual USD news block"

        return {
            "blocked": blocked,
            "reason": reason,
            "events": active_events[:5],
            "upcoming": next_events[:8],
            "needs_update": data.get("needs_update", False),
            "last_updated": data.get("last_updated"),
            "source": data.get("source"),
            "mode": data.get("mode"),
        }
    except Exception as exc:
        return {
            "blocked": False,
            "reason": f"Manual news check unavailable: {exc}. Check Myfxbook before trading.",
            "events": [],
            "upcoming": [],
            "needs_update": True,
        }


def _position_side(position_type: int) -> str:
    return "BUY" if position_type == mt5.POSITION_TYPE_BUY else "SELL"


def _position_current_price(position, tick) -> float:
    return float(tick.bid) if position.type == mt5.POSITION_TYPE_BUY else float(tick.ask)


def _calc_position_risk_usd(position) -> float | None:
    if not position.sl:
        return None

    profit = mt5.order_calc_profit(position.type, position.symbol, float(position.volume), float(position.price_open), float(position.sl))
    if profit is None:
        return None
    return abs(float(profit))


def _calc_current_r(position, risk_usd: float | None) -> float | None:
    if not risk_usd or risk_usd <= 0:
        return None
    return float(position.profit) / float(risk_usd)


def _classify_sl_state(positions: list) -> str:
    if not positions:
        return "No position"
    states = []
    for p in positions:
        if not p.sl:
            states.append("No SL")
            continue
        entry = float(p.price_open)
        sl = float(p.sl)
        if p.type == mt5.POSITION_TYPE_BUY:
            if sl > entry:
                states.append("BE+")
            elif abs(sl - entry) < 1e-8:
                states.append("BE")
            else:
                states.append("-1R / Risk")
        else:
            if sl < entry:
                states.append("BE+")
            elif abs(sl - entry) < 1e-8:
                states.append("BE")
            else:
                states.append("-1R / Risk")
    return ", ".join(sorted(set(states)))


@app.get("/trade/active")
def active_trade(symbol: str = "XAUUSD", account: str = "challenge"):
    """Read EA live-status file for the selected account AND symbol.

    This avoids the MT5 Python package binding to only one terminal. The EA is the
    source of truth; each chart writes its own status file. Finally, a sane lane.
    """
    symbol = _normalise_symbol(symbol)
    account = _normalise_account(account) if "_normalise_account" in globals() else (account or "challenge")

    def one(acct: str):
        if read_live_trade_status is None:
            return {"ok": False, "account": acct, "symbol": symbol, "error": "mt5_bridge.read_live_trade_status unavailable"}
        try:
            raw = read_live_trade_status(account=acct, symbol=symbol)
        except TypeError:
            raw = read_live_trade_status(account=acct)
        except Exception as exc:
            return {"ok": False, "account": acct, "symbol": symbol, "error": str(exc)}

        raw = raw or {}
        status = raw.get("status", "NONE")
        open_positions = int(raw.get("open_positions") or raw.get("position_count") or 0)
        lots = float(raw.get("lots") or 0)
        floating_profit = float(raw.get("floating_profit") or 0)
        current_r = float(raw.get("current_r") or 0)
        return {
            "ok": True,
            "account": acct,
            "symbol": symbol,
            "status": status,
            "position_count": open_positions,
            "lots": lots,
            "entry": raw.get("entry", 0),
            "current_price": raw.get("current_price", 0),
            "sl": raw.get("sl", 0),
            "floating_profit": floating_profit if open_positions > 0 else 0,
            "current_r": current_r if open_positions > 0 else 0,
            "two_r_hit": bool(raw.get("tp1_confirmed", False)),
            "sl_state": "BE/Managed" if raw.get("runner_sl_moved") else ("No position" if open_positions == 0 else "Risk"),
            "initial_risk_usd": raw.get("initial_risk_usd", 0 if open_positions == 0 else raw.get("risk_amount", 0)),
            "initial_risk_percent": raw.get("initial_risk_percent", 0),
            "risk_per_position_usd": raw.get("risk_per_position_usd", 0),
            "raw_status": raw,
        }

    if account == "both":
        return {"ok": True, "symbol": symbol, "account": "both", "accounts": {"funded": one("funded"), "challenge": one("challenge")}}
    return one(account)


def _close_position(position) -> dict:
    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        return {"ok": False, "ticket": int(position.ticket), "error": f"No tick for {position.symbol}"}

    if position.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "position": int(position.ticket),
        "volume": float(position.volume),
        "type": order_type,
        "price": price,
        "deviation": 30,
        "magic": 27052026,
        "comment": "Mobile cockpit close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "ticket": int(position.ticket), "error": f"order_send returned None: {mt5.last_error()}"}

    ok = result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL)
    return {
        "ok": ok,
        "ticket": int(position.ticket),
        "retcode": int(result.retcode),
        "comment": result.comment,
    }


@app.post("/trade/close-full")
def close_full(payload: dict = Body(...)):
    if payload.get("confirm") != "CLOSE_FULL":
        return {"ok": False, "error": "Missing confirmation token for full close"}
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    account = _normalise_account(payload.get("account", "challenge"))
    if write_close_full_command is None:
        return {"ok": False, "error": "mt5_bridge.write_close_full_command unavailable"}

    results = []
    for acct in _account_list(account):
        try:
            try:
                cmd = write_close_full_command(symbol=symbol, account=acct, confirmation_token="CLOSE_FULL")
            except TypeError:
                cmd = write_close_full_command(symbol=symbol, account=acct)
            results.append(cmd)
            if log_management_event is not None:
                try:
                    log_management_event({"action": "CLOSE_FULL", "account": acct, "symbol": symbol, "command": cmd})
                except Exception:
                    pass
        except Exception as exc:
            return {"ok": False, "error": str(exc), "account": acct, "symbol": symbol}
    return {"ok": True, "message": "Close full command written.", "symbol": symbol, "account": account, "commands": results}


@app.post("/trade/close-half")
def close_half(payload: dict = Body(...)):
    if payload.get("confirm") != "CLOSE_HALF":
        return {"ok": False, "error": "Missing confirmation token for half close"}
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    account = _normalise_account(payload.get("account", "challenge"))
    if write_close_half_command is None:
        return {"ok": False, "error": "mt5_bridge.write_close_half_command unavailable"}

    results = []
    for acct in _account_list(account):
        try:
            try:
                cmd = write_close_half_command(symbol=symbol, account=acct, confirmation_token="CLOSE_HALF")
            except TypeError:
                cmd = write_close_half_command(symbol=symbol, account=acct)
            results.append(cmd)
            if log_management_event is not None:
                try:
                    log_management_event({"action": "CLOSE_HALF", "account": acct, "symbol": symbol, "command": cmd})
                except Exception:
                    pass
        except Exception as exc:
            return {"ok": False, "error": str(exc), "account": acct, "symbol": symbol}
    return {"ok": True, "message": "Close half command written.", "symbol": symbol, "account": account, "commands": results}


# =============================
# ANDROID EXECUTION -> MT5 BRIDGE -> EA
# =============================
ACCOUNTS = {"funded", "challenge", "both", "ftmo_funded", "ftmo_challenge", "xm_personal"}
ACCOUNT_ALIASES = {"ftmo_funded": "funded", "ftmo_challenge": "challenge", "xm": "xm_personal"}


def _normalise_account(account: str | None) -> str:
    account = (account or "funded").strip().lower()
    account = ACCOUNT_ALIASES.get(account, account)
    return account if account in ACCOUNTS else "funded"


def _account_list(account: str | None) -> list[str]:
    account = _normalise_account(account)
    if account == "both":
        return ["funded", "challenge"]
    return [account]


def _safe_daily_budget(account: str = "funded") -> dict[str, Any]:
    """Authoritative backend daily lock summary.

    Uses risk_guard.py when available:
    - max 3 executions/day
    - max 2% utilised risk/day
    - separate funded/challenge counters

    Falls back to journal.daily_budget_summary only if risk_guard is not installed yet.
    """
    if daily_lock_summary is not None:
        try:
            return daily_lock_summary(account=account)
        except Exception as exc:
            return {"locked": False, "error": f"risk_guard.daily_lock_summary failed: {exc}"}

    if daily_budget_summary is None:
        return {"locked": False, "error": "risk_guard and journal.daily_budget_summary unavailable"}

    try:
        return daily_budget_summary(account=account)
    except TypeError:
        return daily_budget_summary()
    except Exception as exc:
        return {"locked": False, "error": str(exc)}


def _safe_log_execute_sent(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        if log_execute_sent is not None:
            return log_execute_sent(payload)
    except TypeError:
        pass
    except Exception:
        pass
    if log_event is not None:
        try:
            return log_event("execute_sent", payload)
        except Exception:
            return None
    return None




def _session_execution_window_status() -> dict[str, Any]:
    session = _detect_session()
    # Existing EA also enforces time window. This API view is for cockpit visibility.
    now = datetime.now(SAST)
    minutes = now.hour * 60 + now.minute
    valid = (60 <= minutes <= 300) or (555 <= minutes <= 1140)
    return {
        "valid": valid,
        "label": session.get("phase", "Unknown"),
        "reason": "Within execution window" if valid else "Outside execution window",
        "now_sast": _now_sast_iso(),
    }


def _news_execution_block_status(symbol: str = "XAUUSD") -> dict[str, Any]:
    # Authoritative V1 news gate: manual weekly USD news plan.
    # This intentionally overrides older RSS/API versions that were noisy or paid-locked.
    try:
        data = news_week(symbol=symbol)
        now = datetime.now(SAST)
        active_events = []
        next_events = []
        blocked = False
        warning = None

        for ev in data.get("events", []):
            try:
                event_dt = datetime.fromisoformat(ev["datetime"])
            except Exception:
                continue

            mins = (event_dt - now).total_seconds() / 60.0
            ev2 = {**ev, "minutes_to_event": round(mins, 1)}

            if -60 <= mins <= 240:
                next_events.append(ev2)

            if ev.get("impact") == "Medium":
                if 0 <= mins <= 60:
                    warning = f"Medium USD news in {round(mins)} min"
                continue

            if ev.get("block_type") != "block":
                continue

            before = float(ev.get("block_before_minutes") or 30)
            after = float(ev.get("block_after_minutes") or 15)
            if -after <= mins <= before:
                blocked = True
                active_events.append(ev2)

        if blocked:
            reason = f"USD news block active: {active_events[0].get('title')}"
        elif data.get("needs_update"):
            reason = "Weekly USD news not updated. Check Myfxbook before trading."
        elif warning:
            reason = warning
        else:
            reason = "No active manual USD news block"

        return {
            "blocked": blocked,
            "reason": reason,
            "events": active_events[:5],
            "upcoming": next_events[:8],
            "needs_update": data.get("needs_update", False),
            "last_updated": data.get("last_updated"),
            "source": data.get("source"),
            "mode": data.get("mode"),
        }
    except Exception as exc:
        return {
            "blocked": False,
            "reason": f"Manual news check unavailable: {exc}. Check Myfxbook before trading.",
            "events": [],
            "upcoming": [],
            "needs_update": True,
        }


@app.get("/trade/execution-status")
def trade_execution_status(account: str = "funded", symbol: str = "XAUUSD", risk_percent: float = 0.5):
    account = _normalise_account(account)
    symbol = _normalise_symbol(symbol)
    budget = _safe_daily_budget(account)
    session = _session_execution_window_status()
    news = _news_execution_block_status(symbol)
    bridge = trade_bridge_status(account=account, symbol=symbol)
    engine_gate = _engine_gate_status(symbol=symbol)
    blockers = []
    if not session.get("valid"):
        blockers.append({"code": "INVALID_SESSION", "message": session.get("reason")})
    if news.get("blocked"):
        blockers.append({"code": "NEWS_BLOCK", "message": news.get("reason")})
    if budget.get("locked"):
        blockers.append({"code": "DAILY_LOCK", "message": budget.get("lock_reason") or "Daily lock active"})
    try:
        if float(risk_percent) > float(budget.get("remaining_risk_percent", 999)):
            blockers.append({"code": "MAX_DAILY_RISK_USED", "message": "Requested risk exceeds remaining daily risk."})
    except Exception:
        pass
    if bridge.get("ok") and not bridge.get("ea_online"):
        blockers.append({"code": "EA_NOT_CONNECTED", "message": "EA heartbeat not detected or stale."})
    if not engine_gate.get("allowed", True):
        blockers.extend(engine_gate.get("blockers", []))
    ready = len(blockers) == 0
    return {
        "ok": True,
        "execution_ready": ready,
        "status": "READY" if ready else "BLOCKED",
        "account": account,
        "symbol": symbol,
        "last_refresh": _now_sast_iso(),
        "blockers": blockers,
        "session": session,
        "news": news,
        "budget": budget,
        "bridge": bridge,
        "engine_gate": engine_gate,
        "notifications": [
            {"level": "success" if ready else "danger", "message": "Execution ready" if ready else blockers[0]["message"], "timestamp": _now_sast_iso()}
        ],
    }

@app.get("/trade/bridge-status")
def trade_bridge_status(account: str = "funded", symbol: str = "XAUUSD"):
    account = _normalise_account(account)
    symbol = _normalise_symbol(symbol)
    if mt5_bridge_status is None:
        return {"ok": False, "error": "mt5_bridge.bridge_status unavailable"}
    try:
        return mt5_bridge_status(account=account, symbol=symbol)
    except TypeError:
        return mt5_bridge_status(account=account)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/trade/budget")
def trade_budget(account: str = "funded"):
    account = _normalise_account(account)
    if account == "both":
        return {"funded": _safe_daily_budget("funded"), "challenge": _safe_daily_budget("challenge")}
    return _safe_daily_budget(account)




@app.post("/trade/manual-record")
def trade_manual_record(payload: dict = Body(...)):
    """Manual correction for the daily gate.

    Use this only when a confirmed MT5 trade opened but the app did not record
    the idea/risk due to a previous bug or interrupted response.
    """
    if record_execution_utilised is None:
        return {"ok": False, "error": "risk_guard.record_execution_utilised unavailable"}

    account = _normalise_account(payload.get("account", "funded"))
    symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
    direction = str(payload.get("direction", "BUY")).upper()
    risk_percent = float(payload.get("risk_percent", 0.0) or 0.0)
    trade_id = str(payload.get("trade_id") or f"manual_{account}_{symbol}_{int(datetime.now(SAST).timestamp())}")
    tickets = payload.get("tickets") or []

    if direction not in {"BUY", "SELL", "MANUAL"}:
        return {"ok": False, "error": "Direction must be BUY, SELL, or MANUAL."}
    if risk_percent <= 0:
        return {"ok": False, "error": "risk_percent must be greater than 0."}

    summary = record_execution_utilised(
        account=account,
        symbol=symbol,
        direction=direction,
        risk_percent=risk_percent,
        trade_id=trade_id,
        tickets=[str(t) for t in tickets],
        trade_type=payload.get("trade_type", "manual_correction"),
        entry_model=payload.get("entry_model", "manual_correction"),
        notes=payload.get("notes", "Manual daily gate correction"),
        micro_checklist=payload.get("micro_checklist", {}),
        source="manual_correction",
    )
    return {"ok": True, "message": "Manual trade idea recorded for daily gate.", "summary": summary}



def _sql_context_from_state(state_snapshot: dict[str, Any]) -> dict[str, Any]:
    engine = state_snapshot.get("engine", {}) or {}
    htf_map = engine.get("htf_map", {}) or {}
    return {
        "weekly": htf_map.get("weekly") or state_snapshot.get("weekly", {}),
        "daily": htf_map.get("daily") or state_snapshot.get("daily", {}),
        "intraday": state_snapshot.get("intraday") or engine.get("intraday_engine", {}),
        "micro": state_snapshot.get("micro") or state_snapshot.get("mobile_intraday", {}),
    }

def _safe_sql_blocked(*, account: str, symbol: str, direction: str = "", risk_percent: float = 0, reason_code: str = "", message: str = "", payload: dict[str, Any] | None = None) -> None:
    if sql_log_blocked_attempt is not None:
        try:
            sql_log_blocked_attempt(account=account, symbol=symbol, direction=direction, risk_percent=risk_percent, reason_code=reason_code, message=message, payload=payload or {})
        except Exception:
            pass

def _safe_sql_context(*, trade_id: str, account: str, symbol: str, source: str, state_snapshot: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    if sql_log_context_snapshot is not None:
        try:
            ctx = _sql_context_from_state(state_snapshot or {})
            sql_log_context_snapshot(
                trade_id=trade_id,
                account=account,
                symbol=symbol,
                source=source,
                weekly=ctx.get("weekly"),
                daily=ctx.get("daily"),
                intraday=ctx.get("intraday"),
                micro=ctx.get("micro"),
                full_context={"state": state_snapshot or {}, "android_payload": payload or {}},
            )
        except Exception:
            pass

@app.get("/trade/result")
def trade_result(account: str = "funded", symbol: str = "XAUUSD"):
    if read_trade_result is None:
        return {"ok": False, "error": "mt5_bridge.read_trade_result unavailable"}
    account = _normalise_account(account)
    symbol = _normalise_symbol(symbol)
    try:
        result = read_trade_result(account=account, symbol=symbol)
    except TypeError:
        result = read_trade_result(account=account)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return result or {"ok": True, "message": "No result file yet", "account": account, "symbol": symbol}


MAX_TRADE_IDEA_RISK_PERCENT = 1.0


def _int_or_none_local(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


@app.post("/trade/execute")
def execute_trade(payload: dict = Body(...)):
    """Android Execution screen -> bridge command file(s) -> EA(s).

    Account routing:
    - funded: existing funded EA files, untouched
    - challenge: separate challenge command/result/status files
    - both: writes one command per account
    """
    if write_execute_command is None:
        return {"ok": False, "error": "mt5_bridge.write_execute_command unavailable"}

    try:
        symbol = _normalise_symbol(payload.get("symbol", "XAUUSD"))
        direction = str(payload.get("direction", "BUY")).upper()
        account = _normalise_account(payload.get("account", "funded"))

        # v128 smart SL helper: Android can send either full sl_price or short
        # last-two-digit input. The resolved value is still returned in the
        # payload and can be manually overridden by sending sl_price directly.
        sl_resolved_payload = None
        if payload.get("sl_price") not in (None, ""):
            sl_price = float(payload.get("sl_price"))
        else:
            live_for_sl = payload.get("live_price") or payload.get("current_price")
            if live_for_sl is None:
                live_for_sl = _get_current_price_for_symbol(symbol)
            sl_digits = payload.get("sl_digits") or payload.get("sl_last_digits") or payload.get("sl_short")
            if sl_digits in (None, ""):
                return {"ok": False, "error": "sl_price or sl_digits is required."}
            sl_resolved_payload = _resolve_sl_from_digits(direction=direction, live_price=float(live_for_sl), digits=str(sl_digits))
            sl_price = float(sl_resolved_payload["resolved_sl"])
        risk_percent = float(payload.get("risk_percent"))

        # v125: Explicit add-risk mode with per-trade-idea risk cap.
        # Default behaviour remains defensive: NEW_TRADE still blocks when an EA position is already open.
        # ADD_RISK_TO_ACTIVE_TRADE intentionally allows a second EXECUTE command for the same account/symbol,
        # so Josh can add planned risk to an existing trade idea without changing the EA.
        execution_mode = str(payload.get("execution_mode") or payload.get("mode") or "NEW_TRADE").upper().strip()
        add_risk_flag = bool(payload.get("add_risk") or payload.get("is_add_risk"))
        is_add_risk = add_risk_flag or execution_mode in {"ADD_RISK", "ADD_RISK_TO_ACTIVE_TRADE", "ADD_RISK_TO_TRADE"}

        if direction not in {"BUY", "SELL"}:
            return {"ok": False, "error": "Direction must be BUY or SELL."}
        if sl_price <= 0:
            return {"ok": False, "error": "SL price must be greater than 0."}
        if risk_percent <= 0 or risk_percent > 2.0:
            return {"ok": False, "error": "Risk percent must be greater than 0 and no more than 2.0."}
        if sl_resolved_payload:
            payload["resolved_sl"] = sl_resolved_payload
            payload["sl_price"] = sl_price

        # In add-risk mode, require that the EA status file already shows an active/open position.
        # This prevents ADD_RISK being used as a sneaky bypass for a brand-new trade. Humanity requires bouncers.
        if is_add_risk:
            active_ok = False
            active_statuses = {}
            for acct_check in _account_list(account):
                try:
                    st = read_live_trade_status(account=acct_check, symbol=symbol) if read_live_trade_status is not None else {}
                except TypeError:
                    st = read_live_trade_status(account=acct_check) if read_live_trade_status is not None else {}
                except Exception:
                    st = {}
                active_statuses[acct_check] = st
                try:
                    open_positions = int(st.get("open_positions", st.get("position_count", 0)) or 0)
                    status_text = str(st.get("status", "")).upper()
                    if open_positions > 0 or status_text in {"OPEN", "ACTIVE"}:
                        active_ok = True
                except Exception:
                    pass
            if not active_ok:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "reason_code": "ADD_RISK_REQUIRES_ACTIVE_TRADE",
                    "error": "Add-risk mode requires an existing active EA position for this account/symbol.",
                    "execution_mode": "ADD_RISK_TO_ACTIVE_TRADE",
                    "active_statuses": active_statuses,
                }

        # v125: Per trade idea risk cap. This lets Josh scale 0.25 + 0.25 + 0.50,
        # but blocks the classic human masterpiece: "just one more confirmation entry".
        trade_idea_id = _int_or_none_local(payload.get("trade_idea_id"))
        backend_trade_id = _int_or_none_local(payload.get("backend_trade_id"))
        if risk_percent > MAX_TRADE_IDEA_RISK_PERCENT:
            return {
                "ok": False,
                "status": "BLOCKED",
                "reason_code": "SINGLE_ENTRY_RISK_EXCEEDS_TRADE_IDEA_CAP",
                "error": f"Single entry risk {risk_percent:.2f}% exceeds max trade idea risk {MAX_TRADE_IDEA_RISK_PERCENT:.2f}%.",
                "requested_risk_pct": risk_percent,
                "max_trade_risk_pct": MAX_TRADE_IDEA_RISK_PERCENT,
            }

        if is_add_risk:
            if trade_idea_id is None and backend_trade_id is None:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "reason_code": "ADD_RISK_REQUIRES_TRADE_IDEA_ID",
                    "error": "Add-risk mode requires trade_idea_id or backend_trade_id so the backend can enforce the 1% total risk cap.",
                    "requested_add_risk_pct": risk_percent,
                    "max_trade_risk_pct": MAX_TRADE_IDEA_RISK_PERCENT,
                }

            risk_cap_snapshot = {}
            for acct_check in _account_list(account):
                if sql_trade_idea_risk_total is not None:
                    existing_risk = sql_trade_idea_risk_total(
                        account=acct_check,
                        symbol=symbol,
                        trade_idea_id=trade_idea_id,
                        backend_trade_id=backend_trade_id,
                    )
                else:
                    existing_risk = {
                        "account": acct_check,
                        "symbol": symbol,
                        "current_trade_risk_pct": float(payload.get("current_trade_risk_pct", 0.0) or 0.0),
                        "entries": [],
                        "warning": "sql_trade_idea_risk_total unavailable; using payload fallback only",
                    }
                current_risk = float(existing_risk.get("current_trade_risk_pct", 0.0) or 0.0)
                projected_risk = round(current_risk + risk_percent, 4)
                existing_risk["requested_add_risk_pct"] = risk_percent
                existing_risk["projected_trade_risk_pct"] = projected_risk
                existing_risk["max_trade_risk_pct"] = MAX_TRADE_IDEA_RISK_PERCENT
                risk_cap_snapshot[acct_check] = existing_risk
                if projected_risk > MAX_TRADE_IDEA_RISK_PERCENT + 1e-9:
                    block_msg = (
                        f"Add-risk blocked: current trade idea risk {current_risk:.2f}% + requested {risk_percent:.2f}% "
                        f"would exceed {MAX_TRADE_IDEA_RISK_PERCENT:.2f}%."
                    )
                    _safe_sql_blocked(
                        account=acct_check,
                        symbol=symbol,
                        direction=direction,
                        risk_percent=risk_percent,
                        reason_code="TRADE_IDEA_RISK_CAP_EXCEEDED",
                        message=block_msg,
                        payload={"android_payload": payload, "risk_cap": existing_risk},
                    )
                    return {
                        "ok": False,
                        "status": "BLOCKED",
                        "reason_code": "TRADE_IDEA_RISK_CAP_EXCEEDED",
                        "error": block_msg,
                        "current_trade_risk_pct": current_risk,
                        "requested_add_risk_pct": risk_percent,
                        "projected_trade_risk_pct": projected_risk,
                        "max_trade_risk_pct": MAX_TRADE_IDEA_RISK_PERCENT,
                        "risk_cap": risk_cap_snapshot,
                    }
        else:
            # New standalone trade idea starts its own cap: single entry may not exceed 1%.
            risk_cap_snapshot = {
                acct_check: {
                    "account": acct_check,
                    "symbol": symbol,
                    "current_trade_risk_pct": 0.0,
                    "requested_risk_pct": risk_percent,
                    "projected_trade_risk_pct": risk_percent,
                    "max_trade_risk_pct": MAX_TRADE_IDEA_RISK_PERCENT,
                }
                for acct_check in _account_list(account)
            }

        if sql_log_execute_attempt is not None:
            try:
                sql_log_execute_attempt(
                    account=account,
                    symbol=symbol,
                    direction=direction,
                    risk_percent=risk_percent,
                    sl_price=sl_price,
                    trade_type=payload.get("trade_type", ""),
                    entry_model=payload.get("entry_model", ""),
                    payload=payload,
                )
            except Exception:
                pass

        engine_gate = _engine_gate_status(symbol=symbol, trade_type=payload.get("trade_type"))
        if not engine_gate.get("allowed", True):
            block_msg = engine_gate.get("blockers", [{}])[0].get("message", "Daily/Intraday gate blocked execution.")
            _safe_sql_blocked(
                account=account, symbol=symbol, direction=direction, risk_percent=risk_percent,
                reason_code="DAILY_INTRADAY_GATE_BLOCK", message=block_msg,
                payload={"android_payload": payload, "engine_gate": engine_gate},
            )
            return {
                "ok": False,
                "status": "BLOCKED",
                "reason_code": "DAILY_INTRADAY_GATE_BLOCK",
                "error": block_msg,
                "engine_gate": engine_gate,
            }

        # Authoritative backend risk lock BEFORE writing commands.
        # Risk is only consumed AFTER command file is successfully written and verified.
        budget_snapshot = {}
        for acct in _account_list(account):
            if validate_execution_allowed is not None:
                check = validate_execution_allowed(
                    account=acct,
                    risk_percent=risk_percent,
                    symbol=symbol,
                    trade_type=payload.get("trade_type", ""),
                )
                budget_snapshot[acct] = check.get("summary", {})
                if not check.get("allowed"):
                    block_msg = check.get("error", f"Daily execution lock active for {acct}.")
                    _safe_sql_blocked(account=acct, symbol=symbol, direction=direction, risk_percent=risk_percent, reason_code="RISK_GUARD_BLOCK", message=block_msg, payload={"android_payload": payload, "risk_check": check})
                    return {
                        "ok": False,
                        "error": block_msg,
                        "budget": budget_snapshot,
                    }
            else:
                # Fallback, used only if risk_guard.py has not been copied yet.
                budget = _safe_daily_budget(acct)
                budget_snapshot[acct] = budget
                if budget.get("locked"):
                    block_msg = f"Daily limit reached for {acct}."
                    _safe_sql_blocked(account=acct, symbol=symbol, direction=direction, risk_percent=risk_percent, reason_code="DAILY_LIMIT_REACHED", message=block_msg, payload={"android_payload": payload, "budget": budget_snapshot})
                    return {"ok": False, "error": block_msg, "budget": budget_snapshot}
                remaining = budget.get("remaining_risk_percent")
                if remaining is not None:
                    try:
                        if float(remaining) < risk_percent:
                            block_msg = f"Insufficient remaining risk budget for {acct}."
                            _safe_sql_blocked(account=acct, symbol=symbol, direction=direction, risk_percent=risk_percent, reason_code="INSUFFICIENT_RISK_BUDGET", message=block_msg, payload={"android_payload": payload, "budget": budget_snapshot})
                            return {"ok": False, "error": block_msg, "budget": budget_snapshot}
                    except Exception:
                        pass

        state_snapshot = get_state(symbol)
        try:
            if sql_log_trade_event is not None:
                sql_log_trade_event(trade_id="", account=account, symbol=symbol, event_type="CONTEXT_CAPTURED", message="Context captured before execution", payload={"state": state_snapshot, "android_payload": payload})
        except Exception:
            pass
        executions = []
        journal_times = []

        for acct in _account_list(account):
            # New bridge supports account=. Older bridge will raise TypeError, then we fallback to funded-only style.
            try:
                execution = write_execute_command(
                    symbol=symbol,
                    direction=direction,
                    sl_price=sl_price,
                    risk_percent=risk_percent,
                    account=acct,
                    runner_target_r=float(payload.get("runner_target_r", 5.0) or 5.0),
                    enforce_guardrails=True,
                    allow_when_position_open=is_add_risk,
                )
            except TypeError:
                if acct != "funded":
                    raise RuntimeError("This mt5_bridge.py does not support account routing yet. Replace mt5_bridge.py with the multi-account version.")
                execution = write_execute_command(
                    symbol=symbol,
                    direction=direction,
                    sl_price=sl_price,
                    risk_percent=risk_percent,
                )

            # MT5 ticket confirmation is authoritative.
            # Do NOT fail the trade because the command file is empty after the EA has consumed it.
            # The old check caused false FAILED states even when MT5 opened tickets successfully.
            confirmation = execution.get("confirmation", {}) or {}
            tickets = confirmation.get("tickets") or []
            if confirmation.get("status") == "OPENED" and tickets:
                execution["confirmed"] = True
                execution["ok"] = True
            else:
                # Only verify command-file write when MT5 has NOT confirmed execution.
                path = execution.get("path")
                if path:
                    try:
                        from pathlib import Path
                        p = Path(path)
                        if not p.exists():
                            return {"ok": False, "status": "FAILED", "reason_code": "COMMAND_FILE_MISSING", "error": f"Command file path does not exist for {acct}.", "execution": execution}
                        # Empty command file can be normal after EA consumes command, so do not treat empty as automatic failure.
                    except Exception as exc:
                        return {"ok": False, "status": "FAILED", "reason_code": "COMMAND_FILE_VERIFY_FAILED", "error": f"Could not verify command file for {acct}: {exc}", "execution": execution}

            # Consume daily risk only after MT5 confirms actual ticket(s).
            if not execution.get("confirmed"):
                reason_code = "MT5_NO_TICKET" if confirmation.get("status") == "TIMEOUT" else "EA_REJECTED"
                block_msg = confirmation.get("message") or "MT5 did not confirm opened ticket(s)."
                _safe_sql_blocked(account=acct, symbol=symbol, direction=direction, risk_percent=risk_percent, reason_code=reason_code, message=block_msg, payload={"android_payload": payload, "execution": execution, "confirmation": confirmation})
                return {
                    "ok": False,
                    "status": confirmation.get("status", "FAILED"),
                    "reason_code": reason_code,
                    "error": block_msg,
                    "account": acct,
                    "symbol": symbol,
                    "execution": execution,
                    "budget": {acct: _safe_daily_budget(acct)},
                }

            if record_execution_utilised is not None:
                try:
                    record_execution_utilised(
                        account=acct,
                        symbol=symbol,
                        direction=direction,
                        risk_percent=risk_percent,
                        trade_id=execution.get("trade_id", ""),
                        command_file=execution.get("path", "") or execution.get("file", ""),
                        trade_type=payload.get("trade_type", ""),
                        entry_model=payload.get("entry_model", ""),
                        notes=payload.get("notes", ""),
                        micro_checklist=payload.get("micro_checklist", {}),
                        tickets=tickets,
                        source="mt5_ticket_confirmed",
                    )
                except Exception as exc:
                    return {
                        "ok": False,
                        "error": f"Command written, but daily lock record failed for {acct}: {exc}",
                        "execution": execution,
                    }

            log_payload = {
                "account": acct,
                "execution": execution,
                "state_snapshot": state_snapshot,
                "risk_cap_snapshot": risk_cap_snapshot,
                "android_payload": {
                    "account": account,
                    "trade_idea_id": trade_idea_id,
                    "backend_trade_id": backend_trade_id,
                    "execution_mode": "ADD_RISK_TO_ACTIVE_TRADE" if is_add_risk else "NEW_TRADE",
                    "add_risk": bool(is_add_risk),
                    "trade_type": payload.get("trade_type"),
                    "entry_model": payload.get("entry_model"),
                    "htf_context": payload.get("htf_context"),
                    "notes": payload.get("notes"),
                    "micro_checklist": payload.get("micro_checklist", {}),
                },
                "summary": {
                    "macro_location": state_snapshot.get("macro", {}).get("location_label"),
                    "weekly_location": state_snapshot.get("weekly", {}).get("location_label"),
                    "daily_location": state_snapshot.get("daily", {}).get("location_label"),
                    "intraday_phase": state_snapshot.get("intraday", {}).get("phase_label"),
                    "intraday_profile": state_snapshot.get("intraday", {}).get("profile_label"),
                },
            }
            journal_entry = _safe_log_execute_sent(log_payload)
            if journal_entry:
                journal_times.append(journal_entry.get("time"))

            if sql_log_trade_opened is not None:
                try:
                    sql_log_trade_opened(
                        account=acct,
                        symbol=symbol,
                        trade_id=execution.get("trade_id", ""),
                        direction=direction,
                        risk_percent=risk_percent,
                        runner_target_r=float(payload.get("runner_target_r", 5.0) or 5.0),
                        management_profile=payload.get("management_profile", "tiered_2R_3R_runner"),
                        trade_type=payload.get("trade_type", ""),
                        entry_model=payload.get("entry_model", ""),
                        sl_price=sl_price,
                        tickets=[str(t) for t in tickets],
                        payload=log_payload,
                        trade_idea_id=trade_idea_id,
                        backend_trade_id=backend_trade_id,
                        execution_mode="ADD_RISK_TO_ACTIVE_TRADE" if is_add_risk else "NEW_TRADE",
                        is_add_risk=bool(is_add_risk),
                    )
                except Exception:
                    pass

            _safe_sql_context(
                trade_id=execution.get("trade_id", ""),
                account=acct,
                symbol=symbol,
                source="trade_execute",
                state_snapshot=state_snapshot,
                payload=payload,
            )

            executions.append(execution)

        return {
            "ok": True,
            "message": "Trade opened and MT5 ticket confirmed." if len(executions) == 1 else "Trades opened and MT5 tickets confirmed.",
            "account": account,
            "trade_id": executions[0].get("trade_id") if executions else None,
            "executions": executions,
            "journal_times": journal_times,
            "budget": {acct: _safe_daily_budget(acct) for acct in _account_list(account)},
            "resolved_sl": sl_resolved_payload,
        }
    except PermissionError as exc:
        acct = _normalise_account(payload.get("account", "funded"))
        sym = _normalise_symbol(payload.get("symbol", "XAUUSD"))
        _safe_sql_blocked(account=acct, symbol=sym, direction=str(payload.get("direction", "")).upper(), risk_percent=float(payload.get("risk_percent", 0) or 0), reason_code="PERMISSION_ERROR", message=str(exc), payload={"android_payload": payload})
        return {"ok": False, "error": str(exc), "budget": {a: _safe_daily_budget(a) for a in _account_list(acct)}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}



# =============================
# V1.03 Journal + notification helper endpoints
# =============================
def _safe_read_jsonl(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows[-limit:][::-1]
    except Exception:
        return []


@app.get("/journal/recent")
def journal_recent(limit: int = 30):
    path = Path("logs") / "auto_journal.jsonl"
    rows = _safe_read_jsonl(path, max(1, min(int(limit or 30), 100)))
    trades = []
    for ev in rows:
        payload = ev.get("payload", {}) or {}
        execution = payload.get("execution", {}) or {}
        android_payload = payload.get("android_payload", {}) or {}
        trades.append({
            "time": ev.get("time"),
            "event_type": ev.get("event_type"),
            "account": execution.get("account") or payload.get("account") or android_payload.get("account"),
            "symbol": execution.get("symbol") or payload.get("symbol"),
            "direction": execution.get("direction") or payload.get("direction"),
            "risk_percent": execution.get("risk_percent") or payload.get("risk_percent"),
            "trade_id": execution.get("trade_id") or payload.get("trade_id"),
            "trade_type": android_payload.get("trade_type") or payload.get("trade_type"),
            "entry_model": android_payload.get("entry_model") or payload.get("entry_model"),
            "tickets": ((execution.get("confirmation") or {}).get("tickets") or []),
            "message": ev.get("event_type"),
        })
    return {"ok": True, "last_refresh": _now_sast_iso(), "count": len(trades), "trades": trades}



@app.get("/sql/trades/recent")
def sql_trades_recent(limit: int = 50):
    if sql_recent_trades is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return {"ok": True, "count": min(max(int(limit or 50), 1), 200), "trades": sql_recent_trades(limit=limit)}


@app.get("/sql/blocked/recent")
def sql_blocked_recent(limit: int = 50):
    if sql_recent_blocked is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return {"ok": True, "count": min(max(int(limit or 50), 1), 200), "blocked": sql_recent_blocked(limit=limit)}


@app.get("/sql/status")
def sql_status():
    if sql_db_status is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return sql_db_status()


@app.get("/sql/events/recent")
def sql_events_recent(limit: int = 100, trade_id: str | None = None):
    if sql_recent_events is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return {"ok": True, "events": sql_recent_events(limit=limit, trade_id=trade_id)}


@app.get("/sql/context/recent")
def sql_context_recent(limit: int = 50):
    if sql_recent_context is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return {"ok": True, "contexts": sql_recent_context(limit=limit)}


@app.get("/sql/backtest/recent")
def sql_backtest_recent(limit: int = 100):
    if sql_recent_backtest_samples is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    return {"ok": True, "samples": sql_recent_backtest_samples(limit=limit)}


@app.post("/sql/backtest/sample")
def sql_backtest_sample(payload: dict = Body(...)):
    if sql_log_backtest_sample is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    sample = sql_log_backtest_sample(payload)
    return {"ok": True, "sample": sample}


@app.post("/sql/backtest/import")
def sql_backtest_import(payload: dict = Body(...)):
    if sql_log_backtest_sample is None:
        return {"ok": False, "error": "sql_journal unavailable"}
    rows = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"ok": False, "error": "Expected { samples: [...] }"}
    saved = []
    for row in rows:
        if isinstance(row, dict):
            saved.append(sql_log_backtest_sample(row))
    return {"ok": True, "count": len(saved), "samples": saved}



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flat_execution_event_from_status(
    *,
    status: dict[str, Any],
    account: str,
    symbol: str,
    event_type: str,
    event_reason: str = "",
    event_source: str = "EA_STATUS_FILE",
    idempotency_suffix: str | None = None,
) -> dict[str, Any]:
    trade_id = str(status.get("trade_id") or status.get("active_trade_id") or "")
    suffix = idempotency_suffix or event_type
    return {
        "idempotency_key": f"{account}_{symbol}_{trade_id}_{suffix}",
        "trade_id": trade_id,
        "account": account,
        "account_id": account,
        "symbol": symbol,
        "event_type": event_type,
        "event_source": event_source,
        "event_reason": event_reason,
        "timestamp_utc": _utc_now_iso(),
        "price": status.get("current_price"),
        "volume_after": status.get("lots"),
        "current_sl": status.get("sl") or status.get("last_locked_sl"),
        "current_tp": status.get("tp"),
        "profit_total_open": status.get("floating_profit"),
        "r_realized": None,
        "partial_r_realized": status.get("current_r") if event_type in {"TP1_HIT", "TP2_HIT"} else None,
        "raw_payload": status,
        "notes": f"Derived from EA live status flag: {event_type}",
    }


def _flat_execution_event_from_result(
    *,
    result: dict[str, Any],
    account: str,
    symbol: str,
) -> dict[str, Any]:
    trade_id = str(result.get("trade_id") or "")
    r_multiple = result.get("r_multiple")
    outcome = str(result.get("outcome") or "").upper()
    event_type = "STOPPED_OUT" if outcome == "LOSS" else "TRADE_CLOSED"
    # RESULT file is overwritten by EA for the last closed trade; use raw line in key so a changed result is not hidden.
    raw_key = str(result.get("raw") or result.get("closed_at") or _utc_now_iso())
    return {
        "idempotency_key": f"{account}_{symbol}_{trade_id}_{event_type}_{abs(hash(raw_key))}",
        "trade_id": trade_id,
        "account": account,
        "account_id": account,
        "symbol": symbol,
        "event_type": event_type,
        "event_source": "EA_RESULT_FILE",
        "event_reason": outcome or "RESULT_FILE_SYNC",
        "timestamp_utc": _utc_now_iso(),
        "price": None,
        "volume_after": 0.0,
        "volume_closed": None,
        "profit_realized": result.get("profit_money"),
        "r_realized": r_multiple,
        "partial_r_realized": None,
        "raw_payload": result,
        "notes": "Derived from EA RESULT file.",
    }


def _insert_flat_event(payload: dict[str, Any]) -> dict[str, Any]:
    if sql_log_execution_event_flat is not None:
        return sql_log_execution_event_flat(payload)

    # Legacy fallback. Still idempotent enough through event_key.
    if sql_log_trade_event is None:
        return {"ok": False, "error": "No SQL event logger available", "payload": payload}

    return sql_log_trade_event(
        trade_id=str(payload.get("trade_id") or ""),
        account=str(payload.get("account") or payload.get("account_id") or ""),
        symbol=str(payload.get("symbol") or ""),
        event_type=str(payload.get("event_type") or ""),
        message=str(payload.get("notes") or payload.get("event_reason") or ""),
        payload=payload,
        event_key=str(payload.get("idempotency_key") or ""),
    )


def _derive_state_for_trade(trade_id: str) -> dict[str, Any] | None:
    if reduce_trade_state is None or sql_events_for_trade is None or sql_trade_context is None or not trade_id:
        return None
    try:
        events = sql_events_for_trade(trade_id=trade_id)
        context = sql_trade_context(trade_id=trade_id)
        state = reduce_trade_state(events, context)
        unlock_at = None
        try:
            unlock_at = close_lock_unlock_threshold(state.direction) if close_lock_unlock_threshold else None
        except Exception:
            unlock_at = None
        return {
            "trade_id": state.trade_id,
            "symbol": state.symbol,
            "state": state.current_lifecycle_state,
            "current_lifecycle_state": state.current_lifecycle_state,
            "is_close_locked": state.is_close_locked,
            "close_lock_active": state.is_close_locked,
            "direction": state.direction,
            "latest_price": state.latest_price,
            # Backward compatible field name. Frontends should label this as
            # Daily Range Position %, where 0% = Daily Low and 100% = Daily High.
            "retracement_percent": state.retracement_percent,
            "daily_range_position_percent": state.retracement_percent,
            "close_lock_unlock_at": unlock_at,
            "close_lock_rule": "BULLISH unlocks at <=45% daily range position; BEARISH unlocks at >=55% daily range position",
            "volume_remaining": state.volume_remaining,
            "infractions": state.infractions,
        }
    except Exception as exc:
        return {"error": str(exc), "trade_id": trade_id}




# =============================
# V128 UNIFIED MAP STATE + SMART SL ENGINE
# =============================
VALID_TIMEFRAMES = {"weekly", "daily", "intraday"}


def _safe_layer_state(payload: dict[str, Any] | None, timeframe: str) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    return {
        "timeframe": timeframe,
        "anchors": payload.get("anchors") if isinstance(payload.get("anchors"), list) else [],
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        "visual": payload.get("visual") if isinstance(payload.get("visual"), dict) else payload,
        "telemetry": payload.get("telemetry") if isinstance(payload.get("telemetry"), dict) else {},
        "updated_at": payload.get("updated_at") or _now_sast_iso(),
    }


def _normalise_map_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept Electron v026 visual_state or the newer shared layers payload.

    Backend stores the canonical envelope. Frontends can still send old payloads
    while Android catches up, because apparently backwards compatibility is the
    adult in the room.
    """
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    visual_state = payload.get("visual_state") or payload.get("visuals") or {}
    journal_ready = payload.get("journal_ready") or {}
    layers_in = payload.get("layers") or {}

    layers: dict[str, Any] = {}
    for tf in ("weekly", "daily", "intraday"):
        layer_payload = {}
        if isinstance(layers_in, dict) and isinstance(layers_in.get(tf), dict):
            layer_payload.update(layers_in.get(tf) or {})
        if isinstance(visual_state, dict) and isinstance(visual_state.get(tf), dict):
            layer_payload.setdefault("visual", visual_state.get(tf) or {})
        if isinstance(journal_ready, dict) and isinstance(journal_ready.get(tf), dict):
            jr = journal_ready.get(tf) or {}
            layer_payload.setdefault("anchors", jr.get("anchors") or [])
            layer_payload.setdefault("meta", {k: v for k, v in jr.items() if k != "anchors"})
        layers[tf] = _safe_layer_state(layer_payload, tf)

    telemetry = payload.get("telemetry") if isinstance(payload.get("telemetry"), dict) else {}
    return {
        "symbol": symbol,
        "version": payload.get("version") or "v128_unified_map_state",
        "saved_at": _now_sast_iso(),
        "updated_at": _now_sast_iso(),
        "updated_by": payload.get("updated_by") or "unknown",
        "updated_from_device": payload.get("updated_from_device") or payload.get("device_source") or "unknown",
        "layers": layers,
        "visual_state": visual_state,
        "journal_ready": journal_ready,
        "telemetry": telemetry,
        "raw_payload": payload,
    }


def _load_symbol_map(symbol: str) -> dict[str, Any] | None:
    symbol = _normalise_symbol(symbol)
    store = _load_map_state_store()
    item = store.get(symbol)
    return item if isinstance(item, dict) else None


def _save_symbol_map(symbol: str, record: dict[str, Any]) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    store = _load_map_state_store()
    previous = store.get(symbol) if isinstance(store.get(symbol), dict) else {}
    version_counter = int(previous.get("state_version") or 0) + 1
    record["state_version"] = version_counter
    record["updated_at"] = _now_sast_iso()
    store[symbol] = record
    _save_map_state_store(store)
    return record


def _update_map_anchor(record: dict[str, Any], timeframe: str, anchor_key: str, patch: dict[str, Any]) -> dict[str, Any]:
    timeframe = str(timeframe or "intraday").lower()
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError("timeframe must be weekly, daily, or intraday")
    anchor_key = str(anchor_key or "").strip().upper()
    if not anchor_key:
        raise ValueError("anchor_key is required")
    record.setdefault("layers", {})
    layer = record["layers"].setdefault(timeframe, _safe_layer_state({}, timeframe))
    anchors = layer.setdefault("anchors", [])
    found = False
    for a in anchors:
        if str(a.get("anchor_key") or a.get("label") or "").upper() == anchor_key:
            a.update({k: v for k, v in patch.items() if v is not None})
            a["anchor_key"] = anchor_key
            found = True
            break
    if not found:
        row = {"anchor_key": anchor_key, "timeframe": timeframe.upper(), "status": "INTACT"}
        row.update({k: v for k, v in patch.items() if v is not None})
        anchors.append(row)
    layer["updated_at"] = _now_sast_iso()
    return record


def _resolve_sl_from_digits(*, direction: str, live_price: float, digits: str) -> dict[str, Any]:
    direction = str(direction or "BUY").upper().strip()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("direction must be BUY or SELL")
    live = float(live_price)
    raw = str(digits or "").strip().replace(",", ".")
    if not raw:
        raise ValueError("digits is required")

    # Full manual price wins if the user typed the whole thing.
    try:
        full = float(raw)
        if full > 100:
            return {"ok": True, "direction": direction, "live_price": live, "input": raw, "resolved_sl": round(full, 2), "mode": "FULL_PRICE"}
    except Exception:
        pass

    short = int(float(raw))
    if short < 0 or short > 99:
        raise ValueError("short digits must be between 0 and 99")

    block = int(live // 100) * 100
    candidates = [block - 100 + short, block + short, block + 100 + short]
    if direction == "BUY":
        valid = [c for c in candidates if c < live]
        resolved = max(valid) if valid else block - 100 + short
    else:
        valid = [c for c in candidates if c > live]
        resolved = min(valid) if valid else block + 100 + short
    return {"ok": True, "direction": direction, "live_price": live, "input": raw, "resolved_sl": round(float(resolved), 2), "mode": "LAST_TWO_DIGITS"}


@app.get("/api/v1/maps/state")
def get_map_state(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    saved = _load_symbol_map(symbol)
    if not saved:
        return {"ok": True, "found": False, "symbol": symbol, "state": None}
    return {"ok": True, "found": True, "symbol": symbol, "state": saved}


@app.get("/maps/state")
def get_map_state_alias(symbol: str = "XAUUSD"):
    return get_map_state(symbol=symbol)


@app.post("/api/v1/maps/state")
def save_map_state(payload: dict = Body(...)):
    record = _normalise_map_payload(payload)
    record = _save_symbol_map(record["symbol"], record)
    structured = None
    try:
        if sql_save_map_state_structured is not None:
            structured = sql_save_map_state_structured(record)
    except Exception as exc:
        structured = {"ok": False, "error": str(exc)}
    return {"ok": True, "symbol": record["symbol"], "saved_at": record["saved_at"], "updated_at": record["updated_at"], "state_version": record["state_version"], "version": record["version"], "structured_journal": structured}


@app.post("/maps/save")
def save_map_state_alias(payload: dict = Body(...)):
    return save_map_state(payload)


@app.post("/maps/update-anchor")
def update_map_anchor(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    record = _load_symbol_map(symbol) or _normalise_map_payload({"symbol": symbol, "updated_from_device": payload.get("updated_from_device") or "unknown"})
    patch = {
        "price": payload.get("price"),
        "status": payload.get("status"),
        "role": payload.get("role"),
        "sequence_column": payload.get("sequence_column"),
        "zone": payload.get("zone"),
        "label": payload.get("label"),
    }
    record = _update_map_anchor(record, str(payload.get("timeframe") or "intraday"), str(payload.get("anchor_key") or ""), patch)
    record["updated_by"] = payload.get("updated_by") or "android_quick_editor"
    record["updated_from_device"] = payload.get("updated_from_device") or "android"
    record = _save_symbol_map(symbol, record)
    return {"ok": True, "symbol": symbol, "state_version": record["state_version"], "state": record}


@app.post("/maps/update-state")
def update_map_state_fields(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    timeframe = str(payload.get("timeframe") or "intraday").lower()
    if timeframe not in VALID_TIMEFRAMES:
        return {"ok": False, "error": "timeframe must be weekly, daily, or intraday"}
    record = _load_symbol_map(symbol) or _normalise_map_payload({"symbol": symbol})
    layer = record.setdefault("layers", {}).setdefault(timeframe, _safe_layer_state({}, timeframe))
    meta = layer.setdefault("meta", {})
    for key in ("profile", "phase_state", "delivery_state", "reaction_state", "continuation_state", "entry_model", "objective_1", "objective_2", "bias"):
        if key in payload:
            meta[key] = payload.get(key)
    if "telemetry" in payload and isinstance(payload.get("telemetry"), dict):
        layer["telemetry"] = {**(layer.get("telemetry") or {}), **payload["telemetry"]}
    layer["updated_at"] = _now_sast_iso()
    record["updated_by"] = payload.get("updated_by") or "state_update"
    record["updated_from_device"] = payload.get("updated_from_device") or "unknown"
    record = _save_symbol_map(symbol, record)
    return {"ok": True, "symbol": symbol, "state_version": record["state_version"], "state": record}


@app.post("/api/v1/sl/resolve")
def resolve_smart_sl(payload: dict = Body(...)):
    try:
        live_price = payload.get("live_price") or payload.get("current_price")
        if live_price is None:
            symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
            live_price = _get_current_price_for_symbol(symbol)
        if live_price is None:
            return {"ok": False, "error": "live_price/current_price is required when backend cannot read a live price"}
        return _resolve_sl_from_digits(direction=str(payload.get("direction") or "BUY"), live_price=float(live_price), digits=str(payload.get("digits") or payload.get("sl_digits") or payload.get("input") or ""))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/trade/sl/resolve")
def resolve_smart_sl_alias(payload: dict = Body(...)):
    return resolve_smart_sl(payload)


@app.get("/api/v1/lifecycle/state")
def lifecycle_state(trade_id: str | None = None, backend_trade_id: int | None = None):
    try:
        if backend_trade_id is not None and sql_events_for_trade is not None and sql_trade_context is not None and reduce_trade_state is not None:
            events = sql_events_for_trade(backend_trade_id=backend_trade_id)
            context = sql_trade_context(backend_trade_id=backend_trade_id)
            state = reduce_trade_state(events, context)
            return {"ok": True, "state": state.__dict__ if hasattr(state, "__dict__") else state}
        if trade_id:
            return {"ok": True, "state": _derive_state_for_trade(trade_id)}
        return {"ok": False, "error": "trade_id or backend_trade_id required"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}



@app.get("/api/v1/lifecycle/snapshot")
def get_lifecycle_snapshot(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    snap = _load_lifecycle_snapshot(symbol)
    return {"ok": True, "symbol": symbol, "snapshot": snap}


@app.post("/api/v1/lifecycle/snapshot")
def save_lifecycle_snapshot(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    snap = _save_lifecycle_snapshot(symbol, payload)
    return {"ok": True, "symbol": symbol, "snapshot": snap, "updated_at": snap.get("updated_at")}


@app.post("/api/v1/lifecycle/catch-up")
def catch_up_lifecycle_snapshot(payload: dict = Body(...)):
    """Explicit alias for Electron/Android catch-up wizard.

    This is manual market-state memory, not execution. It tells the machine what
    Josh already knows from the chart so the lifecycle brain stops guessing from
    empty/default map state like a brave little idiot.
    """
    return save_lifecycle_snapshot(payload)


@app.get("/api/version")
def api_version():
    return {"backend_version": "v136_finalized_journal_mitigation_memory", "ea_changed": False}


@app.post("/api/v1/execution/event")
def ingest_execution_event(payload: dict = Body(...)):
    """Flat event ingestion endpoint for future EA WebRequest support.

    Current EA does not need to use this yet. This endpoint is ready for the day
    we want direct POST events instead of status/result file polling.
    """
    try:
        if not payload.get("event_type"):
            return {"ok": False, "error": "event_type is required"}
        if not payload.get("idempotency_key"):
            payload["idempotency_key"] = f"{payload.get('account_id') or payload.get('account')}_{payload.get('symbol')}_{payload.get('trade_id') or payload.get('broker_ticket_id')}_{payload.get('event_type')}_{payload.get('timestamp_utc') or _utc_now_iso()}"

        # Route-level duplicate guard. This runs BEFORE any write path, so even if
        # SQLite migrations, legacy event_key rows, or helper imports behave badly,
        # the API refuses to create another row for the same idempotency key.
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if idempotency_key and sql_get_event_by_idempotency_key is not None:
            existing_event = sql_get_event_by_idempotency_key(idempotency_key)
            if existing_event:
                return {
                    "ok": True,
                    "backend_version": "v136_finalized_journal_mitigation_memory",
                    "duplicate": True,
                    "message": "duplicate ignored at route guard; existing event returned",
                    "existing_event": existing_event,
                }

        trade_id = str(payload.get("trade_id") or "")
        historical_events = []
        static_context = {}
        pre_state = None
        if trade_id and sql_events_for_trade is not None and sql_trade_context is not None and reduce_trade_state is not None:
            historical_events = sql_events_for_trade(trade_id=trade_id)
            static_context = sql_trade_context(trade_id=trade_id)
            pre_state = reduce_trade_state(historical_events, static_context)

        inserted = _insert_flat_event(payload)

        breach = None
        if pre_state is not None and check_compliance_violation is not None:
            try:
                news_status = _news_execution_block_status(symbol=str(payload.get("symbol") or "XAUUSD"))
                breach = check_compliance_violation(pre_state, payload, bool(news_status.get("blocked")))
                if breach:
                    _insert_flat_event(breach)
            except Exception as exc:
                breach = {"error": str(exc)}

        final_state = _derive_state_for_trade(trade_id) if trade_id else None
        is_duplicate = bool(inserted.get("duplicate")) if isinstance(inserted, dict) else False
        if is_duplicate:
            return {
                "ok": True,
                "backend_version": "v136_finalized_journal_mitigation_memory",
                "duplicate": True,
                "message": "duplicate ignored; existing event returned",
                "existing_event": inserted,
                "breach": breach,
                "derived_state": final_state,
            }
        return {
            "ok": True,
            "backend_version": "v136_finalized_journal_mitigation_memory",
            "duplicate": False,
            "message": "event inserted",
            "inserted_event": inserted,
            "breach": breach,
            "derived_state": final_state,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/trade/sync-status")
def trade_sync_status(account: str = "funded", symbol: str = "XAUUSD"):
    """Pull current EA status/result files and write lifecycle events to SQL.

    This is intentionally backend-only. The EA remains untouched: it already writes
    live-status JSON and RESULT lines, so the backend can derive the event ledger
    without risking EA execution stability. A tiny miracle, apparently.
    """
    if read_live_trade_status is None:
        return {"ok": False, "error": "mt5_bridge.read_live_trade_status unavailable"}

    account_n = _normalise_account(account)
    symbol_n = _normalise_symbol(symbol)
    status = read_live_trade_status(account=account_n, symbol=symbol_n) or {}
    trade_id = str(status.get("trade_id") or "")

    events: list[dict[str, Any]] = []

    # 1) Open trade / milestone events from status file.
    if trade_id:
        try:
            open_positions = int(status.get("open_positions") or status.get("position_count") or 0)
        except Exception:
            open_positions = 0

        if open_positions > 0:
            events.append(_insert_flat_event(_flat_execution_event_from_status(
                status=status,
                account=account_n,
                symbol=symbol_n,
                event_type="ENTRY",
                event_reason="EA_OPEN_POSITION_STATUS",
                idempotency_suffix="ENTRY",
            )))

        for flag, event_type, reason in (
            ("tp1_confirmed", "TP1_HIT", "TP1_2R_CONFIRMED"),
            ("tp2_confirmed", "TP2_HIT", "TP2_3R_CONFIRMED"),
            ("runner_sl_moved", "SL_MOVED", "RUNNER_SL_MOVED"),
        ):
            val = status.get(flag)
            if val is True or str(val).lower() in {"true", "1", "yes"}:
                events.append(_insert_flat_event(_flat_execution_event_from_status(
                    status=status,
                    account=account_n,
                    symbol=symbol_n,
                    event_type=event_type,
                    event_reason=reason,
                    idempotency_suffix=event_type,
                )))

    # 2) Final outcome from EA RESULT file. This still works after the status file
    # clears trade_id because RESULT carries the trade_id.
    result_payload = None
    if read_trade_result is not None:
        try:
            result_payload = read_trade_result(account=account_n, symbol=symbol_n)
        except TypeError:
            result_payload = read_trade_result(account=account_n)
        except Exception as exc:
            result_payload = {"ok": False, "error": str(exc)}

    if result_payload and result_payload.get("valid") and result_payload.get("event") == "trade_result":
        events.append(_insert_flat_event(_flat_execution_event_from_result(
            result=result_payload,
            account=account_n,
            symbol=symbol_n,
        )))
        if not trade_id:
            trade_id = str(result_payload.get("trade_id") or "")

    derived_state = _derive_state_for_trade(trade_id) if trade_id else None

    return {
        "ok": True,
        "account": account_n,
        "symbol": symbol_n,
        "status": status,
        "result": result_payload,
        "events": events,
        "derived_state": derived_state,
    }



# =============================
# V129 TRADE LIFECYCLE BRAIN + QUICK TRADE IDEAS
# =============================
QUICK_TRADE_IDEAS_FILE = Path(__file__).resolve().parent / "quick_trade_ideas.json"
LIFECYCLE_SNAPSHOT_FILE = Path(__file__).resolve().parent / "lifecycle_snapshot_store.json"


def _load_quick_trade_ideas_store() -> dict[str, Any]:
    try:
        if QUICK_TRADE_IDEAS_FILE.exists():
            raw = QUICK_TRADE_IDEAS_FILE.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_quick_trade_ideas_store(store: dict[str, Any]) -> None:
    try:
        QUICK_TRADE_IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUICK_TRADE_IDEAS_FILE.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _load_lifecycle_snapshot_store() -> dict[str, Any]:
    try:
        if LIFECYCLE_SNAPSHOT_FILE.exists():
            raw = LIFECYCLE_SNAPSHOT_FILE.read_text(encoding="utf-8")
            if raw.strip():
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_lifecycle_snapshot_store(store: dict[str, Any]) -> None:
    try:
        LIFECYCLE_SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        LIFECYCLE_SNAPSHOT_FILE.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _default_lifecycle_snapshot(symbol: str) -> dict[str, Any]:
    return {
        "symbol": _normalise_symbol(symbol),
        "version": "v130_lifecycle_snapshot",
        "macro": {
            "macro_state": "MACRO_CONTEXT_MANUAL",
            "macro_low": None,
            "macro_high": None,
            "abandoned_macro_low": None,
            "abandoned_macro_high": None,
            "new_macro_swing_high": None,
            "new_macro_swing_low": None,
            "macro_bias_context": "WATCHING",
        },
        "weekly": {
            "weekly_state": "WEEKLY_CONTEXT_ACTIVE",
            "weekly_bias": "WATCHING",
            "weekly_profile": "WAITING",
            "inducement_swing": "NOT_TAGGED",
            "objective_1": "FAIR_PRICE",
            "objective_2": "PREMIUM_M1_OR_DISCOUNT_M1",
            "objective_3": "EXT_IF_MACRO_ALIGNED",
        },
        "daily": {
            "daily_state": "DAILY_PRE_CHOCH",
            "daily_profile": "WAITING",
            "daily_phase": "PRE_CHOCH",
            "structure_event": "WAITING",
            "previous_day_sweep": "NONE",
            "inducement_swing": "NOT_TAGGED",
            "retest_status": "WAITING",
            "profile_transition": "NO_PROFILE_FLIP",
        },
        "intraday": {
            "intraday_state": "INTRADAY_PRE_CHOCH",
            "intraday_profile": "WAITING",
            "phase_state": "PRE_CHOCH",
            "favourable_trade": "NO_FAVOURABLE_TRADE",
            "retest_status": "WAITING",
            "choch_high": None,
            "choch_break": None,
            "choch_low": None,
            "liquidity_cleanup_price": None,
        },
        "micro": {
            "confirmation": "WAITING",
            "trigger_timeframe": "15M",
            "trigger_model": "WAITING",
        },
        "notes": "",
        "updated_at": _now_sast_iso(),
        "updated_by": "system_default",
        "updated_from_device": "backend",
    }


def _deep_merge_v130(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base or {})
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge_v130(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def _load_lifecycle_snapshot(symbol: str) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    store = _load_lifecycle_snapshot_store()
    saved = store.get(symbol) if isinstance(store.get(symbol), dict) else {}
    return _deep_merge_v130(_default_lifecycle_snapshot(symbol), saved)


def _save_lifecycle_snapshot(symbol: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    store = _load_lifecycle_snapshot_store()
    previous = store.get(symbol) if isinstance(store.get(symbol), dict) else {}
    merged = _deep_merge_v130(_default_lifecycle_snapshot(symbol), previous)
    merged = _deep_merge_v130(merged, snapshot or {})
    merged["symbol"] = symbol
    merged["version"] = "v130_lifecycle_snapshot"
    merged["updated_at"] = _now_sast_iso()
    merged["updated_by"] = (snapshot or {}).get("updated_by") or merged.get("updated_by") or "unknown"
    merged["updated_from_device"] = (snapshot or {}).get("updated_from_device") or merged.get("updated_from_device") or "unknown"
    store[symbol] = merged
    _save_lifecycle_snapshot_store(store)
    try:
        if sql_save_lifecycle_snapshot_structured is not None:
            sql_save_lifecycle_snapshot_structured(symbol, merged)
    except Exception:
        pass
    return merged


def _normalise_enum_text_v130(value: Any, default: str = "WAITING") -> str:
    return str(value if value not in (None, "") else default).strip().upper().replace(" ", "_").replace("/", "_")


_EMPTY_STATE_VALUES_V132 = {"", "WAITING", "WATCHING", "NONE", "NOT_SET", "UNKNOWN", "PRE_CHOCH", "DAILY_PRE_CHOCH", "NO_FAVOURABLE_TRADE", "NO_PROFILE_FLIP", "NOT_TAGGED"}


def _prefer_real_value_v132(primary: Any, fallback: Any, default: Any = None, empty_values: set[str] | None = None) -> Any:
    """Prefer explicit snapshot values, but let map values override defaults.

    v130 merged defaults into the lifecycle snapshot. That made fields like
    daily_profile=WAITING and phase_state=PRE_CHOCH look intentional, so the
    brain ignored the map. v132 treats those default values as empty and pulls
    the live map language first. Tiny difference, huge reduction in garbage.
    """
    empties = empty_values or _EMPTY_STATE_VALUES_V132
    if primary not in (None, ""):
        txt = str(primary).strip().upper().replace(" ", "_").replace("/", "_")
        if txt not in empties:
            return primary
    if fallback not in (None, ""):
        return fallback
    return default if default is not None else primary


def _visual_meta_value_v132(layer: dict[str, Any], *keys: str) -> Any:
    visual = layer.get("visual") or {}
    meta = layer.get("meta") or {}
    for src in (visual, meta):
        for key in keys:
            if isinstance(src, dict) and src.get(key) not in (None, ""):
                return src.get(key)
    return None


def _range_from_layer_v132(layer: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract low/high from visual, meta, or anchors.

    This lets Daily/Weekly lifecycle pull from the actual map even when the
    catch-up wizard has not been filled in. The map is the user's source of
    range truth, not the wizard default screen having an existential moment.
    """
    low = _float_or_none_v129(_visual_meta_value_v132(layer, "rangeLow", "range_low", "low", "ext_l", "EXT_L"))
    high = _float_or_none_v129(_visual_meta_value_v132(layer, "rangeHigh", "range_high", "high", "ext_h", "EXT_H"))
    if low is None:
        low = _price_from_anchor_v129(layer, "EXT_L") or _price_from_anchor_v129(layer, "RANGE_L")
    if high is None:
        high = _price_from_anchor_v129(layer, "EXT_H") or _price_from_anchor_v129(layer, "RANGE_H")
    return low, high


def _map_meta_alias_v132(meta: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if meta.get(key) not in (None, ""):
            return meta.get(key)
    return None


def _choch_gateway_metrics_v130(intraday_snapshot: dict[str, Any]) -> dict[str, Any]:
    hi = _float_or_none_v129(intraday_snapshot.get("choch_high"))
    br = _float_or_none_v129(intraday_snapshot.get("choch_break"))
    lo = _float_or_none_v129(intraday_snapshot.get("choch_low"))
    if hi is None or lo is None or hi == lo:
        return {"complete": False, "choch_depth": None, "break_efficiency": None}
    depth = abs(hi - lo)
    if br is None:
        eff = None
    else:
        # Direction-agnostic location of the breaking point inside the CHOCH gateway.
        eff = round(abs(br - lo) / depth, 4)
    return {"complete": br is not None, "choch_depth": round(depth, 2), "break_efficiency": eff, "choch_high": hi, "choch_break": br, "choch_low": lo}


def _interpret_daily_v130(position_pct: float | None, profile: str, structure_event: str, macro_aligned: bool = False) -> dict[str, Any]:
    profile_u = _normalise_enum_text_v130(profile)
    event_u = _normalise_enum_text_v130(structure_event)
    if position_pct is None:
        return {"daily_bias": "WATCHING", "context": "DAILY_RANGE_INCOMPLETE", "allowed_direction": "NONE", "objective_ladder": [], "close_lock_unlock_position": None, "external_allowed": False}

    if any(x in profile_u for x in ["SND", "S_D", "S&D", "DEEP_RETRACE"]):
        if position_pct >= 75:
            return {"daily_bias": "BEARISH", "context": "SND_BEARISH_REVERSAL_ZONE", "allowed_direction": "SELL", "objective_ladder": ["FAIR_PRICE", "DISCOUNT_M1", "DISCOUNT_M2", "EXT_L_IF_MACRO_ALIGNED"], "close_lock_unlock_position": 45, "external_allowed": bool(macro_aligned)}
        if position_pct <= 25:
            return {"daily_bias": "BULLISH", "context": "SND_BULLISH_REVERSAL_ZONE", "allowed_direction": "BUY", "objective_ladder": ["FAIR_PRICE", "PREMIUM_M1", "PREMIUM_M2", "EXT_H_IF_MACRO_ALIGNED"], "close_lock_unlock_position": 55, "external_allowed": bool(macro_aligned)}
        return {"daily_bias": "WATCHING", "context": "SND_MID_RANGE_NO_REVERSAL_EDGE", "allowed_direction": "NONE", "objective_ladder": [], "close_lock_unlock_position": None, "external_allowed": False}

    if any(x in profile_u for x in ["SR", "S_R", "S&R", "SHALLOW_RETRACE"]):
        if any(x in event_u for x in ["MOMENTUM_BOS_UP", "SUPPLY_FLIP_DEMAND", "BULLISH_CONTINUATION"]):
            return {"daily_bias": "BULLISH", "context": "SR_BULLISH_CONTINUATION_SUPPLY_FLIP_DEMAND", "allowed_direction": "BUY", "objective_ladder": ["PREVIOUS_BREAK_HIGH", "EXT_H", "NEXT_HTF_OBJECTIVE"], "close_lock_unlock_position": 55, "external_allowed": True}
        if any(x in event_u for x in ["MOMENTUM_BOS_DOWN", "DEMAND_FLIP_SUPPLY", "BEARISH_CONTINUATION"]):
            return {"daily_bias": "BEARISH", "context": "SR_BEARISH_CONTINUATION_DEMAND_FLIP_SUPPLY", "allowed_direction": "SELL", "objective_ladder": ["PREVIOUS_BREAK_LOW", "EXT_L", "NEXT_HTF_OBJECTIVE"], "close_lock_unlock_position": 45, "external_allowed": True}

    return {"daily_bias": "WATCHING", "context": "NO_VALID_DAILY_CONTEXT", "allowed_direction": "NONE", "objective_ladder": [], "close_lock_unlock_position": None, "external_allowed": False}


def _inducement_interpretation_v130(direction: str, inducement_swing: str) -> dict[str, Any]:
    d = _normalise_enum_text_v130(direction, "WATCHING")
    s = _normalise_enum_text_v130(inducement_swing, "NOT_TAGGED")
    if "INDUCEMENT" not in s:
        return {"active": False, "message": "No inducement swing tagged."}
    if d in {"BULLISH", "BUY"}:
        return {"active": True, "direction": "BULLISH", "message": "Inducement swing: above Fair Price rejected to Discount. Wait for Discount hold before pro-trend continuation."}
    if d in {"BEARISH", "SELL"}:
        return {"active": True, "direction": "BEARISH", "message": "Inducement swing: below Fair Price rejected to Premium. Wait for Premium hold before pro-trend continuation."}
    return {"active": True, "direction": "UNKNOWN", "message": "Inducement swing tagged but directional context is still watching."}


def _intraday_flow_v130(snapshot: dict[str, Any], daily_bias: str) -> dict[str, Any]:
    phase = _normalise_enum_text_v130(snapshot.get("phase_state") or snapshot.get("intraday_state"), "PRE_CHOCH")
    profile = _normalise_enum_text_v130(snapshot.get("intraday_profile"), "WAITING")
    fav = _normalise_enum_text_v130(snapshot.get("favourable_trade"), "NO_FAVOURABLE_TRADE")
    retest = _normalise_enum_text_v130(snapshot.get("retest_status"), "WAITING")
    metrics = _choch_gateway_metrics_v130(snapshot)

    if phase in {"PRE_CHOCH", "WAITING"} or profile == "WAITING":
        execution_status = "WAITING"
        next_step = "Wait for Intraday CHOCH gateway and profile to form."
        fav = "NO_FAVOURABLE_TRADE"
    elif phase in {"CHOCH_CONFIRMED", "CHOCH_RANGE_MARKED", "IMMEDIATE_ENTRY_ACTIVE"}:
        execution_status = "READY" if phase == "IMMEDIATE_ENTRY_ACTIVE" else "FORMING"
        next_step = "Immediate continuation can be prepared only if risk/SL are clean; otherwise wait for P1/P2 sequence."
        fav = "IMMEDIATE_CONTINUATION" if phase == "IMMEDIATE_ENTRY_ACTIVE" else "P1_DEVELOPMENT"
    elif phase == "P1_BOS_CONFIRMED":
        execution_status = "WAITING"
        retest = "RETEST_PENDING"
        fav = "P2_CONTINUATION"
        next_step = "P1 BOS confirmed. Favourable trade is P2 continuation. Retest pending."
    elif phase in {"P2_ACTIVE", "P2_RETEST_ACTIVE", "INTERNAL_SWEEP_CLEANUP"}:
        execution_status = "FORMING"
        retest = "RETEST_ACTIVE"
        fav = "P2_CONTINUATION"
        next_step = "Retest / internal cleanup active. Wait for completion and Micro confirmation."
    elif phase in {"P2_RETEST_COMPLETE", "P2_BOS_CONFIRMED", "REF_CONFIRMATION_ACTIVE"}:
        execution_status = "READY"
        retest = "RETEST_COMPLETE"
        fav = "P2_CONTINUATION"
        next_step = "Retest complete. Confirm Micro/15m ref candle before execution."
    elif phase == "ADD_RISK_READY":
        execution_status = "READY"
        retest = "RETEST_COMPLETE"
        fav = "CONFIRMED_CONTINUATION_ADD_RISK"
        next_step = "Add-risk ready. Input fresh SL and keep total idea risk under 1%."
    elif phase in {"P3_FAILED", "NEW_P1_ACTIVE", "PROFILE_FLIP_ACTIVE"}:
        execution_status = "FORMING"
        retest = "PROFILE_SHIFT"
        fav = "P3_FAILURE_REVERSAL" if phase == "P3_FAILED" else "NEW_P1_PROFILE_FLIP_CONTINUATION"
        next_step = "Profile shift active. Wait for new confirmation; do not trade dead range logic."
    elif phase == "INVALIDATED":
        execution_status = "INVALIDATED"
        retest = "FAILED"
        fav = "NO_FAVOURABLE_TRADE"
        next_step = "Narrative invalidated. Stand down."
    else:
        execution_status = "WATCHING"
        next_step = "No complete intraday rule chain yet."

    return {"intraday_state": phase, "intraday_profile": profile, "favourable_trade": fav, "retest_status": retest, "execution_status": execution_status, "next_required_step": next_step, "choch_gateway": metrics, "daily_bias_context": daily_bias}


def _float_or_none_v129(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _normalise_text_v129(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _layer_from_map_v129(map_state: dict[str, Any] | None, timeframe: str) -> dict[str, Any]:
    if not isinstance(map_state, dict):
        return {}
    layers = map_state.get("layers") if isinstance(map_state.get("layers"), dict) else {}
    layer = layers.get(timeframe.lower()) if isinstance(layers.get(timeframe.lower()), dict) else {}
    visual = layer.get("visual") if isinstance(layer.get("visual"), dict) else {}
    meta = layer.get("meta") if isinstance(layer.get("meta"), dict) else {}
    anchors = layer.get("anchors") if isinstance(layer.get("anchors"), list) else []
    telemetry = layer.get("telemetry") if isinstance(layer.get("telemetry"), dict) else {}
    return {"visual": visual, "meta": meta, "anchors": anchors, "telemetry": telemetry}


def _anchor_v129(layer: dict[str, Any], key: str) -> dict[str, Any] | None:
    key = str(key or "").upper()
    for anchor in layer.get("anchors") or []:
        if str(anchor.get("anchor_key") or anchor.get("label") or "").upper() == key:
            return anchor
    # fallback to visual path if frontend has not normalized anchors yet
    visual = layer.get("visual") or {}
    for point in visual.get("path") or []:
        if str(point.get("anchorKey") or point.get("anchor_key") or point.get("label") or "").upper() == key:
            return point
    return None


def _price_from_anchor_v129(layer: dict[str, Any], key: str) -> float | None:
    a = _anchor_v129(layer, key)
    if not a:
        return None
    return _float_or_none_v129(a.get("price"))


def _range_position_v129(price: float | None, low: float | None, high: float | None) -> dict[str, Any]:
    if price is None or low is None or high is None or high <= low:
        return {"position_pct": None, "zone": "RANGE_INCOMPLETE", "label": "Range incomplete"}
    pct = ((price - low) / (high - low)) * 100.0
    if pct < 0:
        zone = "EXTERNAL_LOW_EXTENSION"
    elif pct <= 25:
        zone = "DISCOUNT"
    elif pct < 75:
        zone = "INTERNAL_RANGE"
    elif pct <= 100:
        zone = "PREMIUM"
    else:
        zone = "EXTERNAL_HIGH_EXTENSION"
    return {"position_pct": round(pct, 2), "zone": zone, "label": zone.replace("_", " ").title()}


def _interpret_daily_v129(position_pct: float | None, profile: str, structure_event: str, macro_aligned: bool = False) -> dict[str, Any]:
    profile = _normalise_text_v129(profile, "WAITING").upper()
    event = _normalise_text_v129(structure_event, "WAITING").upper()
    if position_pct is None:
        return {
            "daily_bias": "WATCHING",
            "context": "DAILY_RANGE_INCOMPLETE",
            "allowed_direction": "NONE",
            "objective_ladder": [],
            "close_lock_unlock_position": None,
        }

    # Supply and Demand profile: premium/external high = bearish reversal; discount/external low = bullish reversal.
    if "SND" in profile or "S&D" in profile:
        if position_pct >= 75:
            return {
                "daily_bias": "BEARISH",
                "context": "SND_BEARISH_REVERSAL_ZONE",
                "allowed_direction": "SELL",
                "objective_ladder": ["FAIR_PRICE", "DISCOUNT_M1", "DISCOUNT_M2", "EXT_L_IF_MACRO_ALIGNED"],
                "external_allowed": bool(macro_aligned),
                "close_lock_unlock_position": 45,
            }
        if position_pct <= 25:
            return {
                "daily_bias": "BULLISH",
                "context": "SND_BULLISH_REVERSAL_ZONE",
                "allowed_direction": "BUY",
                "objective_ladder": ["FAIR_PRICE", "PREMIUM_M1", "PREMIUM_M2", "EXT_H_IF_MACRO_ALIGNED"],
                "external_allowed": bool(macro_aligned),
                "close_lock_unlock_position": 55,
            }
        return {
            "daily_bias": "WATCHING",
            "context": "SND_MID_RANGE_NO_REVERSAL_EDGE",
            "allowed_direction": "NONE",
            "objective_ladder": [],
            "external_allowed": False,
            "close_lock_unlock_position": None,
        }

    # Support and Resistance profile: zone role flips after momentum BOS.
    if "SR" in profile or "S&R" in profile:
        if "BOS_UP" in event or "SUPPLY_FLIP_DEMAND" in event or "BULLISH_CONTINUATION" in event:
            return {
                "daily_bias": "BULLISH",
                "context": "SR_BULLISH_CONTINUATION_SUPPLY_FLIP_DEMAND",
                "allowed_direction": "BUY",
                "objective_ladder": ["PREVIOUS_BREAK_HIGH", "EXT_H", "NEXT_HTF_OBJECTIVE"],
                "external_allowed": True,
                "close_lock_unlock_position": 55,
            }
        if "BOS_DOWN" in event or "DEMAND_FLIP_SUPPLY" in event or "BEARISH_CONTINUATION" in event:
            return {
                "daily_bias": "BEARISH",
                "context": "SR_BEARISH_CONTINUATION_DEMAND_FLIP_SUPPLY",
                "allowed_direction": "SELL",
                "objective_ladder": ["PREVIOUS_BREAK_LOW", "EXT_L", "NEXT_HTF_OBJECTIVE"],
                "external_allowed": True,
                "close_lock_unlock_position": 45,
            }

    return {
        "daily_bias": "WATCHING",
        "context": "NO_VALID_DAILY_CONTEXT",
        "allowed_direction": "NONE",
        "objective_ladder": [],
        "external_allowed": False,
        "close_lock_unlock_position": None,
    }


def _pd_sweep_relevance_v129(position_pct: float | None, swept_level: str | None) -> dict[str, Any]:
    level = _normalise_text_v129(swept_level, "NONE").upper()
    if position_pct is None or level in {"", "NONE", "NOT_SET"}:
        return {"sweep_relevant": False, "sweep_context": "NO_SWEEP", "expected_bias": "WATCHING"}
    if level == "PDH" and position_pct >= 75:
        return {"sweep_relevant": True, "sweep_context": "PREMIUM_PDH_SWEEP", "expected_bias": "BEARISH"}
    if level == "PDL" and position_pct <= 25:
        return {"sweep_relevant": True, "sweep_context": "DISCOUNT_PDL_SWEEP", "expected_bias": "BULLISH"}
    return {"sweep_relevant": False, "sweep_context": "IRRELEVANT_MID_RANGE_SWEEP", "expected_bias": "WATCHING"}


def _intraday_flow_v129(layer: dict[str, Any], daily_bias: str) -> dict[str, Any]:
    meta = layer.get("meta") or {}
    profile = _normalise_text_v129(meta.get("profile"), "WAITING").upper()
    phase = _normalise_text_v129(meta.get("phase_state"), "PRE_CHOCH").upper()
    entry_model = _normalise_text_v129(meta.get("entry_model"), "WAITING").upper()

    if phase in {"PRE_CHOCH", "WAITING"} or profile == "WAITING":
        return {
            "intraday_state": "WAITING",
            "favourable_trade": "NO_FAVOURABLE_TRADE",
            "retest_status": "WAITING",
            "execution_status": "WAITING",
            "next_required_step": "Wait for Intraday CHOCH / structure to form.",
        }
    if phase in {"CHOCH_CONFIRMED", "IMMEDIATE_ENTRY_ACTIVE"}:
        return {
            "intraday_state": phase,
            "favourable_trade": "IMMEDIATE_CONTINUATION" if phase == "IMMEDIATE_ENTRY_ACTIVE" else "P1_DEVELOPMENT",
            "retest_status": "NOT_REQUIRED_YET",
            "execution_status": "FORMING" if phase == "CHOCH_CONFIRMED" else "READY",
            "next_required_step": "If immediate continuation is selected, confirm risk/SL. Otherwise wait for P1/P2 development.",
        }
    if phase == "P1_BOS_CONFIRMED":
        return {
            "intraday_state": phase,
            "favourable_trade": "P2_CONTINUATION",
            "retest_status": "RETEST_PENDING",
            "execution_status": "WAITING",
            "next_required_step": "Wait for P2 retest. No execution yet, stop being a button goblin.",
        }
    if phase in {"P2_ACTIVE", "P2_RETEST_ACTIVE"}:
        return {
            "intraday_state": phase,
            "favourable_trade": "P2_CONTINUATION",
            "retest_status": "RETEST_ACTIVE",
            "execution_status": "FORMING",
            "next_required_step": "Wait for retest completion and Micro confirmation.",
        }
    if phase in {"P2_BOS_CONFIRMED", "P2_RETEST_COMPLETE", "REF_CONFIRMATION_ACTIVE", "ADD_RISK_READY"}:
        return {
            "intraday_state": phase,
            "favourable_trade": "P2_CONTINUATION" if phase != "ADD_RISK_READY" else "CONFIRMED_CONTINUATION_ADD_RISK",
            "retest_status": "RETEST_COMPLETE",
            "execution_status": "READY",
            "next_required_step": "Execution can be prepared if Daily direction and Micro confirmation agree.",
        }
    if phase in {"P3_FAILED", "NEW_P1_ACTIVE"}:
        return {
            "intraday_state": phase,
            "favourable_trade": "P3_FAILURE_REVERSAL" if phase == "P3_FAILED" else "NEW_P1_PROFILE_FLIP",
            "retest_status": "PROFILE_SHIFT",
            "execution_status": "FORMING",
            "next_required_step": "Wait for profile flip confirmation. Do not treat old range logic as alive.",
        }
    if phase == "INVALIDATED":
        return {
            "intraday_state": "INVALIDATED",
            "favourable_trade": "NO_FAVOURABLE_TRADE",
            "retest_status": "FAILED",
            "execution_status": "INVALIDATED",
            "next_required_step": "Narrative dead. Stand down.",
        }
    return {
        "intraday_state": phase,
        "favourable_trade": "WATCHING",
        "retest_status": "WATCHING",
        "execution_status": "WATCHING",
        "next_required_step": "No complete intraday rule chain yet.",
    }


def _build_lifecycle_brain_v129(symbol: str, live_price: float | None = None) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    map_state = _load_symbol_map(symbol) or _normalise_map_payload({"symbol": symbol})
    weekly_layer = _layer_from_map_v129(map_state, "weekly")
    daily_layer = _layer_from_map_v129(map_state, "daily")
    intraday_layer = _layer_from_map_v129(map_state, "intraday")

    if live_price is None:
        live_price = _get_current_price_for_symbol(symbol)

    # Macro memory can be supplied in raw payload or state fields. Keep it permissive.
    raw = map_state.get("raw_payload") if isinstance(map_state.get("raw_payload"), dict) else {}
    macro = raw.get("macro") if isinstance(raw.get("macro"), dict) else raw.get("macro_state", {}) if isinstance(raw.get("macro_state"), dict) else {}
    macro_state = {
        "macro_state": macro.get("macro_state") or macro.get("range_state") or "MACRO_CONTEXT_MANUAL",
        "macro_low": macro.get("macro_low"),
        "macro_high": macro.get("macro_high"),
        "abandoned_macro_low": macro.get("abandoned_macro_low"),
        "new_macro_swing_high": macro.get("new_macro_swing_high"),
        "macro_bias_context": macro.get("macro_bias_context") or "WATCHING",
    }

    weekly_meta = weekly_layer.get("meta") or {}
    weekly_snapshot = {
        "weekly_state": weekly_meta.get("phase_state") or weekly_meta.get("continuation_state") or "WEEKLY_CONTEXT_ACTIVE",
        "weekly_profile": weekly_meta.get("profile") or "WAITING",
        "weekly_bias": weekly_meta.get("bias") or weekly_layer.get("visual", {}).get("mapBias") or "WATCHING",
        "objective_1": weekly_meta.get("objective_1") or weekly_meta.get("objective1"),
        "objective_2": weekly_meta.get("objective_2") or weekly_meta.get("objective2"),
        "inducement_swing": weekly_meta.get("inducement_swing") or "NOT_TAGGED",
    }

    daily_visual = daily_layer.get("visual") or {}
    daily_meta = daily_layer.get("meta") or {}
    daily_low = _float_or_none_v129(daily_visual.get("rangeLow") or daily_meta.get("range_low") or daily_meta.get("rangeLow"))
    daily_high = _float_or_none_v129(daily_visual.get("rangeHigh") or daily_meta.get("range_high") or daily_meta.get("rangeHigh"))
    daily_pos = _range_position_v129(live_price, daily_low, daily_high)
    daily_profile = daily_meta.get("profile") or "WAITING"
    structure_event = daily_meta.get("structure_event") or daily_meta.get("continuationState") or daily_meta.get("continuation_state") or daily_meta.get("phaseState") or daily_meta.get("phase_state") or "WAITING"
    macro_aligned = str(weekly_snapshot.get("weekly_bias", "")).upper() in {"BULLISH", "BEARISH", "BUY", "SELL"}
    daily_interpretation = _interpret_daily_v129(daily_pos.get("position_pct"), daily_profile, structure_event, macro_aligned=macro_aligned)
    pd_sweep = _pd_sweep_relevance_v129(daily_pos.get("position_pct"), daily_meta.get("pd_sweep") or daily_meta.get("previous_day_sweep"))
    daily_snapshot = {
        **daily_pos,
        **daily_interpretation,
        "daily_profile": daily_profile,
        "structure_event": structure_event,
        "pd_sweep": pd_sweep,
        "range_low": daily_low,
        "range_high": daily_high,
        "live_price": live_price,
    }

    intraday_snapshot = _intraday_flow_v129(intraday_layer, daily_interpretation.get("daily_bias", "WATCHING"))
    micro_state = raw.get("micro") if isinstance(raw.get("micro"), dict) else {}
    micro_confirmation = micro_state.get("confirmation") or micro_state.get("status") or "WAITING"

    participation_status = "WATCHING"
    execution_allowed = False
    suggested_direction = daily_interpretation.get("allowed_direction") or "NONE"
    reason = "No complete rule chain yet."
    next_step = intraday_snapshot.get("next_required_step")

    if daily_interpretation.get("daily_bias") == "WATCHING":
        participation_status = "NO_TRADE"
        reason = daily_interpretation.get("context") or "No active Daily bias."
        next_step = "Wait for Daily location/profile to produce a valid bias."
    elif intraday_snapshot.get("execution_status") in {"WAITING", "FORMING", "WATCHING"}:
        participation_status = "FORMING"
        reason = f"Daily {daily_interpretation.get('daily_bias')} is active, but Intraday is not ready."
    elif intraday_snapshot.get("execution_status") == "READY":
        if str(micro_confirmation).upper() in {"CONFIRMED", "READY", "REF_CANDLE_CONFIRMED", "MICRO_ENTRY_APPROVED"}:
            participation_status = "EXECUTE_ALLOWED"
            execution_allowed = True
            reason = "Daily bias active, Intraday ready, Micro confirmation valid."
        else:
            participation_status = "READY"
            reason = "Daily and Intraday are ready. Micro confirmation still required."
            next_step = "Wait for 15m confirmation / ref candle."
    elif intraday_snapshot.get("execution_status") == "INVALIDATED":
        participation_status = "INVALIDATED"
        reason = "Intraday narrative invalidated."
        next_step = "Stand down or rebuild the map."

    machine_message = f"Daily: {daily_interpretation.get('daily_bias')} / {daily_interpretation.get('context')}. Intraday: {intraday_snapshot.get('intraday_state')} → {intraday_snapshot.get('favourable_trade')}. Retest: {intraday_snapshot.get('retest_status')}. Status: {participation_status}."

    return {
        "ok": True,
        "symbol": symbol,
        "updated_at": _now_sast_iso(),
        "macro": macro_state,
        "weekly": weekly_snapshot,
        "daily": daily_snapshot,
        "intraday": intraday_snapshot,
        "micro": {"confirmation": micro_confirmation},
        "participation": {
            "participation_status": participation_status,
            "execution_allowed": execution_allowed,
            "suggested_direction": suggested_direction,
            "reason": reason,
            "next_required_step": next_step,
            "machine_message": machine_message,
            "risk_permission": "0.50% initial / add-risk only within 1% cap" if execution_allowed or participation_status in {"READY", "FORMING"} else "NO_RISK",
        },
    }



def _build_lifecycle_brain_v130(symbol: str, live_price: float | None = None) -> dict[str, Any]:
    symbol = _normalise_symbol(symbol)
    map_state = _load_symbol_map(symbol) or _normalise_map_payload({"symbol": symbol})
    snapshot = _load_lifecycle_snapshot(symbol)
    weekly_layer = _layer_from_map_v129(map_state, "weekly")
    daily_layer = _layer_from_map_v129(map_state, "daily")
    intraday_layer = _layer_from_map_v129(map_state, "intraday")

    if live_price is None:
        live_price = _get_current_price_for_symbol(symbol)

    macro_snap = snapshot.get("macro") or {}
    weekly_snap = snapshot.get("weekly") or {}
    daily_snap_manual = snapshot.get("daily") or {}
    intraday_snap_manual = snapshot.get("intraday") or {}
    micro_snap = snapshot.get("micro") or {}

    macro_state = {
        **macro_snap,
        "macro_state": macro_snap.get("macro_state") or "MACRO_CONTEXT_MANUAL",
        "macro_bias_context": macro_snap.get("macro_bias_context") or "WATCHING",
    }

    weekly_meta = weekly_layer.get("meta") or {}
    weekly_visual = weekly_layer.get("visual") or {}
    weekly_bias = _prefer_real_value_v132(weekly_snap.get("weekly_bias"), weekly_meta.get("bias") or weekly_visual.get("mapBias"), "WATCHING")
    weekly_snapshot = {
        "weekly_state": _prefer_real_value_v132(weekly_snap.get("weekly_state"), _map_meta_alias_v132(weekly_meta, "phase_state", "phaseState", "continuation_state", "continuationState"), "WEEKLY_CONTEXT_ACTIVE"),
        "weekly_profile": _prefer_real_value_v132(weekly_snap.get("weekly_profile"), weekly_meta.get("profile"), "WAITING"),
        "weekly_bias": str(weekly_bias).upper(),
        "inducement_swing": _prefer_real_value_v132(weekly_snap.get("inducement_swing"), weekly_meta.get("inducement_swing"), "NOT_TAGGED"),
        "objective_1": _prefer_real_value_v132(weekly_snap.get("objective_1"), _map_meta_alias_v132(weekly_meta, "objective_1", "objective1"), "FAIR_PRICE"),
        "objective_2": _prefer_real_value_v132(weekly_snap.get("objective_2"), _map_meta_alias_v132(weekly_meta, "objective_2", "objective2"), "PENDING"),
        "objective_3": _prefer_real_value_v132(weekly_snap.get("objective_3"), _map_meta_alias_v132(weekly_meta, "objective_3", "objective3"), "EXT_IF_MACRO_ALIGNED"),
    }
    weekly_snapshot["inducement"] = _inducement_interpretation_v130(weekly_snapshot.get("weekly_bias"), weekly_snapshot.get("inducement_swing"))

    daily_meta = daily_layer.get("meta") or {}
    daily_low_map, daily_high_map = _range_from_layer_v132(daily_layer)
    daily_low = _float_or_none_v129(_prefer_real_value_v132(daily_snap_manual.get("range_low"), daily_low_map, daily_low_map))
    daily_high = _float_or_none_v129(_prefer_real_value_v132(daily_snap_manual.get("range_high"), daily_high_map, daily_high_map))
    daily_pos = _range_position_v129(live_price, daily_low, daily_high)
    daily_profile = _prefer_real_value_v132(daily_snap_manual.get("daily_profile"), daily_meta.get("profile"), "WAITING")
    structure_event = _prefer_real_value_v132(
        daily_snap_manual.get("structure_event") or daily_snap_manual.get("daily_phase"),
        _map_meta_alias_v132(daily_meta, "structure_event", "continuationState", "continuation_state", "phaseState", "phase_state"),
        "WAITING",
    )
    macro_aligned = str(weekly_snapshot.get("weekly_bias", "")).upper() in {"BULLISH", "BEARISH", "BUY", "SELL"}
    daily_interpretation = _interpret_daily_v130(daily_pos.get("position_pct"), daily_profile, structure_event, macro_aligned=macro_aligned)
    pd_sweep = _pd_sweep_relevance_v129(daily_pos.get("position_pct"), _prefer_real_value_v132(daily_snap_manual.get("previous_day_sweep"), daily_meta.get("pd_sweep") or daily_meta.get("previous_day_sweep"), "NONE"))
    inducement_tag = _prefer_real_value_v132(daily_snap_manual.get("inducement_swing"), daily_meta.get("inducement_swing"), "NOT_TAGGED")
    daily_snapshot = {
        **daily_pos,
        **daily_interpretation,
        "daily_state": _prefer_real_value_v132(daily_snap_manual.get("daily_state"), _map_meta_alias_v132(daily_meta, "daily_state", "state"), "DAILY_PRE_CHOCH"),
        "daily_phase": _prefer_real_value_v132(daily_snap_manual.get("daily_phase"), _map_meta_alias_v132(daily_meta, "phase_state", "phaseState"), "PRE_CHOCH"),
        "daily_profile": daily_profile,
        "structure_event": structure_event,
        "profile_transition": _prefer_real_value_v132(daily_snap_manual.get("profile_transition"), daily_meta.get("profile_transition"), "NO_PROFILE_FLIP"),
        "inducement_swing": inducement_tag,
        "inducement": _inducement_interpretation_v130(daily_interpretation.get("daily_bias"), inducement_tag),
        "pd_sweep": pd_sweep,
        "range_low": daily_low,
        "range_high": daily_high,
        "live_price": live_price,
        "source": {"range": "map" if daily_low_map is not None and daily_high_map is not None else "snapshot_or_missing", "profile": "map_fallback_enabled"},
    }

    # Manual snapshot wins only if it is not still sitting on backend defaults.
    intraday_merged = dict(intraday_snap_manual)
    meta = intraday_layer.get("meta") or {}
    intraday_merged["phase_state"] = _prefer_real_value_v132(intraday_snap_manual.get("phase_state") or intraday_snap_manual.get("intraday_state"), _map_meta_alias_v132(meta, "phase_state", "phaseState"), "PRE_CHOCH")
    intraday_merged["intraday_profile"] = _prefer_real_value_v132(intraday_snap_manual.get("intraday_profile"), meta.get("profile"), "WAITING")
    intraday_merged["entry_model"] = _prefer_real_value_v132(intraday_snap_manual.get("entry_model"), _map_meta_alias_v132(meta, "entry_model", "entryModel"), "WAITING")
    intraday_merged["favourable_trade"] = _prefer_real_value_v132(intraday_snap_manual.get("favourable_trade"), meta.get("favourable_trade"), "NO_FAVOURABLE_TRADE")
    intraday_merged["retest_status"] = _prefer_real_value_v132(intraday_snap_manual.get("retest_status"), meta.get("retest_status"), "WAITING")
    if not intraday_merged.get("liquidity_cleanup_price"):
        intraday_merged["liquidity_cleanup_price"] = (intraday_layer.get("visual") or {}).get("liquidityCleanUpPrice") or meta.get("liquidity_cleanup_price")
    intraday_snapshot = _intraday_flow_v130(intraday_merged, daily_interpretation.get("daily_bias", "WATCHING"))
    micro_confirmation = _prefer_real_value_v132(micro_snap.get("confirmation"), (intraday_layer.get("meta") or {}).get("micro_confirmation"), "WAITING")

    participation_status = "WATCHING"
    execution_allowed = False
    suggested_direction = daily_interpretation.get("allowed_direction") or "NONE"
    reason = "No complete rule chain yet."
    next_step = intraday_snapshot.get("next_required_step")

    if daily_interpretation.get("daily_bias") == "WATCHING":
        participation_status = "NO_TRADE"
        reason = daily_interpretation.get("context") or "No active Daily bias."
        next_step = "Catch up Daily range/profile first."
    elif intraday_snapshot.get("execution_status") in {"WAITING", "FORMING", "WATCHING"}:
        participation_status = "FORMING"
        reason = f"Daily {daily_interpretation.get('daily_bias')} is active, but Intraday has not completed the next required state."
    elif intraday_snapshot.get("execution_status") == "READY":
        if str(micro_confirmation).upper() in {"CONFIRMED", "READY", "REF_CANDLE_CONFIRMED", "MICRO_ENTRY_APPROVED"}:
            participation_status = "EXECUTE_ALLOWED" if intraday_snapshot.get("favourable_trade") != "CONFIRMED_CONTINUATION_ADD_RISK" else "ADD_RISK_READY"
            execution_allowed = True
            reason = "Daily bias active, Intraday ready, Micro confirmation valid."
        else:
            participation_status = "READY"
            reason = "Daily and Intraday are ready. Micro/15m confirmation still required."
            next_step = "Wait for 15m confirmation / ref candle."
    elif intraday_snapshot.get("execution_status") == "INVALIDATED":
        participation_status = "INVALIDATED"
        reason = "Intraday narrative invalidated."
        next_step = "Stand down or rebuild the lifecycle snapshot."

    daily_obj = (daily_snapshot.get("objective_ladder") or ["UNKNOWN"])[0]
    machine_message = (
        f"Weekly: {weekly_snapshot.get('weekly_bias')} / {weekly_snapshot.get('weekly_state')}. "
        f"Daily: {daily_snapshot.get('daily_bias')} toward {daily_obj} ({daily_snapshot.get('context')}). "
        f"Intraday: {intraday_snapshot.get('intraday_state')} → {intraday_snapshot.get('favourable_trade')}. "
        f"Retest: {intraday_snapshot.get('retest_status')}. Status: {participation_status}."
    )

    return {
        "ok": True,
        "symbol": symbol,
        "engine_version": "v136_finalized_journal_mitigation_memory",
        "updated_at": _now_sast_iso(),
        "snapshot": snapshot,
        "macro": macro_state,
        "weekly": weekly_snapshot,
        "daily": daily_snapshot,
        "intraday": intraday_snapshot,
        "micro": {"confirmation": micro_confirmation, **micro_snap},
        "participation": {
            "participation_status": participation_status,
            "execution_allowed": execution_allowed,
            "suggested_direction": suggested_direction,
            "reason": reason,
            "next_required_step": next_step,
            "machine_message": machine_message,
            "risk_permission": "0.50% initial / add-risk only within 1% cap" if execution_allowed or participation_status in {"READY", "FORMING", "ADD_RISK_READY"} else "NO_RISK",
        },
    }

@app.get("/api/v1/lifecycle/brain")
def lifecycle_brain(symbol: str = "XAUUSD", live_price: float | None = None):
    return _build_lifecycle_brain_v130(symbol=symbol, live_price=live_price)


@app.get("/participation/snapshot")
def participation_snapshot(symbol: str = "XAUUSD", live_price: float | None = None):
    return _build_lifecycle_brain_v130(symbol=symbol, live_price=live_price)


@app.get("/api/v1/trade-ideas")
def list_quick_trade_ideas(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    store = _load_quick_trade_ideas_store()
    rows = [r for r in store.get(symbol, []) if isinstance(r, dict)]
    return {"ok": True, "symbol": symbol, "ideas": rows}


@app.post("/api/v1/trade-ideas/quick")
def create_quick_trade_idea(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    brain = _build_lifecycle_brain_v130(symbol=symbol, live_price=_float_or_none_v129(payload.get("live_price")))
    direction = _normalise_text_v129(payload.get("direction") or brain.get("participation", {}).get("suggested_direction"), "NONE").upper()
    risk_pct = _float_or_none_v129(payload.get("risk_percent"))
    if risk_pct is None:
        risk_pct = 0.5 if payload.get("setup_type", "").upper() != "A+ REVERSAL" else 1.0
    idea = {
        "id": payload.get("id") or f"idea_{int(datetime.now(SAST).timestamp() * 1000)}",
        "symbol": symbol,
        "direction": direction,
        "setup_type": payload.get("setup_type") or payload.get("setupType") or "Quick Trade Idea",
        "lifecycle_state": payload.get("lifecycle_state") or payload.get("status") or brain.get("participation", {}).get("participation_status") or "WATCHING",
        "add_risk_state": payload.get("add_risk_state") or "WAITING",
        "risk_percent": float(risk_pct),
        "max_trade_risk_percent": 1.0,
        "sl_price": payload.get("sl_price") or payload.get("invalidationPrice") or "",
        "add_risk_sl": payload.get("add_risk_sl") or "",
        "objective": payload.get("objective") or (brain.get("daily", {}).get("objective_ladder") or [""])[0],
        "waiting_for": payload.get("waiting_for") or brain.get("participation", {}).get("next_required_step"),
        "machine_message": brain.get("participation", {}).get("machine_message"),
        "brain_snapshot": brain,
        "created_at": _now_sast_iso(),
        "updated_at": _now_sast_iso(),
        "source": payload.get("source") or "quick_trade_idea",
        "notes": payload.get("notes") or "",
    }
    store = _load_quick_trade_ideas_store()
    rows = [r for r in store.get(symbol, []) if isinstance(r, dict) and r.get("id") != idea["id"]]
    store[symbol] = [idea] + rows[:49]
    _save_quick_trade_ideas_store(store)
    # Attach latest map/snapshot versions before writing to SQL, so each idea
    # knows the exact surveillance state it was born from. Future ML says thanks,
    # present software merely grunts.
    try:
        current_map = _load_symbol_map(symbol) or {}
        idea["map_state_version"] = current_map.get("state_version")
        idea["map_snapshot"] = current_map
        current_snapshot = _load_lifecycle_snapshot(symbol) or {}
        idea["lifecycle_snapshot_version"] = current_snapshot.get("snapshot_version")
    except Exception:
        pass
    structured = None
    memory = None
    try:
        if sql_save_trade_idea_structured is not None:
            structured = sql_save_trade_idea_structured(idea)
    except Exception as exc:
        structured = {"ok": False, "error": str(exc)}
    try:
        if sql_save_trade_memory_record is not None:
            memory = sql_save_trade_memory_record(idea)
    except Exception as exc:
        memory = {"ok": False, "error": str(exc)}
    return {"ok": True, "symbol": symbol, "idea": idea, "structured_journal": structured, "trade_memory": memory}


@app.post("/api/v1/trade-ideas/update")
def update_quick_trade_idea(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    idea_id = str(payload.get("id") or payload.get("idea_id") or "").strip()
    if not idea_id:
        return {"ok": False, "error": "id/idea_id is required"}
    store = _load_quick_trade_ideas_store()
    rows = [r for r in store.get(symbol, []) if isinstance(r, dict)]
    found = False
    for row in rows:
        if str(row.get("id")) == idea_id:
            for key in ("direction", "setup_type", "lifecycle_state", "add_risk_state", "risk_percent", "sl_price", "add_risk_sl", "objective", "waiting_for", "notes"):
                if key in payload:
                    row[key] = payload.get(key)
            row["updated_at"] = _now_sast_iso()
            found = True
            break
    if not found:
        return {"ok": False, "error": "idea not found"}
    store[symbol] = rows
    _save_quick_trade_ideas_store(store)
    return {"ok": True, "symbol": symbol, "ideas": rows}


@app.post("/api/v1/quick-trade/preview")
def quick_trade_preview(payload: dict = Body(...)):
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    live_price = _float_or_none_v129(payload.get("live_price") or payload.get("current_price"))
    if live_price is None:
        live_price = _get_current_price_for_symbol(symbol)
    sl_preview = None
    if payload.get("sl_digits") or payload.get("digits"):
        try:
            sl_preview = _resolve_sl_from_digits(direction=str(payload.get("direction") or "BUY"), live_price=float(live_price), digits=str(payload.get("sl_digits") or payload.get("digits")))
        except Exception as exc:
            sl_preview = {"ok": False, "error": str(exc)}
    brain = _build_lifecycle_brain_v130(symbol=symbol, live_price=live_price)
    return {
        "ok": True,
        "symbol": symbol,
        "live_price": live_price,
        "sl_preview": sl_preview,
        "participation": brain.get("participation"),
        "daily": brain.get("daily"),
        "intraday": brain.get("intraday"),
        "recommended_payload": {
            "symbol": symbol,
            "direction": payload.get("direction") or brain.get("participation", {}).get("suggested_direction"),
            "execution_mode": payload.get("execution_mode") or "NEW_TRADE",
            "risk_percent": payload.get("risk_percent") or 0.5,
            "sl_price": (sl_preview or {}).get("resolved_sl") if isinstance(sl_preview, dict) else payload.get("sl_price"),
            "entry_model": payload.get("entry_model") or "IMMEDIATE_CONTINUATION_ENTRY",
        }
    }




def _scenario_result_from_payload_v133(payload: dict[str, Any]) -> dict[str, Any]:
    """Rule-chain sandbox for manually testing lifecycle scenarios.

    This does not place trades. It lets Josh test whether the machine hints in the
    correct path before ML-lite gets invited to the party and starts acting clever.
    """
    symbol = _normalise_symbol(str(payload.get("symbol") or "XAUUSD"))
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else payload
    intraday = payload.get("intraday") if isinstance(payload.get("intraday"), dict) else payload
    micro = payload.get("micro") if isinstance(payload.get("micro"), dict) else payload
    weekly = payload.get("weekly") if isinstance(payload.get("weekly"), dict) else {}
    daily_bias = str(daily.get("daily_bias") or daily.get("bias") or "WATCHING").upper()
    daily_profile = str(daily.get("daily_profile") or daily.get("profile") or "WAITING").upper()
    daily_objective = str(daily.get("daily_objective") or daily.get("objective") or daily.get("objective_1") or "UNKNOWN")
    bos_direction = str(daily.get("bos_direction") or daily.get("BOS_DIRECTION") or payload.get("bos_direction") or "WAITING").upper()
    phase_type = str(daily.get("phase_type") or payload.get("phase_type") or "WAITING").upper()
    reclaim_status = str(daily.get("reclaim_status") or payload.get("reclaim_status") or "WAITING").upper()
    range_status = str(daily.get("range_status") or payload.get("range_status") or "ACTIVE").upper()
    order_flow = str(daily.get("order_flow") or payload.get("order_flow") or "WAITING").upper()
    inducement = payload.get("inducement") if payload.get("inducement") is not None else daily.get("inducement")
    inducement_active = str(inducement).lower() in {"true", "1", "yes", "y", "held", "active"}
    mitigation_sequence = payload.get("mitigation_sequence") or payload.get("mitigationSequence") or []
    if not isinstance(mitigation_sequence, list):
        mitigation_sequence = [x.strip() for x in str(mitigation_sequence).split(',') if x.strip()]
    phase = str(intraday.get("intraday_state") or intraday.get("phase_state") or "WAITING").upper()
    favourable = str(intraday.get("favourable_trade") or "NO_FAVOURABLE_TRADE").upper()
    retest = str(intraday.get("retest_status") or "WAITING").upper()
    micro_conf = str(micro.get("confirmation") or micro.get("micro_confirmation") or "WAITING").upper()
    status = "WATCHING"
    execution_allowed = False
    next_step = "Catch up Daily range/profile first."
    reason = "No active Daily bias."
    if daily_bias in {"BULLISH", "BEARISH", "BUY", "SELL"}:
        reason = f"Daily {daily_bias} active toward {daily_objective}."
        if "INVALID" in phase or "FAILED" in retest:
            status = "INVALIDATED"; next_step = "Stand down or rebuild scenario."
        elif "ADD_RISK" in phase or favourable == "CONFIRMED_CONTINUATION_ADD_RISK":
            status = "ADD_RISK_READY" if micro_conf in {"CONFIRMED", "READY", "REF_CANDLE_CONFIRMED"} else "READY"
            execution_allowed = status == "ADD_RISK_READY"
            next_step = "Execute add-risk with new SL." if execution_allowed else "Wait for 15m ref candle confirmation."
        elif retest in {"RETEST_COMPLETE", "COMPLETE", "DONE"} and micro_conf in {"CONFIRMED", "READY", "REF_CANDLE_CONFIRMED", "MICRO_ENTRY_APPROVED"}:
            status = "EXECUTE_ALLOWED"; execution_allowed = True; next_step = "Execute allowed if risk cap permits."
        elif retest in {"RETEST_ACTIVE", "ACTIVE"}:
            status = "FORMING"; next_step = "Wait for retest completion and micro confirmation."
        elif retest in {"RETEST_PENDING", "PENDING", "WAITING"}:
            status = "FORMING"; next_step = "Wait for retest. Do not force it."
        elif "P1_BOS" in phase:
            status = "FORMING"; favourable = favourable if favourable != "NO_FAVOURABLE_TRADE" else "P2_CONTINUATION"; next_step = "Favourable trade: P2 continuation. Retest pending."
        elif "P2_RETEST_COMPLETE" in phase:
            status = "READY"; next_step = "Micro/15m confirmation required."
        else:
            status = "WATCHING"; next_step = "Structure not complete."
    if daily_profile == "SND_DEEP_RETRACE" and daily_bias in {"BULLISH", "BEARISH"}:
        logic_line = f"S&D {daily_bias.lower()} context: {bos_direction} / {reclaim_status}."
    elif "SR" in daily_profile:
        logic_line = f"S&R continuation check: {bos_direction} • {order_flow}."
    else:
        logic_line = f"Profile waiting: {daily_profile}."
    if inducement_active:
        logic_line += " Inducement swing tagged; wait for reaction zone hold/fail."
    if mitigation_sequence:
        logic_line += f" Mitigation path logged: {' → '.join(map(str, mitigation_sequence[:5]))}."
    message = f"Daily {daily_bias} / {daily_profile} toward {daily_objective}. {logic_line} Intraday {phase} → {favourable}. Retest: {retest}. Status: {status}."
    return {
        "ok": True,
        "symbol": symbol,
        "engine_version": "v136_lifecycle_scenario_mitigation_calculator",
        "weekly": weekly,
        "daily": {"daily_bias": daily_bias, "daily_profile": daily_profile, "daily_objective": daily_objective, "bos_direction": bos_direction, "phase_type": phase_type, "reclaim_status": reclaim_status, "range_status": range_status, "order_flow": order_flow, "inducement_active": inducement_active, "mitigation_sequence": mitigation_sequence},
        "intraday": {"intraday_state": phase, "favourable_trade": favourable, "retest_status": retest},
        "micro": {"confirmation": micro_conf},
        "participation": {"participation_status": status, "execution_allowed": execution_allowed, "next_required_step": next_step, "reason": reason, "machine_message": message},
        "input": payload,
    }


@app.post("/api/v1/lifecycle/scenario/calculate")
def lifecycle_scenario_calculate(payload: dict = Body(...)):
    result = _scenario_result_from_payload_v133(payload)
    stored = None
    try:
        if sql_save_lifecycle_scenario_test is not None:
            stored = sql_save_lifecycle_scenario_test(payload, result)
    except Exception as exc:
        stored = {"ok": False, "error": str(exc)}
    return {**result, "stored": stored}


@app.post("/api/v1/lifecycle/scenario/backtest")
def lifecycle_scenario_backtest(payload: dict = Body(...)):
    rows = payload.get("scenarios") if isinstance(payload.get("scenarios"), list) else [payload]
    results = []
    for row in rows:
        if isinstance(row, dict):
            results.append(lifecycle_scenario_calculate(row))
    passed = sum(1 for r in results if (r.get("stored") or {}).get("scenario", {}).get("pass_flag") == 1)
    return {"ok": True, "count": len(results), "passed": passed, "results": results}



# =============================
# V135 DATE-AWARE HISTORICAL LIFECYCLE LINKER
# =============================

@app.post("/api/v1/historical/lifecycle-bundle")
def historical_lifecycle_bundle_save(payload: dict = Body(...)):
    if sql_save_historical_lifecycle_bundle is None:
        return {"ok": False, "error": "historical lifecycle bundle storage unavailable"}
    try:
        return sql_save_historical_lifecycle_bundle(payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/v1/historical/lifecycle-bundles")
def historical_lifecycle_bundle_list(symbol: str | None = None, limit: int = 100):
    if sql_historical_lifecycle_bundles is None:
        return {"ok": False, "error": "historical lifecycle bundles unavailable"}
    return sql_historical_lifecycle_bundles(symbol=symbol, limit=limit)


@app.get("/api/v1/historical/resolve-context")
def historical_resolve_context(symbol: str = "XAUUSD", sample_date: str = ""):
    if sql_resolve_context_by_date is None:
        return {"ok": False, "error": "date-aware context resolver unavailable"}
    return sql_resolve_context_by_date(symbol=symbol, sample_date=sample_date)


@app.post("/api/v1/historical/resolve-context")
def historical_resolve_context_post(payload: dict = Body(...)):
    return historical_resolve_context(symbol=str(payload.get("symbol") or "XAUUSD"), sample_date=str(payload.get("sample_date") or payload.get("date") or ""))

@app.get("/api/v1/journal/trades/detailed")
def journal_detailed_trades(symbol: str | None = None, limit: int = 50):
    if sql_detailed_trade_rows is None:
        return {"ok": False, "error": "detailed journal unavailable"}
    return sql_detailed_trade_rows(limit=limit, symbol=symbol)


@app.get("/api/v1/journal/trade/detail")
def journal_trade_detail(id: str, symbol: str | None = None):
    if sql_trade_detail is None:
        return {"ok": False, "error": "trade detail unavailable"}
    return sql_trade_detail(id, symbol=symbol)


@app.post("/api/v1/journal/trade/update")
def journal_trade_update(payload: dict = Body(...)):
    if sql_update_trade_memory_record is None:
        return {"ok": False, "error": "trade memory update unavailable"}
    ident = str(payload.get("id") or payload.get("trade_id") or payload.get("trade_idea_external_id") or "").strip()
    if not ident:
        return {"ok": False, "error": "id/trade_id/trade_idea_external_id is required"}
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
    return sql_update_trade_memory_record(ident, fields, symbol=payload.get("symbol"))


@app.get("/journal/trades/detailed")
def journal_detailed_trades_alias(symbol: str | None = None, limit: int = 50):
    return journal_detailed_trades(symbol=symbol, limit=limit)

@app.get("/api/v1/journal/report/summary")
def journal_report_summary_endpoint(symbol: str | None = None):
    if sql_journal_report_summary is None:
        return {"ok": False, "error": "structured journal reporting unavailable"}
    return sql_journal_report_summary(symbol=symbol)


@app.get("/api/v1/journal/report/recent")
def journal_report_recent_endpoint(limit: int = 50, symbol: str | None = None):
    if sql_recent_structured_journal is None:
        return {"ok": False, "error": "structured journal reporting unavailable"}
    return sql_recent_structured_journal(limit=limit, symbol=symbol)


@app.get("/journal/report/summary")
def journal_report_summary_alias(symbol: str | None = None):
    return journal_report_summary_endpoint(symbol=symbol)


@app.get("/journal/report/recent")
def journal_report_recent_alias(limit: int = 50, symbol: str | None = None):
    return journal_report_recent_endpoint(limit=limit, symbol=symbol)


def _range_alerts_for_symbol(symbol: str) -> list[dict[str, Any]]:
    state = get_state(symbol)
    mobile = state.get("mobile_structure", {}) or {}
    price = mobile.get("current_price")
    if price in (None, ""):
        try:
            p = _price_payload(symbol)
            price = p.get("mid") or p.get("price") or p.get("bid")
        except Exception:
            price = None
    try:
        price_f = float(price)
    except Exception:
        return []

    alerts = []
    for layer in ["macro", "weekly", "daily"]:
        high = mobile.get(f"{layer}_high")
        low = mobile.get(f"{layer}_low")
        try:
            high_f = float(high)
            low_f = float(low)
        except Exception:
            continue
        if high_f == low_f:
            continue
        lo, hi = min(low_f, high_f), max(low_f, high_f)
        rng = hi - lo
        pct = ((price_f - lo) / rng) * 100.0
        if price_f >= hi:
            alerts.append({"level": "danger", "type": "EXTERNAL_BREACH_UP", "layer": layer, "message": f"{layer.title()} external high breached", "price": price_f, "level_price": hi})
        elif price_f <= lo:
            alerts.append({"level": "danger", "type": "EXTERNAL_BREACH_DOWN", "layer": layer, "message": f"{layer.title()} external low breached", "price": price_f, "level_price": lo})
        elif pct >= 95:
            alerts.append({"level": "warning", "type": "DEEP_PREMIUM_HIT", "layer": layer, "message": f"{layer.title()} deep premium reached", "price": price_f, "position_percent": round(pct, 1)})
        elif pct >= 75:
            alerts.append({"level": "info", "type": "PREMIUM_HIT", "layer": layer, "message": f"{layer.title()} premium reached", "price": price_f, "position_percent": round(pct, 1)})
        elif pct <= 5:
            alerts.append({"level": "warning", "type": "DEEP_DISCOUNT_HIT", "layer": layer, "message": f"{layer.title()} deep discount reached", "price": price_f, "position_percent": round(pct, 1)})
        elif pct <= 25:
            alerts.append({"level": "info", "type": "DISCOUNT_HIT", "layer": layer, "message": f"{layer.title()} discount reached", "price": price_f, "position_percent": round(pct, 1)})
    return alerts


@app.get("/notifications")
def notifications(symbol: str = "XAUUSD"):
    symbol = _normalise_symbol(symbol)
    alerts = _range_alerts_for_symbol(symbol)
    return {"ok": True, "symbol": symbol, "last_refresh": _now_sast_iso(), "alerts": alerts, "count": len(alerts)}

# -----------------------------------------------------------------------------
# Market Memory Candle + Map API v137
# Separate data bridge for map/AI memory. Does not touch execution EA logic.
# -----------------------------------------------------------------------------
import os as _os
import sys as _sys
from pathlib import Path as _Path
_backend_dir = str(_Path(__file__).resolve().parent)
if _backend_dir not in _sys.path:
    _sys.path.insert(0, _backend_dir)

_market_memory_error = None
try:
    import candle_store as market_memory
    market_memory.init_db()
except Exception as exc:  # pragma: no cover
    _market_memory_error = repr(exc)
    market_memory = None


@app.get("/api/v1/market-memory/status")
def market_memory_status():
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.status()


@app.post("/api/v1/candles/import")
def candles_import(payload: dict[str, Any] = Body(...)):
    """Bulk JSON candle import. EA/WebRequest can post {candles:[...]} here later."""
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    candles = payload.get("candles") if isinstance(payload, dict) else None
    if not isinstance(candles, list):
        # also accept one candle payload
        candles = [payload]
    return market_memory.upsert_candles(candles, source=str(payload.get("source") or "api-import"))


@app.post("/api/v1/candles/live")
def candles_live(payload: dict[str, Any] = Body(...)):
    """Single/latest closed candle endpoint for bridge updates."""
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.upsert_candles([payload], source=str(payload.get("source") or "ea-live"))


@app.post("/api/v1/candles/import-common-files")
def candles_import_common_files(payload: dict[str, Any] = Body(default={})):
    """Import CSVs exported by MarketMemoryBridge EA from Terminal Common Files."""
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    symbol = str((payload or {}).get("symbol") or "XAUUSD")
    timeframes = (payload or {}).get("timeframes") or ["MN1", "W1", "D1", "H4", "H1", "M15"]
    return market_memory.import_common_files(symbol=symbol, timeframes=timeframes)


@app.get("/api/v1/candles")
def candles_get(symbol: str = "XAUUSD", timeframe: str = "D1", limit: int = 500, start: str | None = None, end: str | None = None):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_candles(symbol=symbol, timeframe=timeframe, limit=limit, start=start, end=end)


@app.post("/api/v1/raw-mapping/cases")
def raw_mapping_case_create(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.create_raw_mapping_case(payload)
    response.status_code = int(result.get('status') or (201 if result.get('created') else 200))
    return result


@app.post("/api/v1/raw-mapping/events")
def raw_mapping_event_save(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.save_raw_mapping_event(payload)
    response.status_code = int(result.get('status') or (201 if result.get('ok') else 400))
    return result


@app.post("/api/v1/raw-mapping/events/batch")
def raw_mapping_events_batch(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.save_raw_mapping_events_batch(str((payload or {}).get("case_id") or ""), (payload or {}).get("events") or [])
    response.status_code = int(result.get('status') or (201 if result.get('ok') else 400))
    return result


@app.post("/api/v1/raw-mapping/events/delete")
def raw_mapping_event_delete(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.append_raw_delete_event(str((payload or {}).get("case_id") or ""), str((payload or {}).get("event_id") or ""), str((payload or {}).get("notes") or ""))
    response.status_code = int(result.get('status') or (201 if result.get('ok') else 400))
    return result


@app.get("/api/v1/raw-mapping/events")
def raw_mapping_events_get(case_id: str):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_raw_mapping_events(case_id)


@app.get("/api/v1/raw-mapping/events/export")
def raw_mapping_events_export(response: Response, case_id: str):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.export_raw_mapping_events(case_id)
    response.status_code = int(result.get('status') or (200 if result.get('ok') else 400))
    return result


@app.post("/api/v1/map/event")
def map_event_save(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.save_map_event(payload)


@app.post("/api/v1/map/structural-event")
def map_structural_event_save(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.save_structural_map_event(payload)
    response.status_code = int(result.get("status") or (201 if result.get("ok") and not result.get("duplicate") else 200 if result.get("ok") else 400))
    return result


@app.patch("/api/v1/map/structural-event/{event_id}")
def map_structural_event_patch(event_id: str, response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.patch_structural_map_event(event_id, payload or {})
    response.status_code = int(result.get("status") or (200 if result.get("ok") else 400))
    return result


@app.get("/api/v1/map/events")
def map_events_get(symbol: str = "XAUUSD", timeframe: str | None = None, limit: int = 1000, case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, structure_layer: str | None = None, source_timeframe: str | None = None, active_range_id: int | None = None, parent_range_id: int | None = None, event_type: str | None = None):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_map_events(symbol=symbol, timeframe=timeframe, limit=limit, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref, structure_layer=structure_layer, source_timeframe=source_timeframe, active_range_id=active_range_id, parent_range_id=parent_range_id, event_type=event_type)


@app.delete("/api/v1/map/event/{event_id}")
def map_event_delete(event_id: str):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.delete_map_event(event_id)


@app.delete("/api/v1/map/events/clear-candle")
def map_events_clear_candle(symbol: str = "XAUUSD", timeframe: str = "D1", time: str = ""):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.clear_map_events_for_candle(symbol=symbol, timeframe=timeframe, time=time)


@app.post("/api/v1/map/range")
def map_range_upsert(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.upsert_map_range(payload)


@app.patch("/api/v1/map/range/{range_id}")
def map_range_patch(range_id: int, response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.patch_map_range(range_id, payload or {})
    response.status_code = int(result.get("status") or (200 if result.get("ok") else 400))
    return result


@app.get("/api/v1/map/range")
def map_range_get(symbol: str = "XAUUSD", timeframe: str = "D1", range_key: str = "active"):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_map_range(symbol=symbol, timeframe=timeframe, range_key=range_key)


@app.delete("/api/v1/map/range")
def map_range_delete(symbol: str = "XAUUSD", timeframe: str = "D1", range_key: str = "active"):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.delete_map_range(symbol=symbol, timeframe=timeframe, range_key=range_key)


@app.get("/api/v1/map/ranges")
def map_ranges_list(symbol: str = "XAUUSD", timeframe: str | None = None, case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, structure_layer: str | None = None, source_timeframe: str | None = None, parent_range_id: int | None = None, limit: int = 1000):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.list_map_ranges(symbol=symbol, timeframe=timeframe, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref, structure_layer=structure_layer, source_timeframe=source_timeframe, parent_range_id=parent_range_id, limit=limit)


@app.get("/api/v1/map/range-tree")
def map_range_tree(symbol: str = "XAUUSD", case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, parent_timeframe: str = "W1", child_timeframe: str = "D1", parent_layer: str | None = None, child_layer: str | None = None):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_range_tree(symbol=symbol, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref, parent_timeframe=parent_timeframe, child_timeframe=child_timeframe, parent_layer=parent_layer, child_layer=child_layer)


@app.post("/api/v1/map/range/reparent")
def map_range_reparent(response: Response, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        response.status_code = 500
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    result = market_memory.reparent_map_range(int((payload or {}).get("child_range_id") or (payload or {}).get("range_id") or 0), (payload or {}).get("parent_range_id"))
    response.status_code = int(result.get("status") or (200 if result.get("ok") else 400))
    return result


@app.get("/api/v1/map/hierarchy-audit")
def map_hierarchy_audit(symbol: str = "XAUUSD", case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.hierarchy_audit(symbol=symbol, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref)


@app.post("/api/v1/htf/state")
def htf_state_save(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.save_htf_state_snapshot(payload)


@app.get("/api/v1/htf/states")
def htf_states_get(symbol: str = "XAUUSD", timeframe: str = "D1", limit: int = 50):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_htf_state_snapshots(symbol=symbol, timeframe=timeframe, limit=limit)

# -------------------------------
# MOS v1 GPS / Story-Chapter-Phase endpoints
# -------------------------------

@app.get("/api/v1/mos/status")
def mos_v1_status():
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.mos_status()


@app.get("/api/v1/market-gps/mock")
def market_gps_mock(
    symbol: str = "XAUUSD",
    timeframe: str = "W1",
    story_anchor: str = "WEEKLY_REF_LOW_TAKEN",
    chapter: str = "DAILY_BOS_UP",
    phase: str = "P1",
    phase_part: str = "RETEST",
    objective: str = "WEEKLY_PREMIUM",
    current_zone: str = "DISCOUNT",
):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    # Sprint-2 front-door test: allow Electron to test GPS language without database automation.
    return {
        "ok": True,
        "status": "MOCK_TRACKING_ACTIVE",
        "symbol": symbol,
        "timeframe": timeframe,
        "coordinates": {
            "story_anchor": story_anchor,
            "chapter": chapter,
            "phase": phase,
            "phase_part": phase_part,
            "objective": objective,
            "current_zone": current_zone,
        },
    }


@app.get("/api/v1/market-gps/{timeframe}")
def market_gps_active(timeframe: str, symbol: str = "XAUUSD"):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_active_gps_snapshot(symbol=symbol, timeframe=timeframe)




@app.get("/api/v1/market-gps/{timeframe}/timeline")
def market_gps_timeline(timeframe: str, symbol: str = "XAUUSD"):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_mos_timeline(symbol=symbol, timeframe=timeframe)

@app.post("/api/v1/mos/state")
def mos_save_manual_state(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.save_manual_gps_state(payload)


@app.post("/api/v1/mos/story")
def mos_create_story(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.create_narrative_story(payload)


@app.post("/api/v1/mos/chapter")
def mos_create_chapter(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.create_story_chapter(payload)


@app.post("/api/v1/mos/phase")
def mos_create_phase(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.create_market_phase(payload)


@app.post("/api/v1/mos/build-state")
def mos_build_state(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.build_mos_state(payload)
    except Exception as exc:
        return {"ok": False, "error": "MOS_BUILD_STATE_FAILED", "detail": str(exc)}


@app.get("/api/v1/mos/coordinates/{symbol}")
def mos_coordinates(symbol: str):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_mos_coordinates(symbol=symbol)


@app.get("/api/v1/mos/playback/{story_id}")
def mos_playback(story_id: int, evaluate: bool = False):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.get_mos_playback_evaluation(story_id) if evaluate else market_memory.get_mos_playback(story_id)


@app.post("/api/v1/mos/seed/case-03")
def mos_seed_case_03():
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    return market_memory.seed_case_03()


@app.post("/api/v1/mos/seed/case-03-frames")
def mos_seed_case_03_frames():
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.seed_case_03_frames()
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_CASE_03_FRAMES_FAILED", "detail": str(exc)}


@app.post("/api/v1/mos/seed-idea")
def mos_seed_idea_save(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.save_mos_seed_idea(payload)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEA_SAVE_FAILED", "detail": str(exc)}


@app.put("/api/v1/mos/seed-idea/{case_id}")
def mos_seed_idea_update(case_id: int, payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.update_mos_seed_idea(case_id, payload)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEA_UPDATE_FAILED", "detail": str(exc)}



@app.get("/api/v1/mos/seed-idea/{case_id}/payload")
def mos_seed_idea_payload(case_id: int):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.get_case_payload(case_id)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEA_PAYLOAD_FAILED", "detail": str(exc)}


@app.get("/api/v1/mos/seed-idea/{case_id}/audit")
def mos_seed_idea_audit(case_id: int, include_fallback: bool = False):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.get_case_audit(case_id, include_fallback=include_fallback)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEA_AUDIT_FAILED", "detail": str(exc)}



@app.delete("/api/v1/mos/seed-idea/{case_id}")
def mos_seed_idea_delete(case_id: int, delete_linked_events: bool = False):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.delete_mos_seed_idea(case_id, delete_linked_events=delete_linked_events)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEA_DELETE_FAILED", "detail": str(exc)}


@app.delete("/api/v1/mos/seed-ideas")
def mos_seed_ideas_clear(symbol: str = ""):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.clear_mos_seed_ideas(symbol=symbol or None)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEAS_CLEAR_FAILED", "detail": str(exc)}


@app.post("/api/v1/mos/research-reset")
def mos_research_reset(payload: dict[str, Any] = Body(...)):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.reset_research_mapping(symbol=str(payload.get("symbol") or "XAUUSD"), confirm=str(payload.get("confirm") or ""))
    except Exception as exc:
        return {"ok": False, "error": "MOS_RESEARCH_RESET_FAILED", "detail": str(exc)}

@app.get("/api/v1/mos/seed-ideas")
def mos_seed_ideas(symbol: str = "XAUUSD", limit: int = 50):
    if market_memory is None:
        return {"ok": False, "error": "market memory module unavailable", "detail": _market_memory_error}
    try:
        return market_memory.get_mos_seed_ideas(symbol=symbol, limit=limit)
    except Exception as exc:
        return {"ok": False, "error": "MOS_SEED_IDEAS_FETCH_FAILED", "detail": str(exc)}
