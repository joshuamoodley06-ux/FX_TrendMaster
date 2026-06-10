from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


@dataclass
class RawEvent:
    event_id: str
    created_order: int
    event_type: str
    is_deleted: int = 0
    supersedes_event_id: Optional[str] = None
    candle_time_utc_ms: Optional[int] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    price: Optional[float] = None
    price_int: Optional[int] = None
    price_scale: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RawEvent:
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RawEvent:
        return cls(
            event_id=str(payload.get("event_id") or ""),
            created_order=int(payload.get("created_order") or 0),
            event_type=str(payload.get("event_type") or ""),
            is_deleted=int(payload.get("is_deleted") or 0),
            supersedes_event_id=_optional_str(payload.get("supersedes_event_id")),
            candle_time_utc_ms=_optional_int(payload.get("candle_time_utc_ms")),
            symbol=_optional_str(payload.get("symbol")),
            timeframe=_optional_str(payload.get("timeframe")),
            price=_optional_float(payload.get("price")),
            price_int=_optional_int(payload.get("price_int")),
            price_scale=_optional_int(payload.get("price_scale")),
            raw=dict(payload),
        )
