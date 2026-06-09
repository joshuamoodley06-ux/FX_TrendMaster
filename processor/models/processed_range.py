from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProcessedRange:
    range_id: str
    symbol: str
    timeframe: str
    high_event_id: Optional[str]
    low_event_id: Optional[str]
    start_time_utc_ms: int
    end_time_utc_ms: Optional[int]
