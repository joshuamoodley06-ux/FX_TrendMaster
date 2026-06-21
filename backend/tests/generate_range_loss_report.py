"""Generate 2025 W1 range loss report: baseline 4750e5ac vs leg-doctrine bd1500c3."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.pipeline import run_detector_v1
from detector.range_state import RangeSeedContext
from tests.detector_audit_fixture import (
    build_gold_rows,
    load_audit_fixture,
    range_candidate_from_result,
    replay_context_for_week,
    _rh_rl_from_snapshot,
)

BASELINE_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "detector_audit_4750e5ac.json"
LEG_PATH = Path.home() / "Downloads" / "detection_audit_XAUUSD_2025_bd1500c3.json"
LEG_FIXTURE_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "detector_audit_bd1500c3.json"
OUT_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / "2025_w1_range_loss_report.md"
DB_CANDIDATES = [
    Path.home() / "Documents" / "FXTM_Research" / "raw_mapping_v159.db",
    BACKEND_DIR / "data" / "raw_mapping_v159.db",
]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _index_by_replay(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in audit.get("suggestions") or []:
        week = str(s.get("replay_until_time") or "")
        if week:
            out[week] = s
    return out


def _load_candles() -> list[dict[str, Any]] | None:
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


def _promoted_seed_chain(baseline: dict[str, Any]) -> dict[str, tuple[float, float, str]]:
    """Prior-week Josh final snapshots → seed for next replay week."""
    corrections = {c["suggestion_id"]: c for c in baseline.get("corrections") or []}
    weeks = sorted(baseline.get("suggestions") or [], key=lambda s: int(s["replay_until_time_ms"]))
    chain: dict[str, tuple[float, float, str]] = {}
    for i, suggestion in enumerate(weeks):
        if i == 0:
            continue
        week = str(suggestion["replay_until_time"])
        prev = weeks[i - 1]
        corr = corrections.get(str(prev["suggestion_id"]))
        if not corr or not corr.get("final_snapshot_json"):
            continue
        rh, rl = _rh_rl_from_snapshot(corr["final_snapshot_json"])
        if rh is not None and rl is not None:
            chain[week] = (rh, rl, "PROMOTED_RANGE")
    return chain


def _bos_state(meta: dict[str, Any]) -> str:
    if meta.get("bos_time"):
        broken = meta.get("broken_boundary") or "—"
        return f"BOS {broken} @ {meta['bos_time']}"
    if meta.get("broken_boundary"):
        return f"broken_boundary={meta['broken_boundary']}"
    return "none"


def _reclaim_state(meta: dict[str, Any]) -> str:
    conf = meta.get("reclaim_confirmation")
    rt = meta.get("reclaim_time")
    if conf or rt:
        return f"{conf or '—'} @ {rt or meta.get('reclaim_time_ms') or '—'}"
    lifecycle = meta.get("lifecycle_state")
    if lifecycle in {"BREACHED_UP", "BREACHED_DOWN"}:
        return "reclaim not confirmed"
    return "none"


def _replay_leg_doctrine(
    candles: list[dict[str, Any]],
    row,
    promoted_chain: dict[str, tuple[float, float, str]],
) -> dict[str, Any]:
    ctx, _ = replay_context_for_week(all_candles=candles, row=row)
    seed_src = "bootstrap_candidate"
    if row.week in promoted_chain:
        rh, rl, seed_src = promoted_chain[row.week]
        seed = RangeSeedContext(range_high=rh, range_low=rl, seed_source=seed_src)
        ctx.range_seed = seed
        ctx.range_high = rh
        ctx.range_low = rl
        ctx.range_seed_meta = {
            "seed_source": seed_src,
            "seed_rh": rh,
            "seed_rl": rl,
            "seed_policy": "reviewed_truth_only",
        }
    else:
        seed_src = "bootstrap_candidate (no prior promoted truth)"

    result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
    range_draft = range_candidate_from_result(result)
    no_valid = next((d for d in result.drafts if d.candidate_kind == "NO_VALID_RANGE"), None)
    draft = range_draft or no_valid
    meta = dict((draft.meta_json if draft else {}) or {})
    boundary_reached = bool(
        meta.get("htf_leg_trace") or meta.get("boundary_candidates_considered")
    )

    if range_draft is not None:
        rejection = (
            "Historical scan did not persist RANGE_CANDIDATE at this replay week "
            "(isolated leg replay would emit a candidate)"
        )
    elif no_valid is not None:
        rejection = str(no_valid.reason_text or "NO_VALID_RANGE")
    else:
        rejection = "no RANGE_CANDIDATE draft"

    return {
        "rejection_reason": rejection,
        "lifecycle_state": meta.get("lifecycle_state") or "—",
        "bos_state": _bos_state(meta),
        "reclaim_state": _reclaim_state(meta),
        "seed_source": seed_src,
        "boundary_stage_reached": boundary_reached,
        "isolated_candidate": range_draft is not None,
    }


def _classify_loss(reason: str) -> str:
    if "did not persist" in reason or "did not write" in reason:
        return "scan_step_skipped_despite_isolated_candidate"
    if "Reclaim cycle completed before active replay week" in reason:
        return "reclaim_cycle_stale_before_active_week"
    if "reclaim not yet confirmed" in reason.lower() or "BOS detected" in reason:
        return "bos_without_confirmed_reclaim"
    if "no leg boundary candidates" in reason.lower():
        return "boundary_selection_failed"
    if "Opposite BOS" in reason:
        return "opposite_bos_before_reclaim"
    return reason[:72]


def generate_report() -> str:
    baseline = _load_json(BASELINE_PATH)
    if not LEG_PATH.is_file():
        raise FileNotFoundError(f"Leg-doctrine audit not found: {LEG_PATH}")
    leg = _load_json(LEG_PATH)
    LEG_FIXTURE_PATH.write_text(json.dumps(leg, indent=2), encoding="utf-8")

    leg_by_week = _index_by_replay(leg)
    rows = build_gold_rows(baseline)
    corrections = {c["suggestion_id"]: c for c in baseline.get("corrections") or []}
    promoted_chain = _promoted_seed_chain(baseline)
    candles = _load_candles()

    entries: list[dict[str, Any]] = []
    for row in rows:
        week = row.week
        baseline_s = next(s for s in baseline["suggestions"] if s["replay_until_time"] == week)
        corr = corrections.get(row.suggestion_id, {})
        leg_s = leg_by_week.get(week)
        present = leg_s is not None

        entry: dict[str, Any] = {
            "week": week,
            "present": present,
            "baseline_rh": baseline_s.get("rh"),
            "baseline_rl": baseline_s.get("rl"),
            "baseline_lifecycle": baseline_s.get("lifecycle_state"),
            "baseline_seed": (baseline_s.get("meta_json") or {}).get("seed_source"),
            "baseline_boundary": baseline_s.get("boundary_selection_reason"),
            "audit_action": corr.get("user_action"),
            "rejection_reason": "—",
            "lifecycle_state": "—",
            "bos_state": "—",
            "reclaim_state": "—",
            "seed_source": "—",
            "boundary_stage_reached": "—",
            "leg_rh": None,
            "leg_rl": None,
            "leg_boundary": None,
        }

        if present and leg_s:
            entry["leg_rh"] = leg_s.get("rh")
            entry["leg_rl"] = leg_s.get("rl")
            lm = leg_s.get("meta_json") or {}
            entry["leg_boundary"] = leg_s.get("boundary_selection_reason") or lm.get("boundary_selection_reason")
            entry["lifecycle_state"] = leg_s.get("lifecycle_state") or lm.get("lifecycle_state")
            entry["bos_state"] = _bos_state(lm)
            entry["reclaim_state"] = _reclaim_state(lm)
            entry["seed_source"] = lm.get("seed_source") or "—"
            entry["boundary_stage_reached"] = bool(lm.get("htf_leg_trace") or lm.get("boundary_candidates_considered"))
        elif candles is not None:
            diag = _replay_leg_doctrine(candles, row, promoted_chain)
            entry.update(diag)

        entries.append(entry)

    retained = [e for e in entries if e["present"]]
    lost = [e for e in entries if not e["present"]]
    loss_reasons = Counter(_classify_loss(str(e["rejection_reason"])) for e in lost)
    dominant = loss_reasons.most_common(1)[0][0] if loss_reasons else "—"
    leg_only_weeks = sorted(set(leg_by_week) - {r.week for r in rows})

    lines = [
        "# 2025 W1 Range Loss Report",
        "",
        "Compares baseline historical scan **4750e5ac** (pre-leg boundary, in-scan seed roll) "
        "against latest leg-doctrine scan **bd1500c3** (`reviewed_truth_only`, `PROMOTED_RANGE` seeds, leg boundaries).",
        "",
        "## Run metadata",
        "",
        "| | Baseline | Leg doctrine |",
        "|--|----------|--------------|",
        f"| Run ID | `{baseline['detection_run_id']}` | `{leg['detection_run_id']}` |",
        f"| RANGE_CANDIDATE rows | {baseline['counts']['suggestions_in_run']} | {leg['counts']['suggestions_in_run']} |",
        f"| Boundary doctrine | `LAST_OPPOSITE_SWING_BEFORE_BOS` | `STRUCTURAL_SWING_*` + `htf_leg_trace` |",
        f"| Seed policy | `bootstrap_candidate` / `previous_range_candidate` | `reviewed_truth_only` → `PROMOTED_RANGE` |",
        f"| Diagnostics replay | {'local W1 candles (' + str(len(candles)) + ' bars)' if candles else 'unavailable'} | audit export |",
        "",
        "## Summary",
        "",
        f"- **Baseline weeks reviewed:** {len(entries)}",
        f"- **Ranges retained** (RANGE_CANDIDATE at same `replay_until`): **{len(retained)} / {len(entries)}**",
        f"- **Ranges lost:** **{len(lost)} / {len(entries)}**",
        f"- **New-only weeks in leg run:** {len(leg_only_weeks)} — {', '.join(leg_only_weeks) or '—'}",
        f"- **Dominant loss reason:** `{dominant}`",
        "",
        "### Loss reason histogram",
        "",
    ]
    for reason, count in loss_reasons.most_common():
        lines.append(f"- `{reason}`: **{count}**")

    lines.extend(["", "## Per-week comparison", ""])
    lines.append(
        "| Week | Present? | Baseline RH/RL | Leg RH/RL | Baseline seed | Leg / replay seed | "
        "Rejection (if lost) | Lifecycle | BOS | Reclaim | Boundary stage? |"
    )
    lines.append(
        "|------|----------|----------------|-----------|---------------|-------------------|"
        "---------------------|-----------|-----|---------|-----------------|"
    )
    for e in entries:
        pres = "YES" if e["present"] else "**NO**"
        base_rng = f"{e['baseline_rh']}/{e['baseline_rl']}"
        leg_rng = f"{e['leg_rh']}/{e['leg_rl']}" if e["present"] else "—"
        rej = str(e["rejection_reason"]).replace("|", "\\|")
        if len(rej) > 90:
            rej = rej[:87] + "..."
        bnd = (
            "YES"
            if e["boundary_stage_reached"] is True
            else ("NO" if e["boundary_stage_reached"] is False else str(e["boundary_stage_reached"]))
        )
        lines.append(
            f"| {e['week']} | {pres} | {base_rng} | {leg_rng} | {e['baseline_seed']} | {e['seed_source']} | "
            f"{rej} | {e['lifecycle_state']} | {e['bos_state']} | {e['reclaim_state']} | {bnd} |"
        )

    lines.extend(["", "## Retained weeks", ""])
    for e in retained:
        lines.append(
            f"- **{e['week']}** — baseline {e['baseline_rh']}/{e['baseline_rl']} → "
            f"leg {e['leg_rh']}/{e['leg_rl']} · seed `{e['seed_source']}` · boundary `{e['leg_boundary']}`"
        )

    lines.extend(["", "## Lost weeks — detail", ""])
    for e in lost:
        lines.append(f"### {e['week']} (baseline {e['audit_action']})")
        lines.append("")
        lines.append("- **Present in leg run:** NO")
        lines.append(
            f"- **Baseline:** RH/RL {e['baseline_rh']}/{e['baseline_rl']} · "
            f"`{e['baseline_boundary']}` · seed `{e['baseline_seed']}` · lifecycle `{e['baseline_lifecycle']}`"
        )
        lines.append(f"- **Rejection reason:** {e['rejection_reason']}")
        lines.append(f"- **Lifecycle state (leg replay):** {e['lifecycle_state']}")
        lines.append(f"- **BOS state:** {e['bos_state']}")
        lines.append(f"- **Reclaim state:** {e['reclaim_state']}")
        lines.append(f"- **Seed source:** {e['seed_source']}")
        bnd = "YES" if e["boundary_stage_reached"] is True else "NO"
        lines.append(f"- **Boundary stage reached:** {bnd}")
        lines.append("")

    lines.extend(
        [
            "## Why ranges were lost",
            "",
            "1. **Reclaim freshness gate (dominant)** — With `PROMOTED_RANGE` seeds, many baseline weeks "
            "hit `Reclaim cycle completed before active replay week`. The BOS→reclaim cycle tied to promoted "
            "truth finished on an earlier bar, so the walk does not emit a new RANGE_CANDIDATE at the baseline replay week.",
            "2. **Scan cadence vs isolated replay** — Week **2025-01-12** still produces a candidate in isolated "
            "leg replay (bootstrap seed) but bd1500c3's first written candidate is **2025-01-19** (promoted seed from range 15).",
            "3. **Boundary failures** — **2025-07-20** and **2025-12-07**: reclaim confirmed but "
            "`Reclaim confirmed; no leg boundary candidates` (boundary stage **NO**).",
            "4. **Open BOS** — **2025-07-27** and **2025-08-10**: `BOS detected; reclaim not yet confirmed` under promoted seeds.",
            "5. **Trade-off** — Leg run adds **2025-10-12** and **2025-10-19** (not in baseline) while dropping eight Jun–Aug baseline weeks.",
            "",
            "## Notes",
            "",
            "- Baseline fixture: `docs/fixtures/detector_audit_4750e5ac.json`",
            "- Leg audit: `docs/fixtures/detector_audit_bd1500c3.json`",
            "- Match key: `replay_until_time` (same W1 bar close).",
            "- Lost-week diagnostics: leg-doctrine isolated replay with promoted seeds from prior-week Josh `final_snapshot_json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    report = generate_report()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
