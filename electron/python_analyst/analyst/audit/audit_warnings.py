"""Audit warning primitives.

Audits warn, they never crash an analysis run. Every anomaly becomes a
row in audit_warnings.csv.
"""

from __future__ import annotations

from dataclasses import dataclass

AUDIT_WARNING_COLUMNS = ["code", "severity", "case_ref", "subject_id", "message"]


@dataclass(frozen=True)
class AuditWarning:
    code: str
    message: str
    case_ref: str | None = None
    subject_id: str | None = None
    severity: str = "WARNING"

    def to_row(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "case_ref": self.case_ref or "",
            "subject_id": self.subject_id or "",
            "message": self.message,
        }
