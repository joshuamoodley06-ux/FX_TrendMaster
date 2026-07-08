"""Data models for normalized range records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RangeRecord:
    """Minimal normalized range representation for report scaffolding."""

    range_id: str
    layer: str
    status: str
    parent_id: str | None = None
    source: dict[str, Any] | None = None

    @property
    def is_orphan(self) -> bool:
        return self.parent_id is None
