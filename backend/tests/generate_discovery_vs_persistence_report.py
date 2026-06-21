"""Discovery vs persistence report — 2025 W1 recovery after split implementation."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.pipeline import run_detector_v1
from detector.range_scan_runner import SCAN_MAX_RECLAIM_LAG_BARS
from detector.range_seed import (
    DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
    DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE,
    SEED_SOURCE_PROMOTED_RANGE,
)
from detector.range_state import RangeSeedContext
from tests.detector_audit_fixture import (
    build_gold_rows,
    load_audit_fixture,
    range_candidate_from_result,
    replay_context_for_week,
    _rh_rl_from_snapshot,
)

BASELINE_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "detector_audit_4750e5ac.json"
OUT_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "discovery_vs_persistence_report.md"

STALE_WEEKS = [
    "2025-06-08",
    "2025-06-15",
    "2025-06-29",
    "2025-07-06",
    "2025-07-13",
]

JUN_JUL_CLUSTER = STALE_WEEKS

DB_CANDIDATES = [
    Path.home() / "Documents" / "FXTM_Research" / "raw_mapping_v159.db",
    BACKEND_DIR / "data" / "raw_mapping_v159.db",
]


def _load_candles():
    import candle_store

    for db in DB_CANDIDATES:
        if not db.is_file():
            continue
        candle_store.DB_PATH = db
        candle_store.init_db()
        payload = candle_store.get_candles(symbol="XAUUSD", timeframe="W1", limit=5000)
        candles = list(payload.get("candles") or [])
        if len(candles) >= 200:
            return candles
    return None


def _promoted_chain(baseline: dict) -> dict[str, tuple[float, float]]:
    corrections = {c["suggestion_id"]: c for c in baseline.get("corrections") or []}
    weeks = sorted(baseline.get("suggestions") or [], key=lambda s: int(s["replay_until_time_ms"]))
    chain: dict[str, tuple[float, float]] = {}
    for i, suggestion in enumerate(weeks):
        if i == 0:
            continue
        week = str(suggestion["replay_until_time"])
        prev = weeks[i - 1]
        corr = corrections.get(str(prev["suggestion_id"]))
        if corr and corr.get("final_snapshot_json"):
            rh, rl = _rh_rl_from_snapshot(corr["final_snapshot_json"])
            if rh is not None and rl is not None:
                chain[week] = (rh, rl)
    return chain


def _replay_week(candles, row, promoted_chain: dict[str, tuple[float, float]]) -> dict:
    ctx, _ = replay_context_for_week(all_candles=candles, row=row)
    promoted = promoted_chain.get(row.week)
    if promoted:
        rh, rl = promoted
        seed = RangeSeedContext(
            range_high=rh,
            range_low=rl,
            seed_source=SEED_SOURCE_PROMOTED_RANGE,
        )
        ctx.range_seed = seed
        ctx.range_high = rh
        ctx.range_low = rl
        ctx.range_seed_meta = {
            "seed_source": SEED_SOURCE_PROMOTED_RANGE,
            "seed_rh": rh,
            "seed_rl": rl,
            "seed_policy": "reviewed_truth_only",
        }
    if row.meta_json.get("date_from_ms"):
        ctx.detection_window_meta["min_reclaim_time_ms"] = row.meta_json["date_from_ms"]
    ctx.detection_window_meta["max_reclaim_lag_bars"] = SCAN_MAX_RECLAIM_LAG_BARS
    ctx.detection_window_meta["seed_policy"] = "reviewed_truth_only"

    result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
    range_draft = range_candidate_from_result(result)
    no_valid = next((d for d in result.drafts if d.candidate_kind == "NO_VALID_RANGE"), None)
    draft = range_draft or no_valid
    meta = dict((draft.meta_json if draft else {}) or {})

    return {
        "week": row.week,
        "emitted": range_draft is not None,
        "kind": range_draft.candidate_kind if range_draft else "NO_VALID_RANGE",
        "reason": (no_valid.reason_text if no_valid and not range_draft else None),
        "rh": range_draft.suggested_rh if range_draft else None,
        "rl": range_draft.suggested_rl if range_draft else None,
        "discovery_source": meta.get("discovery_source"),
        "stale_context_rejected": meta.get("stale_context_rejected"),
        "local_discovery_attempted": meta.get("local_discovery_attempted"),
        "local_discovery_result": meta.get("local_discovery_result"),
        "context_seed_source": meta.get("context_seed_source"),
        "had_promoted_seed": promoted is not None,
        "baseline_had_candidate": row.detector_rh is not None,
    }


def main() -> None:
    candles = _load_candles()
    if candles is None:
        OUT_PATH.write_text(
            "# Discovery vs persistence report\n\n"
            "**Status:** SKIPPED — local W1 candle DB not found.\n",
            encoding="utf-8",
        )
        print(f"SKIP: no candles — wrote stub to {OUT_PATH}")
        return

    baseline = load_audit_fixture(BASELINE_PATH)
    rows = build_gold_rows(baseline)
    promoted_chain = _promoted_chain(baseline)
    baseline_weeks = {r.week for r in rows if r.detector_rh is not None}

    results = [_replay_week(candles, row, promoted_chain) for row in rows]
    emitted_weeks = {r["week"] for r in results if r["emitted"]}

    recovered = sorted(baseline_weeks - emitted_weeks)  # weeks baseline had but we don't - wrong direction
    # recovered = baseline weeks that were lost in leg run but now emit
    leg_lost = {
        "2025-01-26",
        "2025-02-09",
        "2025-02-16",
        "2025-03-02",
        "2025-03-09",
        "2025-06-08",
        "2025-06-15",
        "2025-06-29",
        "2025-07-06",
        "2025-07-13",
    }
    recovered_from_leg_loss = sorted(w for w in leg_lost if w in emitted_weeks)
    still_missing = sorted(w for w in baseline_weeks if w not in emitted_weeks)

    stale_results = [r for r in results if r["week"] in STALE_WEEKS]
    stale_blocked = all(
        r.get("discovery_source") != DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE
        for r in stale_results
        if r["had_promoted_seed"]
    )
    jun_jul_recovered = [r["week"] for r in stale_results if r["emitted"]]

    lines = [
        "# Discovery vs persistence report",
        "",
        "Split implementation: `PROMOTED_RANGE` supplies persistence context; "
        "week-local BOS→reclaim discovery emits when promoted lifecycle is stale.",
        "",
        "## Summary",
        "",
        f"- Baseline audit weeks with candidates: **{len(baseline_weeks)}**",
        f"- Weeks emitting RANGE after split: **{len(emitted_weeks)}**",
        f"- Recovered from prior leg+reviewed-truth loss set: **{len(recovered_from_leg_loss)}** / 10",
        f"- Still missing vs baseline: **{len(still_missing)}**",
        f"- Stale promoted cycles blocked from direct emit: **{'yes' if stale_blocked else 'no'}**",
        f"- Jun–Jul stale cluster local recovery: **{len(jun_jul_recovered)}** / {len(STALE_WEEKS)}",
        "",
    ]

    if recovered_from_leg_loss:
        lines.append("### Recovered weeks")
        lines.append("")
        for w in recovered_from_leg_loss:
            r = next(x for x in results if x["week"] == w)
            lines.append(
                f"- `{w}` — `{r['discovery_source']}` "
                f"(local_discovery={r.get('local_discovery_result')})"
            )
        lines.append("")

    lines.extend(["### Still missing weeks", ""])
    if still_missing:
        for w in still_missing:
            r = next(x for x in results if x["week"] == w)
            reason = r.get("reason") or r.get("local_discovery_result") or "no RANGE_CANDIDATE"
            lines.append(f"- `{w}` — {reason}")
    else:
        lines.append("- None")
    lines.append("")

    lines.extend(["## Stale-week detail (Jun–Jul cluster)", ""])
    lines.append(
        "| Week | Emitted | discovery_source | stale_rejected | local_result |"
    )
    lines.append("|------|---------|------------------|----------------|--------------|")
    for r in stale_results:
        lines.append(
            f"| {r['week']} | {'yes' if r['emitted'] else 'no'} | "
            f"{r.get('discovery_source') or '—'} | "
            f"{r.get('stale_context_rejected')} | "
            f"{r.get('local_discovery_result') or r.get('reason') or '—'} |"
        )
    lines.append("")

    lines.extend(["## Discovery source counts", ""])
    from collections import Counter

    src_counts = Counter(r.get("discovery_source") or "—" for r in results if r["emitted"])
    for src, count in sorted(src_counts.items()):
        lines.append(f"- `{src}`: {count}")
    lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Emitted: {len(emitted_weeks)}/{len(rows)}")
    print(f"Jun-Jul recovered: {jun_jul_recovered}")


if __name__ == "__main__":
    main()
