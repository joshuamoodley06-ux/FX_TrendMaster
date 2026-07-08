"""Range Library scaffold for future range analytics."""

from .models import RangeRecord
from .report import generate_summary_report

__all__ = ["RangeRecord", "generate_summary_report"]
