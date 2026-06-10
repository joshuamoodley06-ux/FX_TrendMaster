from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from processor.models.raw_event import RawEvent


@dataclass
class AuditWarning:
    code: str
    message: str
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.event_id is not None:
            payload["event_id"] = self.event_id
        return payload


@dataclass
class LedgerResolveResult:
    visible_events: list[dict[str, Any]]
    delete_trail: list[dict[str, Any]]
    hidden_event_ids: list[str]
    warnings: list[AuditWarning] = field(default_factory=list)
    delete_effects: dict[str, str] = field(default_factory=dict)
    orphaned_delete_ids: list[str] = field(default_factory=list)
    raw_record_count: int = 0
    delete_record_count: int = 0
    visible_record_count: int = 0
    orphaned_delete_count: int = 0
