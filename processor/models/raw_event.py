from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class RawEvent(BaseModel):
    event_id: str
    case_id: str
    symbol: str
    timeframe: str
    candle_time_utc_ms: int
    candle_index: Optional[int] = None
    price: Optional[float] = None
    price_int: Optional[int] = None
    price_scale: Optional[int] = None
    event_type: str
    event_side: str = "NONE"
    source: str = "manual"
    created_order: int
    is_deleted: int = 0
    supersedes_event_id: Optional[str] = None
    notes: str = ""
    raw: dict[str, Any] = {}
