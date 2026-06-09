from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LedgerResolveResult:
    visible_events: list[dict[str, Any]]
    hidden_event_ids: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
