from dataclasses import dataclass, field
from typing import Optional, Any, Dict

@dataclass(frozen=True)
class RangeRecord:
    range_id: str
    layer: str
    status: str
    parent_id: Optional[str] = None
    active_from_time: Optional[str] = None
    inactive_from_time: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
