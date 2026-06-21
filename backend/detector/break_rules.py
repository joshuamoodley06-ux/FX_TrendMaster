"""BOS break rule selection by timeframe (Phase 0 contract §9.5)."""

from __future__ import annotations

WICK = "WICK"
BODY_CLOSE = "BODY_CLOSE"
RECLAIM_TOUCH = "RECLAIM_TOUCH"
RECLAIM_CLOSE = "RECLAIM_CLOSE"

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


def reclaim_touch_after_bos_up(
    candle_low: float,
    candle_close: float,
    old_rh: float,
    break_rule: str,
) -> bool:
    """Observational wick tag of old RH (HTF) or close inside (LTF)."""
    if break_rule == BODY_CLOSE:
        return candle_close <= old_rh
    return candle_low <= old_rh


def reclaim_touch_after_bos_down(
    candle_high: float,
    candle_close: float,
    old_rl: float,
    break_rule: str,
) -> bool:
    """Observational wick tag of old RL (HTF) or close inside (LTF)."""
    if break_rule == BODY_CLOSE:
        return candle_close >= old_rl
    return candle_high >= old_rl


def reclaim_close_after_bos_up(candle_close: float, old_rh: float) -> bool:
    """Body close back inside old RH — lifecycle confirmation for range birth."""
    return candle_close <= old_rh


def reclaim_close_after_bos_down(candle_close: float, old_rl: float) -> bool:
    """Body close back inside old RL — LTF lifecycle confirmation."""
    return candle_close >= old_rl


def reclaim_confirmed_after_bos_up(
    candle_low: float,
    candle_close: float,
    old_rh: float,
    break_rule: str,
) -> bool:
    """HTF: wick tag of old RH completes reclaim. LTF (M15): body close inside only."""
    if break_rule == BODY_CLOSE:
        return reclaim_close_after_bos_up(candle_close, old_rh)
    return reclaim_touch_after_bos_up(candle_low, candle_close, old_rh, break_rule)


def reclaim_confirmed_after_bos_down(
    candle_high: float,
    candle_close: float,
    old_rl: float,
    break_rule: str,
) -> bool:
    """HTF: wick tag of old RL completes reclaim. LTF (M15): body close inside only."""
    if break_rule == BODY_CLOSE:
        return reclaim_close_after_bos_down(candle_close, old_rl)
    return reclaim_touch_after_bos_down(candle_high, candle_close, old_rl, break_rule)


def reclaims_after_bos_up(
    candle_low: float,
    candle_close: float,
    old_rh: float,
    break_rule: str,
) -> bool:
    return reclaim_confirmed_after_bos_up(candle_low, candle_close, old_rh, break_rule)


def reclaims_after_bos_down(
    candle_high: float,
    candle_close: float,
    old_rl: float,
    break_rule: str,
) -> bool:
    return reclaim_confirmed_after_bos_down(candle_high, candle_close, old_rl, break_rule)
