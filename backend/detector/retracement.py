"""Retracement measurement for RANGE_V2 impulse legs (detector layer)."""

from __future__ import annotations

from dataclasses import dataclass

from detector.models import NormalizedCandle
from detector.range_state import BosDirection, BosReclaimChain


@dataclass(frozen=True)
class RetracementMeasurement:
    percent: float | None
    retracement_class: str | None
    retracement_price: float | None
    retracement_candle_index: int | None
    retracement_time_ms: int | None
    impulse_high: float | None
    impulse_low: float | None
    direction: str | None
    reason_text: str | None = None

    def to_meta(self) -> dict[str, float | int | str | None]:
        return {
            "retracement_percent": self.percent,
            "retracement_class": self.retracement_class,
            "retracement_price": self.retracement_price,
            "retracement_candle_index": self.retracement_candle_index,
            "retracement_time_ms": self.retracement_time_ms,
            "retracement_impulse_high": self.impulse_high,
            "retracement_impulse_low": self.impulse_low,
            "retracement_direction": self.direction,
            "retracement_reason": self.reason_text,
        }


def classify_retracement(percent: float | None) -> str | None:
    if percent is None:
        return None
    if percent > 1.0:
        return "EXTREME"
    if percent >= 0.66:
        return "DEEP"
    if percent >= 0.33:
        return "MID"
    return "SHALLOW"


def measure_retracement_for_chain(
    candles: list[NormalizedCandle],
    chain: BosReclaimChain,
    *,
    impulse_high: float,
    impulse_low: float,
) -> RetracementMeasurement:
    """
    Measure retracement depth into the new impulse leg between BOS and reclaim.

    Bullish BOS UP:
        (impulse_high - lowest_low_after_bos) / (impulse_high - impulse_low)
    Bearish BOS DOWN:
        (highest_high_after_bos - impulse_low) / (impulse_high - impulse_low)
    """
    try:
        rh = float(impulse_high)
        rl = float(impulse_low)
    except (TypeError, ValueError):
        return RetracementMeasurement(
            percent=None,
            retracement_class=None,
            retracement_price=None,
            retracement_candle_index=None,
            retracement_time_ms=None,
            impulse_high=None,
            impulse_low=None,
            direction=chain.direction.value,
            reason_text="Invalid impulse high/low",
        )

    if rh <= rl:
        return RetracementMeasurement(
            percent=None,
            retracement_class=None,
            retracement_price=None,
            retracement_candle_index=None,
            retracement_time_ms=None,
            impulse_high=rh,
            impulse_low=rl,
            direction=chain.direction.value,
            reason_text="Impulse span must be positive",
        )

    bos_idx = int(chain.bos_index)
    reclaim_idx = int(chain.reclaim_index)
    if bos_idx < 0 or reclaim_idx <= bos_idx or reclaim_idx >= len(candles):
        return RetracementMeasurement(
            percent=None,
            retracement_class=None,
            retracement_price=None,
            retracement_candle_index=None,
            retracement_time_ms=None,
            impulse_high=rh,
            impulse_low=rl,
            direction=chain.direction.value,
            reason_text="BOS/reclaim indices out of range",
        )

    window = candles[bos_idx + 1 : reclaim_idx + 1]
    if not window:
        return RetracementMeasurement(
            percent=None,
            retracement_class=None,
            retracement_price=None,
            retracement_candle_index=None,
            retracement_time_ms=None,
            impulse_high=rh,
            impulse_low=rl,
            direction=chain.direction.value,
            reason_text="No candles between BOS and reclaim",
        )

    span = rh - rl
    if chain.direction == BosDirection.UP:
        extreme = min(window, key=lambda c: c.low)
        percent = max((rh - float(extreme.low)) / span, 0.0)
        return RetracementMeasurement(
            percent=round(percent, 6),
            retracement_class=classify_retracement(percent),
            retracement_price=float(extreme.low),
            retracement_candle_index=int(extreme.index),
            retracement_time_ms=int(extreme.time_ms),
            impulse_high=rh,
            impulse_low=rl,
            direction=chain.direction.value,
            reason_text="Measured lowest low after BOS through reclaim",
        )

    extreme = max(window, key=lambda c: c.high)
    percent = max((float(extreme.high) - rl) / span, 0.0)
    return RetracementMeasurement(
        percent=round(percent, 6),
        retracement_class=classify_retracement(percent),
        retracement_price=float(extreme.high),
        retracement_candle_index=int(extreme.index),
        retracement_time_ms=int(extreme.time_ms),
        impulse_high=rh,
        impulse_low=rl,
        direction=chain.direction.value,
        reason_text="Measured highest high after BOS through reclaim",
    )
