"""Catalog for Daily doctrine drafts.

The catalog is deliberately not imported by the production runtime registry.
It provides stable names and planned dependencies for tests and later packaging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .approved_ports import (
    run_daily_bos,
    run_daily_extreme_rejection_destination,
    run_daily_movement_classification,
    run_daily_profile_classification,
    run_daily_reclaim,
    run_daily_reclaim_depth,
)
from .weekly_relative import (
    run_daily_child_trend_classification,
    run_daily_profile_streaks,
    run_first_daily_at_weekly_extreme_rejection,
    run_first_daily_external_to_internal,
    run_pdl_pdh_reversal_sweep,
)

Runner = Callable[[Any], dict[str, list[dict[str, Any]]]]


@dataclass(frozen=True)
class DailyDraftScript:
    script_key: str
    display_name: str
    planned_order: int
    planned_dependency: str | None
    scope: str
    runner: Runner


DAILY_DRAFT_CATALOG: tuple[DailyDraftScript, ...] = (
    DailyDraftScript(
        "daily_structure",
        "Daily BOS",
        100,
        "weekly_daily_relationship_builder",
        "DAILY_RANGE",
        run_daily_bos,
    ),
    DailyDraftScript(
        "daily_reclaim",
        "Daily Reclaim",
        110,
        "daily_structure",
        "DAILY_RANGE",
        run_daily_reclaim,
    ),
    DailyDraftScript(
        "daily_reclaim_depth",
        "Daily Reclaim Depth",
        120,
        "daily_reclaim",
        "DAILY_RANGE",
        run_daily_reclaim_depth,
    ),
    DailyDraftScript(
        "daily_movement_classification",
        "Daily Movement Classification",
        130,
        "daily_structure",
        "DAILY_RANGE",
        run_daily_movement_classification,
    ),
    DailyDraftScript(
        "daily_profile_classification",
        "Daily Profile Classification",
        140,
        "daily_reclaim_depth",
        "DAILY_RANGE",
        run_daily_profile_classification,
    ),
    DailyDraftScript(
        "daily_extreme_rejection_destination",
        "Daily Extreme Rejection Destination",
        150,
        "daily_profile_classification",
        "DAILY_RANGE",
        run_daily_extreme_rejection_destination,
    ),
    DailyDraftScript(
        "daily_child_trend_classification",
        "Daily Child Trend Classification",
        160,
        "weekly_daily_relationship_builder",
        "WEEKLY_PARENT",
        run_daily_child_trend_classification,
    ),
    DailyDraftScript(
        "first_daily_external_to_internal",
        "First Daily External-to-Internal",
        170,
        "daily_child_trend_classification",
        "WEEKLY_PARENT",
        run_first_daily_external_to_internal,
    ),
    DailyDraftScript(
        "first_daily_at_weekly_extreme_rejection",
        "First Daily at Weekly Extreme Rejection",
        180,
        "weekly_extreme_rejection_destination",
        "WEEKLY_PARENT",
        run_first_daily_at_weekly_extreme_rejection,
    ),
    DailyDraftScript(
        "daily_profile_streaks",
        "Daily Profile Streaks",
        190,
        "daily_profile_classification",
        "WEEKLY_PARENT",
        run_daily_profile_streaks,
    ),
    DailyDraftScript(
        "pdl_pdh_reversal_sweep",
        "PDL / PDH Reversal Sweep",
        200,
        "weekly_daily_relationship_builder",
        "WEEKLY_PARENT",
        run_pdl_pdh_reversal_sweep,
    ),
)

_CATALOG_BY_KEY = {candidate.script_key: candidate for candidate in DAILY_DRAFT_CATALOG}


def run_daily_draft(script_key: str, context: Any) -> dict[str, list[dict[str, Any]]]:
    candidate = _CATALOG_BY_KEY.get(str(script_key or "").strip())
    if candidate is None:
        supported = ", ".join(item.script_key for item in DAILY_DRAFT_CATALOG)
        raise KeyError(f"Unknown Daily draft {script_key!r}. Supported: {supported}")
    return candidate.runner(context)
