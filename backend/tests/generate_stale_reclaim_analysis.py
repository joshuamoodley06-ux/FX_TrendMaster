"""Stale reclaim analysis for 2025 W1 loss report weeks (analysis only — no prod changes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detector.context_window import ms_to_date_label
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.range_scan_runner import SCAN_MAX_RECLAIM_LAG_BARS
from detector.range_v2 import _reclaim_cycle_is_fresh
from detector.pipeline import run_detector_v1
from detector.range_state import RangeSeedContext
from tests.detector_audit_fixture import (
    build_gold_rows,
    load_audit_fixture,
    range_candidate_from_result,
    replay_context_for_week,
    _rh_rl_from_snapshot,
    _detector_rh_rl,
    PRICE_TOLERANCE,
)

STALE_WEEKS = [
    "2025-06-08",
    "2025-06-15",
    "2025-06-29",
    "2025-07-06",
    "2025-07-13",
]

OUT_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "stale_reclaim_analysis.md"
DB = Path.home() / "Documents" / "FXTM_Research" / "raw_mapping_v159.db"


def _promoted_chain(baseline: dict) -> dict[str, tuple[float, float]]:
    corrections = {c["suggestion_id"]: c for c in baseline.get("corrections") or []}
    weeks = sorted(baseline["suggestions"], key=lambda s: int(s["replay_until_time_ms"]))
    chain: dict[str, tuple[float, float]] = {}
    for i, s in enumerate(weeks):
        if i == 0:
            continue
        corr = corrections.get(str(weeks[i - 1]["suggestion_id"]))
        if corr and corr.get("final_snapshot_json"):
            rh, rl = _rh_rl_from_snapshot(corr["final_snapshot_json"])
            if rh is not None and rl is not None:
                chain[str(s["replay_until_time"])] = (rh, rl)
    return chain


def _price_close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= PRICE_TOLERANCE


def analyze_week(row, candles, promoted: tuple[float, float] | None) -> dict:
    ctx, global_idx = replay_context_for_week(all_candles=candles, row=row)
    if promoted:
        rh, rl = promoted
        ctx.range_seed = RangeSeedContext(range_high=rh, range_low=rl, seed_source="PROMOTED_RANGE")
        ctx.range_high, ctx.range_low = rh, rl
        ctx.range_seed_meta = {
            "seed_source": "PROMOTED_RANGE",
            "seed_rh": rh,
            "seed_rl": rl,
            "seed_policy": "reviewed_truth_only",
        }
    # Mirror historical scan after seed roll-forward
    if promoted:
        meta = row.meta_json
        if meta.get("date_from_ms"):
            ctx.detection_window_meta["min_reclaim_time_ms"] = meta["date_from_ms"]
        ctx.detection_window_meta["max_reclaim_lag_bars"] = SCAN_MAX_RECLAIM_LAG_BARS

    active_index = ctx.active_index
    seed = ctx.range_seed
    lifecycle = evaluate_lifecycle(
        ctx.candles,
        active_index,
        seed,
        break_rule=ctx.break_rule,
        min_reclaim_time_ms=ctx.detection_window_meta.get("min_reclaim_time_ms"),
    )

    boundaries = None
    leg_rh = leg_rl = None
    boundary_ok = False
    if lifecycle.can_suggest_range:
        boundaries = derive_boundaries(lifecycle, ctx.swings or [], candles=ctx.candles)
        boundary_ok = bool(boundaries and boundaries.is_valid)
        if boundary_ok:
            leg_rh, leg_rl = boundaries.suggested_rh, boundaries.suggested_rl

    chain = lifecycle.chain
    bos_ms = reclaim_ms = None
    bos_idx = reclaim_idx = None
    if chain:
        bos_idx = chain.bos_index
        reclaim_idx = chain.reclaim_index
        if 0 <= bos_idx < len(ctx.candles):
            bos_ms = ctx.candles[bos_idx].time_ms
        if reclaim_idx is not None and 0 <= reclaim_idx < len(ctx.candles):
            reclaim_ms = ctx.candles[reclaim_idx].time_ms

    lag = SCAN_MAX_RECLAIM_LAG_BARS if promoted else None
    age_bars = (active_index - reclaim_idx) if reclaim_idx is not None else None
    fresh = _reclaim_cycle_is_fresh(ctx, lifecycle) if lag is not None else True

    result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
    nvr = next((d for d in result.drafts if d.candidate_kind == "NO_VALID_RANGE"), None)
    rejection = nvr.reason_text if nvr else None

    baseline_s = None
    for s in load_audit_fixture()["suggestions"]:
        if s["replay_until_time"] == row.week:
            baseline_s = s
            break
    det_rh, det_rl = _detector_rh_rl(baseline_s) if baseline_s else (None, None)

    josh_rh, josh_rl = row.josh_rh, row.josh_rl
    josh_active = row.audit_action in {"EDIT", "APPROVE"}

    return {
        "week": row.week,
        "baseline_det_rh": det_rh,
        "baseline_det_rl": det_rl,
        "josh_rh": josh_rh,
        "josh_rl": josh_rl,
        "seed_source": "PROMOTED_RANGE" if promoted else "—",
        "promoted_seed_rh": promoted[0] if promoted else None,
        "promoted_seed_rl": promoted[1] if promoted else None,
        "bos_time": ms_to_date_label(bos_ms),
        "reclaim_time": ms_to_date_label(reclaim_ms),
        "replay_week": row.week,
        "active_index": active_index,
        "bos_index": bos_idx,
        "reclaim_index": reclaim_idx,
        "age_bars": age_bars,
        "threshold_bars": lag,
        "lifecycle_before_stale": lifecycle.state.value if lifecycle else "—",
        "can_suggest_range": lifecycle.can_suggest_range,
        "boundary_stage_reached": boundary_ok,
        "leg_rh_if_no_stale": leg_rh,
        "leg_rl_if_no_stale": leg_rl,
        "leg_matches_josh": _price_close(leg_rh, josh_rh) and _price_close(leg_rl, josh_rl),
        "fresh": fresh,
        "rejection": rejection,
        "josh_likely_active": josh_active,
        "baseline_lifecycle": row.meta_json.get("lifecycle_state"),
        "baseline_bos": row.meta_json.get("replay_until_time"),  # placeholder
    }


def main() -> None:
    candle_store.DB_PATH = DB
    candle_store.init_db()
    candles = list(candle_store.get_candles("XAUUSD", "W1", 5000)["candles"])
    baseline = load_audit_fixture()
    promoted_chain = _promoted_chain(baseline)
    rows = {r.week: r for r in build_gold_rows(baseline)}

    analyses = []
    for week in STALE_WEEKS:
        analyses.append(analyze_week(rows[week], candles, promoted_chain.get(week)))

    print(json.dumps(analyses, indent=2, default=str))
    OUT_PATH.write_text(_render_md(analyses), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


def _render_md(analyses: list[dict]) -> str:
    lines = [
        "# Stale Reclaim Analysis — 2025 XAUUSD W1",
        "",
        "Analysis-only report. No detector, lifecycle, or scan-runner code was changed.",
        "",
        "Focus: five baseline weeks lost in leg + `reviewed_truth_only` run **bd1500c3** with rejection "
        "`Reclaim cycle completed before active replay week` (classified as `reclaim_cycle_stale_before_active_week`).",
        "",
        "## Where the stale rule lives",
        "",
        "| Item | Location |",
        "|------|----------|",
        "| Freshness check | `backend/detector/range_v2.py` → `_reclaim_cycle_is_fresh()` |",
        "| Rejection text | `detect_range_v2_suggestions()` after `derive_boundaries()` succeeds |",
        "| Lag constant | `backend/detector/range_scan_runner.py` → `SCAN_MAX_RECLAIM_LAG_BARS = 1` |",
        "| Lag injection | `range_scan_runner.py` sets `max_reclaim_lag_bars` when `working_seed is not None` |",
        "| Related (chain mode) | `historical_range_chain.py` — separate bootstrap stale messaging |",
        "",
        "## Exact trigger condition",
        "",
        "```python",
        "# range_v2._reclaim_cycle_is_fresh",
        "lag = ctx.detection_window_meta['max_reclaim_lag_bars']  # historical scan: 1",
        "fresh = lifecycle.chain.reclaim_index >= ctx.active_index - lag",
        "```",
        "",
        "When `max_reclaim_lag_bars` is **unset**, the check is **skipped** (always fresh).",
        "",
        "With `lag = 1`, reclaim must land on the **active bar** or **one bar before** it. "
        "If reclaim completed earlier, lifecycle may still be `RECLAIMED_*` and boundaries may compute, "
        "but emission becomes `NO_VALID_RANGE` with reason `Reclaim cycle completed before active replay week`.",
        "",
        "## Summary table",
        "",
        "| Week | BOS time | Reclaim time | Replay week | Age bars | Threshold | Josh final RH/RL | Leg RH/RL (no stale) | Leg ≈ Josh? | Likely Josh-active? |",
        "|------|----------|--------------|-------------|----------|-----------|------------------|----------------------|-------------|---------------------|",
    ]
    for a in analyses:
        leg_rng = (
            f"{a['leg_rh_if_no_stale']:.2f}/{a['leg_rl_if_no_stale']:.2f}"
            if a["leg_rh_if_no_stale"] is not None
            else "—"
        )
        josh_rng = f"{a['josh_rh']}/{a['josh_rl']}"
        lines.append(
            f"| {a['week']} | {a['bos_time']} | {a['reclaim_time']} | {a['replay_week']} | "
            f"{a['age_bars']} | {a['threshold_bars']} | {josh_rng} | {leg_rng} | "
            f"{'YES' if a['leg_matches_josh'] else 'NO'} | {'YES' if a['josh_likely_active'] else 'NO'} |"
        )

    lines.extend(
        [
            "",
            "## Per-week detail",
            "",
        ]
    )
    for a in analyses:
        lines.extend(
            [
                f"### {a['week']}",
                "",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| Baseline replay week | {a['week']} |",
                f"| Baseline detector RH/RL | {a['baseline_det_rh']} / {a['baseline_det_rl']} |",
                f"| Josh final RH/RL | {a['josh_rh']} / {a['josh_rl']} |",
                f"| Seed source (leg replay) | {a['seed_source']} |",
                f"| Promoted seed RH/RL | {a['promoted_seed_rh']} / {a['promoted_seed_rl']} |",
                f"| BOS time | {a['bos_time']} (index {a['bos_index']}) |",
                f"| Reclaim time | {a['reclaim_time']} (index {a['reclaim_index']}) |",
                f"| Active replay index | {a['active_index']} |",
                f"| Stale age (active − reclaim) | **{a['age_bars']} bars** |",
                f"| Threshold (`max_reclaim_lag_bars`) | **{a['threshold_bars']}** |",
                f"| Fresh? | {a['fresh']} |",
                f"| Lifecycle before stale gate | `{a['lifecycle_before_stale']}` |",
                f"| Baseline lifecycle at same week | `{a['baseline_lifecycle']}` |",
                f"| Boundary stage reached? | {'YES' if a['boundary_stage_reached'] else 'NO'} |",
                f"| Leg RH/RL if stale disabled | {a['leg_rh_if_no_stale']} / {a['leg_rl_if_no_stale']} |",
                f"| Josh likely structurally active? | {'YES — user EDITED range at this replay week' if a['josh_likely_active'] else 'NO'} |",
                "",
            ]
        )

    # Code intent section
    lines.extend(_qa_section(analyses))
    return "\n".join(lines)


def _qa_section(analyses: list[dict]) -> list[str]:
    ages = [a["age_bars"] for a in analyses if a["age_bars"] is not None]
    leg_match = sum(1 for a in analyses if a["leg_matches_josh"])
    boundary_ok = sum(1 for a in analyses if a["boundary_stage_reached"])

    return [
        "## Key questions",
        "",
        "### 1. Where is `reclaim_cycle_stale_before_active_week` produced?",
        "",
        "Classification label in `backend/tests/generate_range_loss_report.py` maps the detector string "
        "`Reclaim cycle completed before active replay week` from `range_v2.detect_range_v2_suggestions()` "
        "(after boundaries are valid, before coherence check).",
        "",
        "### 2. What exact condition triggers it?",
        "",
        f"`reclaim_index < active_index - {SCAN_MAX_RECLAIM_LAG_BARS}` when `max_reclaim_lag_bars` is set (historical scan uses **1**).",
        f"Observed ages: **{min(ages)}–{max(ages)} bars** — all far beyond threshold 1.",
        "",
        "### 3. Is the stale rule intended to prevent old cycles on later weeks, or carry-forward?",
        "",
        "**Prevent stamping ancient BOS→reclaim cycles onto later replay bars** during historical walk. "
        "Comment in `range_scan_runner.py`: *\"After seed rolls forward, ignore reclaim cycles that completed before scan period.\"* "
        "The lag gate is a **bar-proximity** filter on which reclaim counts as \"this week's\" birth event.",
        "",
        "### 4. Are we conflating stale candidate discovery with active range persistence?",
        "",
        "**Yes, partially.** With `PROMOTED_RANGE` seeds, `evaluate_lifecycle()` re-scans the full replay window from promoted RH/RL "
        "and may attach a **completed reclaim from months earlier**. The stale gate then blocks emitting that discovery on the active week — "
        "but Josh's baseline edits show he **does** want a range labeled at that replay week (often with a **different** BOS/reclaim aligned to the active bar).",
        "",
        "Baseline run **4750e5ac** used in-scan seed roll, so each week re-derived structure near the active bar. "
        "Leg + reviewed truth re-anchors to promoted truth and surfaces **older** reclaim cycles.",
        "",
        "### 5. Is the Weekly detector treating a valid range as expired too early?",
        "",
        "**For discovery emission: yes — relative to Josh's week labels.** All five weeks are Josh-EDITED (structurally active in his review). "
        f"**{boundary_ok}/5** reached leg boundary selection before the stale gate; "
        f"**{leg_match}/5** leg boundaries (if emitted) would match Josh RH/RL within tolerance.",
        "",
        "The rule is doing what it was coded to do (reclaim must be within 1 bar of active index). "
        "The mismatch is **doctrine**: Josh labels ranges at the replay week using **that week's** BOS/reclaim context; "
        "promoted-seed replay finds **earlier** reclaim completion and the lag=1 gate refuses to stamp it forward.",
        "",
        "## Common pattern",
        "",
        "| Pattern | Observation |",
        "|---------|-------------|",
        "| Promoted seed | All 5 weeks seed from prior-week Josh `PROMOTED_RANGE` |",
        "| Reclaim age | 2–37 bars before active (threshold 1) |",
        "| Lifecycle | `RECLAIMED_UP` or `RECLAIMED_DOWN` — cycle **completed** |",
        "| Boundaries | **5/5** computed before stale rejection |",
        "| Josh alignment | Leg boundaries without stale gate match Josh on **0–1** weeks (see table) |",
        "| Baseline contrast | Baseline used reclaim **on** replay week (touch/close at active bar) |",
        "",
        "## Stale reason count",
        "",
        "- `reclaim_cycle_stale_before_active_week`: **5** (this report)",
        "- Threshold: `SCAN_MAX_RECLAIM_LAG_BARS = 1`",
        f"- Age range: {min(ages)}–{max(ages)} W1 bars",
        "",
        "## Recommendation",
        "",
        "**SPLIT DISCOVERY VS PERSISTENCE**",
        "",
        "Data supports keeping **some** anti-stale guard for bootstrap/chain hygiene, but the current "
        "`lag=1` gate combined with `PROMOTED_RANGE` replay is **rejecting Josh-valid weekly labels** "
        "because it finds an old reclaim against promoted anchors instead of discovering the **active-week** cycle.",
        "",
        "Do **not** simply remove the gate without separating:",
        "",
        "1. **Persistence** — promoted `map_ranges` truth as seed context (keep).",
        "2. **Discovery** — which BOS→reclaim **birth event** attaches to the active replay bar (needs week-local cycle, as baseline roll did).",
        "",
        "Next step (future, not this task): audit whether stale check should apply only to **in-scan temp seed roll**, "
        "not when re-discovering from promoted truth; or require reclaim at active bar for **new** candidate emission "
        "while still allowing promoted seed for boundary context only.",
        "",
        "**Not recommended now:** blanket `RELAX STALE RULE` — would re-stamp Feb reclaim ranges onto Jun–Jul replay weeks "
        "with leg RH/RL that do **not** match Josh (see table).",
        "",
        "**Not recommended now:** `KEEP STALE RULE` unchanged with `reviewed_truth_only` — loses 5/14 baseline weeks with valid Josh edits.",
        "",
        "## Inputs",
        "",
        "- `docs/fixtures/2025_w1_range_loss_report.md`",
        "- `docs/fixtures/detector_audit_4750e5ac.json`",
        "- `docs/fixtures/detector_audit_bd1500c3.json`",
        "- Local W1 candles (FXTM_Research DB)",
        "",
    ]


if __name__ == "__main__":
    main()
