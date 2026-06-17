"""BOS break rule selection by timeframe (Phase 0 contract §9.5)."""

from __future__ import annotations

WICK = "WICK"
BODY_CLOSE = "BODY_CLOSE"

_WICK_TIMEFRAMES = frozenset({"MN1", "W1", "D1", "H4", "H1"})
_BODY_CLOSE_TIMEFRAMES = frozenset({"M15", "M5", "M1", "MICRO"})


def normalise_timeframe(tf: str) -> str:
    val = str(tf or "D1").strip().upper()
    aliases = {
        "MN": "MN1",
        "MONTHLY": "MN1",
        "MACRO": "MN1",
        "WEEKLY": "W1",
        "DAILY": "D1",
        "4H": "H4",
        "1H": "H1",
        "15M": "M15",
        "5M": "M5",
        "1M": "M1",
    }
    return aliases.get(val, val)


def timeframe_prefix(tf: str) -> str:
    return normalise_timeframe(tf)


def structure_layer_for_timeframe(tf: str) -> str:
    t = normalise_timeframe(tf)
    if t in {"MN1"}:
        return "MACRO"
    if t == "W1":
        return "WEEKLY"
    if t == "D1":
        return "DAILY"
    return "INTRADAY"


def break_rule_for_timeframe(tf: str) -> str:
    t = normalise_timeframe(tf)
    if t in _BODY_CLOSE_TIMEFRAMES:
        return BODY_CLOSE
    if t in _WICK_TIMEFRAMES:
        return WICK
    return WICK


def breaches_high(candle_high: float, candle_close: float, level: float, break_rule: str) -> bool:
    if break_rule == BODY_CLOSE:
        return candle_close > level
    return candle_high > level


def breaches_low(candle_low: float, candle_close: float, level: float, break_rule: str) -> bool:
    if break_rule == BODY_CLOSE:
        return candle_close < level
    return candle_low < level
