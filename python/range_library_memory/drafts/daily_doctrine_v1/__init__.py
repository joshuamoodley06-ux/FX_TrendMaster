"""Draft-only Daily doctrine research suite.

Do not import this package from the active doctrine registry until Josh approves the
individual rules and integration is explicitly scheduled.
"""

from .approved_weekly_on_daily import (
    calculate_daily_retracement_depth,
    classify_daily_movement,
    classify_daily_profile,
    detect_daily_extreme_rejections,
    detect_daily_reclaim,
)
from .core import (
    anchor_direction,
    classify_first_daily_after_weekly_rejection,
    classify_first_range_transition,
    classify_pro_counter,
    classify_profile,
    detect_bos,
    detect_pdh_pdl_sweeps,
    profile_streaks,
    weekly_zone,
)

__all__ = [
    "anchor_direction",
    "calculate_daily_retracement_depth",
    "classify_daily_movement",
    "classify_daily_profile",
    "classify_first_daily_after_weekly_rejection",
    "classify_first_range_transition",
    "classify_pro_counter",
    "classify_profile",
    "detect_bos",
    "detect_daily_extreme_rejections",
    "detect_daily_reclaim",
    "detect_pdh_pdl_sweeps",
    "profile_streaks",
    "weekly_zone",
]
