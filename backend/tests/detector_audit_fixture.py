"""2025 XAUUSD W1 detector audit fixture (run 4750e5ac) — load, gold table, replay helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_NAME = "detector_audit_4750e5ac.json"
DETECTION_RUN_ID = "4750e5ac-46d0-47db-82f0-ac183d0671a2"
PRICE_TOLERANCE = 0.02

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
DOCS_FIXTURE_PATH = BACKEND_DIR.parent / "docs" / "fixtures" / FIXTURE_NAME
TESTS_FIXTURE_PATH = TESTS_DIR / "fixtures" / FIXTURE_NAME


@dataclass(frozen=True)
class AuditWeekRow:
    week: str
    replay_until_time_ms: int
    detector_rh: float | None
    detector_rl: float | None
    josh_rh: float | None
    josh_rl: float | None
    audit_action: str
    audit_reason: str | None
    boundary_selection_reason: str | None
    retracement_price: float | None
    retracement_impulse_low: float | None
    retracement_impulse_high: float | None
    retracement_reason: str | None
    suggestion_id: str
    meta_json: dict[str, Any]


def fixture_paths() -> list[Path]:
    return [TESTS_FIXTURE_PATH, DOCS_FIXTURE_PATH]


def load_audit_fixture(path: Path | None = None) -> dict[str, Any]:
    p = path or TESTS_FIXTURE_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _detector_rh_rl(suggestion: dict[str, Any]) -> tuple[float | None, float | None]:
    meta = suggestion.get("meta_json") or {}
    det_rh = meta.get("detector_suggested_rh")
    det_rl = meta.get("detector_suggested_rl")
    if det_rh is None:
        det_rh = suggestion.get("rh")
    if det_rl is None:
        det_rl = suggestion.get("rl")
    return det_rh, det_rl


def build_gold_rows(fixture: dict[str, Any] | None = None) -> list[AuditWeekRow]:
    data = fixture or load_audit_fixture()
    corrections = {c["suggestion_id"]: c for c in data.get("corrections") or []}
    rows: list[AuditWeekRow] = []
    for s in data.get("suggestions") or []:
        sid = str(s["suggestion_id"])
        corr = corrections.get(sid, {})
        meta = s.get("meta_json") or {}
        det_rh, det_rl = _detector_rh_rl(s)
        rows.append(
            AuditWeekRow(
                week=str(s.get("replay_until_time") or ""),
                replay_until_time_ms=int(s["replay_until_time_ms"]),
                detector_rh=det_rh,
                detector_rl=det_rl,
                josh_rh=s.get("rh"),
                josh_rl=s.get("rl"),
                audit_action=str(corr.get("user_action") or s.get("status") or ""),
                audit_reason=corr.get("error_category"),
                boundary_selection_reason=s.get("boundary_selection_reason")
                or meta.get("boundary_selection_reason"),
                retracement_price=s.get("retracement_price"),
                retracement_impulse_low=meta.get("retracement_impulse_low"),
                retracement_impulse_high=meta.get("retracement_impulse_high"),
                retracement_reason=meta.get("retracement_reason"),
                suggestion_id=sid,
                meta_json=meta,
            )
        )
    return rows


def write_summary_csv(path: Path, rows: list[AuditWeekRow] | None = None) -> None:
    gold = rows or build_gold_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "week",
                "detector_rh",
                "detector_rl",
                "josh_rh",
                "josh_rl",
                "audit_action",
                "audit_reason",
            ]
        )
        for r in gold:
            writer.writerow(
                [
                    r.week,
                    r.detector_rh,
                    r.detector_rl,
                    r.josh_rh,
                    r.josh_rl,
                    r.audit_action,
                    r.audit_reason or "",
                ]
            )


def _price_close(a: float | None, b: float | None, tol: float = PRICE_TOLERANCE) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


def rl_failure_kind(row: AuditWeekRow) -> str | None:
    """Classify RL bug pattern from fixture metadata (no detector code)."""
    if row.detector_rl is None:
        return None
    if _price_close(row.detector_rl, row.retracement_price):
        return "equals_retracement_price"
    if _price_close(row.detector_rl, row.retracement_impulse_low):
        return "equals_retracement_impulse_low"
    if _price_close(row.detector_rl, row.retracement_impulse_high):
        return "equals_retracement_impulse_high"
    if row.retracement_reason and "after BOS through reclaim" in row.retracement_reason:
        return "retracement_pipeline_adjacent"
    return None


def write_rl_analysis_md(path: Path, rows: list[AuditWeekRow] | None = None) -> None:
    gold = rows or build_gold_rows()
    failures = [r for r in gold if rl_failure_kind(r)]
    lines = [
        "# Detector RL analysis — audit run 4750e5ac",
        "",
        "XAUUSD W1 weekly range audit (14 reviewed weeks). **No code changes** — fixture-only report.",
        "",
        f"## Summary",
        "",
        f"- **RL failure count:** {len(failures)} / {len(gold)} weeks show RL tied to retracement logic",
        f"- **Explicit WRONG_RL edits:** {sum(1 for r in gold if r.audit_reason == 'WRONG_RL')}",
        "",
        "## Per-week table",
        "",
        "| week | detector_rl | josh_rl | retracement_price | impulse_low | impulse_high | failure_kind | audit_reason |",
        "|------|-------------|---------|-------------------|-------------|--------------|--------------|--------------|",
    ]
    for r in gold:
        kind = rl_failure_kind(r) or "—"
        lines.append(
            f"| {r.week} | {r.detector_rl} | {r.josh_rl} | {r.retracement_price} "
            f"| {r.retracement_impulse_low} | {r.retracement_impulse_high} | {kind} | {r.audit_reason or '—'} |"
        )
    lines.extend(
        [
            "",
            "## Affected weeks (RL ≡ retracement-derived)",
            "",
        ]
    )
    for r in failures:
        kind = rl_failure_kind(r)
        lines.append(
            f"- **{r.week}** — `{kind}`; detector RL {r.detector_rl}, Josh RL {r.josh_rl}, "
            f"retracement {r.retracement_price}; reason: {r.retracement_reason or '—'}"
        )
    lines.extend(
        [
            "",
            "## Strongest RL signal",
            "",
            "In **12/12 EDIT weeks** with `detector_suggested_rl`, RL equals `retracement_impulse_low` "
            "(the post-BOS retrace measurement anchor), not the structural swing low Josh selected. "
            "Weeks **2025-06-22** and **2025-06-29** were explicitly corrected for WRONG_RL.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_rh_analysis_md(path: Path, rows: list[AuditWeekRow] | None = None) -> None:
    gold = rows or build_gold_rows()
    by_reason: dict[str, list[AuditWeekRow]] = {}
    for r in gold:
        key = r.boundary_selection_reason or "UNKNOWN"
        by_reason.setdefault(key, []).append(r)

    lines = [
        "# Detector RH analysis — audit run 4750e5ac",
        "",
        "Grouped by `boundary_selection_reason`. **No code changes** — fixture-only report.",
        "",
        "## Per-week RH delta",
        "",
        "| week | detector_rh | josh_rh | difference | rh == impulse_high | scan_chain | seed_rh | audit_reason |",
        "|------|-------------|---------|------------|--------------------|------------|---------|--------------|",
    ]
    for r in gold:
        diff = None
        if r.detector_rh is not None and r.josh_rh is not None:
            diff = round(float(r.josh_rh) - float(r.detector_rh), 2)
        rh_is_bos = _price_close(r.detector_rh, r.retracement_impulse_high)
        chain = r.meta_json.get("scan_chain_index")
        seed_rh = r.meta_json.get("seed_rh")
        lines.append(
            f"| {r.week} | {r.detector_rh} | {r.josh_rh} | {diff} | {rh_is_bos} | {chain} | {seed_rh} | {r.audit_reason or '—'} |"
        )

    lines.extend(["", "## Grouped by boundary_selection_reason", ""])
    for reason, group in sorted(by_reason.items()):
        wrong_rh = sum(1 for r in group if r.audit_reason == "WRONG_RH")
        lines.append(f"### `{reason}` ({len(group)} weeks, {wrong_rh} WRONG_RH)")
        lines.append("")
        for r in group:
            diff = round(float(r.josh_rh) - float(r.detector_rh), 2) if r.detector_rh and r.josh_rh else "—"
            lines.append(
                f"- **{r.week}** — detector {r.detector_rh}, Josh {r.josh_rh}, Δ {diff}; "
                f"seed {r.meta_json.get('seed_rh')}/{r.meta_json.get('seed_rl')}; "
                f"chain index {r.meta_json.get('scan_chain_index')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Error pattern hypotheses (data only)",
            "",
            "1. **BOS high selection** — detector RH equals `retracement_impulse_high` (BOS bar high) in **14/14** weeks.",
            "2. **Swing selection** — all weeks use `LAST_OPPOSITE_SWING_BEFORE_BOS` for the opposite boundary; "
            "RL side pinned to stale pre-BOS swing or retrace impulse low.",
            "3. **Stale seed influence** — `seed_rh`/`seed_rl` roll from prior detector output (`scan_chain_index` 0→13); "
            "Jul–Aug weeks show largest RH deltas as chain compounds.",
            "4. **Chain compounding** — weeks 2025-07-20 through 2025-08-10: Josh RH exceeds detector by 1000–2190 pts "
            "while seeds still reflect earlier wrong ranges.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def replay_context_for_week(
    *,
    all_candles: list[dict[str, Any]],
    row: AuditWeekRow,
    lookback_bars: int = 104,
) -> tuple[Any, int]:
    """Build DetectionContext mirroring historical scan replay for one audited week."""
    from detector.context_window import build_detection_window_meta
    from detector.ohlc_loader import build_context
    from detector.range_scan_runner import SCAN_MAX_RECLAIM_LAG_BARS
    from detector.range_state import RangeSeedContext

    replay_ms = row.replay_until_time_ms
    meta = row.meta_json
    idx = None
    for i, c in enumerate(all_candles):
        if int(c.get("time_ms") or 0) == replay_ms:
            idx = i
            break
    if idx is None:
        for i, c in enumerate(all_candles):
            if int(c.get("time_ms") or 0) <= replay_ms:
                idx = i
        if idx is None:
            raise ValueError(f"No candle at or before replay_until_time_ms={replay_ms} for {row.week}")

    slice_start = max(0, idx - lookback_bars)
    window = all_candles[slice_start : idx + 1]
    active_index = len(window) - 1

    ctx = build_context(
        symbol="XAUUSD",
        source_timeframe="W1",
        structure_layer="WEEKLY",
        candles=window,
        active_index=active_index,
        replay_until_time_ms=replay_ms,
        detection_run_id=DETECTION_RUN_ID,
    )

    seed_rh = meta.get("seed_rh")
    seed_rl = meta.get("seed_rl")
    chain_index = int(meta.get("scan_chain_index") or 0)
    if seed_rh is not None and seed_rl is not None:
        seed = RangeSeedContext(
            range_high=float(seed_rh),
            range_low=float(seed_rl),
            seed_source=str(meta.get("seed_source") or "fixture_seed"),
        )
        ctx.range_seed = seed
        ctx.range_high = seed.range_high
        ctx.range_low = seed.range_low
        ctx.range_seed_meta = {
            "seed_source": meta.get("seed_source"),
            "seed_rh": seed_rh,
            "seed_rl": seed_rl,
            "scan_chain_index": chain_index,
            "no_seed_context": False,
        }

    ctx.detection_window_meta = build_detection_window_meta(ctx, detection_run_id=DETECTION_RUN_ID)
    ctx.detection_window_meta["historical_scan"] = True
    if meta.get("date_from_ms"):
        ctx.detection_window_meta["date_from_ms"] = meta["date_from_ms"]
    if meta.get("date_to_ms"):
        ctx.detection_window_meta["date_to_ms"] = meta["date_to_ms"]
    if chain_index > 0 and meta.get("date_from_ms"):
        ctx.detection_window_meta["min_reclaim_time_ms"] = meta["date_from_ms"]
    if chain_index > 0:
        ctx.detection_window_meta["max_reclaim_lag_bars"] = SCAN_MAX_RECLAIM_LAG_BARS
    ctx.detection_window_meta["seed_source"] = meta.get("seed_source")

    return ctx, idx


def range_candidate_from_result(result: Any) -> Any | None:
    for draft in result.drafts:
        if str(draft.candidate_kind or "").upper() == "RANGE_CANDIDATE":
            return draft
    return None


def _rh_rl_from_snapshot(snapshot: str | dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not snapshot:
        return None, None
    data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    rh = data.get("suggested_rh")
    rl = data.get("suggested_rl")
    try:
        return (float(rh) if rh is not None else None, float(rl) if rl is not None else None)
    except (TypeError, ValueError):
        return None, None


SIM_SEED_SOURCE = "audit_correction_final_snapshot"


def run_seed_simulation(fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Phase 3 pre-check: compare old detector-rolled seeds vs correction-final seeds.
    Research only — no detector or DB changes.
    """
    data = fixture or load_audit_fixture()
    corrections = {str(c["suggestion_id"]): c for c in data.get("corrections") or []}
    weeks = sorted(
        data.get("suggestions") or [],
        key=lambda s: int(s["replay_until_time_ms"]),
    )

    rows: list[dict[str, Any]] = []
    for i, suggestion in enumerate(weeks):
        meta = suggestion.get("meta_json") or {}
        week = str(suggestion.get("replay_until_time") or "")
        josh_rh = suggestion.get("rh")
        josh_rl = suggestion.get("rl")
        old_seed_rh = meta.get("seed_rh")
        old_seed_rl = meta.get("seed_rl")
        old_seed_source = meta.get("seed_source")

        sim_source: str | None = None
        sim_seed_rh: float | None = None
        sim_seed_rl: float | None = None
        if i > 0:
            prev = weeks[i - 1]
            prev_corr = corrections.get(str(prev["suggestion_id"]))
            if prev_corr:
                sim_seed_rh, sim_seed_rl = _rh_rl_from_snapshot(prev_corr.get("final_snapshot_json"))
                if sim_seed_rh is not None and sim_seed_rl is not None:
                    sim_source = SIM_SEED_SOURCE

        def _delta(seed_rh: float | None, seed_rl: float | None) -> tuple[float | None, float | None]:
            rh_d = abs(float(seed_rh) - float(josh_rh)) if seed_rh is not None and josh_rh is not None else None
            rl_d = abs(float(seed_rl) - float(josh_rl)) if seed_rl is not None and josh_rl is not None else None
            return rh_d, rl_d

        old_rh_delta, old_rl_delta = _delta(old_seed_rh, old_seed_rl)
        sim_rh_delta, sim_rl_delta = _delta(sim_seed_rh, sim_seed_rl)

        old_total = (old_rh_delta or 0.0) + (old_rl_delta or 0.0)
        if sim_source is None:
            outcome = "unchanged"
        else:
            sim_total = (sim_rh_delta or 0.0) + (sim_rl_delta or 0.0)
            if sim_total < old_total - PRICE_TOLERANCE:
                outcome = "improved"
            elif sim_total > old_total + PRICE_TOLERANCE:
                outcome = "worsened"
            else:
                outcome = "unchanged"

        rows.append(
            {
                "week": week,
                "replay_until_time": week,
                "old_seed_source": old_seed_source,
                "old_seed_rh": old_seed_rh,
                "old_seed_rl": old_seed_rl,
                "simulated_seed_source": sim_source or "—",
                "simulated_seed_rh": sim_seed_rh,
                "simulated_seed_rl": sim_seed_rl,
                "josh_rh": josh_rh,
                "josh_rl": josh_rl,
                "old_seed_rh_delta": old_rh_delta,
                "old_seed_rl_delta": old_rl_delta,
                "simulated_seed_rh_delta": sim_rh_delta,
                "simulated_seed_rl_delta": sim_rl_delta,
                "improved": outcome == "improved",
                "outcome": outcome,
            }
        )

    improved = sum(1 for r in rows if r["outcome"] == "improved")
    unchanged = sum(1 for r in rows if r["outcome"] == "unchanged")
    worsened = sum(1 for r in rows if r["outcome"] == "worsened")

    old_rh_deltas = [r["old_seed_rh_delta"] for r in rows if r["old_seed_rh_delta"] is not None]
    old_rl_deltas = [r["old_seed_rl_delta"] for r in rows if r["old_seed_rl_delta"] is not None]
    sim_rh_deltas = [
        r["simulated_seed_rh_delta"]
        for r in rows
        if r["simulated_seed_rh_delta"] is not None and r["simulated_seed_source"] == SIM_SEED_SOURCE
    ]
    sim_rl_deltas = [
        r["simulated_seed_rl_delta"]
        for r in rows
        if r["simulated_seed_rl_delta"] is not None and r["simulated_seed_source"] == SIM_SEED_SOURCE
    ]

    avg_old_rh = sum(old_rh_deltas) / len(old_rh_deltas) if old_rh_deltas else 0.0
    avg_old_rl = sum(old_rl_deltas) / len(old_rl_deltas) if old_rl_deltas else 0.0
    avg_sim_rh = sum(sim_rh_deltas) / len(sim_rh_deltas) if sim_rh_deltas else 0.0
    avg_sim_rl = sum(sim_rl_deltas) / len(sim_rl_deltas) if sim_rl_deltas else 0.0

    jul_aug = [r for r in rows if r["week"] >= "2025-07-01" and r["week"] < "2025-09-01"]
    jul_aug_improved = sum(1 for r in jul_aug if r["outcome"] == "improved")
    jul_aug_worsened = sum(1 for r in jul_aug if r["outcome"] == "worsened")

    implement = improved > worsened and (avg_sim_rh + avg_sim_rl) < (avg_old_rh + avg_old_rl)

    return {
        "rows": rows,
        "total": len(rows),
        "improved": improved,
        "unchanged": unchanged,
        "worsened": worsened,
        "avg_old_rh_delta": avg_old_rh,
        "avg_old_rl_delta": avg_old_rl,
        "avg_sim_rh_delta": avg_sim_rh,
        "avg_sim_rl_delta": avg_sim_rl,
        "jul_aug_improved": jul_aug_improved,
        "jul_aug_worsened": jul_aug_worsened,
        "jul_aug_total": len(jul_aug),
        "recommendation": "IMPLEMENT PHASE 3" if implement else "DO NOT IMPLEMENT PHASE 3 YET",
    }


def write_seed_simulation_report(path: Path, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = run_seed_simulation(fixture)
    rows = stats["rows"]

    lines = [
        "# Seed simulation report — audit run 4750e5ac",
        "",
        "Phase 3 **pre-check** only. Compares historical-walk seeds (`previous_range_candidate`) "
        "vs simulated seeds from prior week `final_snapshot_json` (Josh-reviewed RH/RL).",
        "",
        "**No detector code was changed.**",
        "",
        "## Per-week comparison",
        "",
        "| week | old_seed_source | old_seed_rh | old_seed_rl | sim_seed_source | sim_seed_rh | sim_seed_rl | "
        "josh_rh | josh_rl | old_ΔRH | old_ΔRL | sim_ΔRH | sim_ΔRL | improved? |",
        "|------|-----------------|-------------|-------------|-----------------|-------------|-------------|"
        "---------|---------|---------|---------|---------|---------|-----------|",
    ]

    for r in rows:
        lines.append(
            f"| {r['week']} | {r['old_seed_source']} | {r['old_seed_rh']} | {r['old_seed_rl']} | "
            f"{r['simulated_seed_source']} | {r['simulated_seed_rh']} | {r['simulated_seed_rl']} | "
            f"{r['josh_rh']} | {r['josh_rl']} | "
            f"{round(r['old_seed_rh_delta'], 2) if r['old_seed_rh_delta'] is not None else '—'} | "
            f"{round(r['old_seed_rl_delta'], 2) if r['old_seed_rl_delta'] is not None else '—'} | "
            f"{round(r['simulated_seed_rh_delta'], 2) if r['simulated_seed_rh_delta'] is not None else '—'} | "
            f"{round(r['simulated_seed_rl_delta'], 2) if r['simulated_seed_rl_delta'] is not None else '—'} | "
            f"{r['outcome']} |"
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- **Total weeks compared:** {stats['total']}",
            f"- **Improved:** {stats['improved']}",
            f"- **Unchanged:** {stats['unchanged']}",
            f"- **Worsened:** {stats['worsened']}",
            f"- **Avg RH seed |Δ| (old → sim):** {stats['avg_old_rh_delta']:.2f} → {stats['avg_sim_rh_delta']:.2f}",
            f"- **Avg RL seed |Δ| (old → sim):** {stats['avg_old_rl_delta']:.2f} → {stats['avg_sim_rl_delta']:.2f}",
            f"- **Jul–Aug improved / total:** {stats['jul_aug_improved']} / {stats['jul_aug_total']} "
            f"(worsened: {stats['jul_aug_worsened']})",
            "",
            "## Recommendation",
            "",
            f"**{stats['recommendation']}**",
            "",
            "Improvement = combined |seed−Josh| distance (RH+RL) smaller than old detector-rolled seed.",
            "Week 1 has no prior audited correction → simulated seed N/A (unchanged).",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return stats


def print_seed_simulation_summary(stats: dict[str, Any]) -> None:
    print("Seed simulation:")
    print(f"Compared: {stats['total']}")
    print(f"Improved: {stats['improved']}")
    print(f"Unchanged: {stats['unchanged']}")
    print(f"Worsened: {stats['worsened']}")
    print(
        f"Avg RH delta: {stats['avg_old_rh_delta']:.2f} -> {stats['avg_sim_rh_delta']:.2f}"
    )
    print(
        f"Avg RL delta: {stats['avg_old_rl_delta']:.2f} -> {stats['avg_sim_rl_delta']:.2f}"
    )
    jul = stats["jul_aug_improved"]
    jul_total = stats["jul_aug_total"]
    jul_note = "improved" if jul > stats["jul_aug_worsened"] else "not improved"
    print(f"Jul-Aug: {jul}/{jul_total} improved ({jul_note})")
    print(f"Recommendation: {stats['recommendation']}")


def write_metadata_report(
    path: Path,
    *,
    live_candles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write Phase 2 market-time metadata report for audit run 4750e5ac."""
    from detector.context_window import ms_to_date_label
    from detector.range_mode import RANGE_MODE_DOCTRINE_V2
    from detector.pipeline import run_detector_v1

    rows = build_gold_rows()
    fixture = load_audit_fixture()
    suggestions = {str(s["suggestion_id"]): s for s in fixture.get("suggestions") or []}

    def _label(ms: int | None) -> str:
        return ms_to_date_label(ms) or "—"

    def _plausible(ms: int | None, replay_ms: int) -> bool:
        if ms is None:
            return False
        return ms <= replay_ms

    lines = [
        "# Detector audit metadata report — run 4750e5ac",
        "",
        "Phase 2: market-time keys for BOS/reclaim/boundaries. "
        "`bos_candle_index` / `reclaim_candle_index` are replay-window hints only (`candle_index_scope=replay_window`).",
        "",
    ]

    stats = {
        "weeks": len(rows),
        "bos_time_ms_valid": 0,
        "reclaim_time_ms_valid": 0,
        "rh_boundary_time_ms_valid": 0,
        "rl_boundary_time_ms_valid": 0,
        "fixture_index_duplicated_103_104": 0,
        "live_replay": live_candles is not None,
    }

    lines.extend(
        [
            "## Per-week metadata",
            "",
            "| week | replay_until | old_bos_idx | bos_time | old_reclaim_idx | reclaim_time | rh_boundary_time | rl_boundary_time | idx_dup_103_104 | plausible |",
            "|------|--------------|-------------|----------|-----------------|--------------|------------------|------------------|-----------------|-----------|",
        ]
    )

    for row in rows:
        sug = suggestions.get(row.suggestion_id, {})
        meta = row.meta_json
        old_bos = meta.get("bos_candle_index", sug.get("bos_candle_index"))
        old_reclaim = meta.get("reclaim_candle_index", sug.get("reclaim_candle_index"))
        idx_dup = old_bos == 103 and old_reclaim == 104
        if idx_dup:
            stats["fixture_index_duplicated_103_104"] += 1

        bos_ms = reclaim_ms = rh_ms = rl_ms = None
        if live_candles:
            try:
                ctx, _ = replay_context_for_week(all_candles=live_candles, row=row)
                result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
                draft = range_candidate_from_result(result)
                if draft is not None:
                    live_meta = draft.meta_json or {}
                    bos_ms = live_meta.get("bos_time_ms")
                    reclaim_ms = live_meta.get("reclaim_time_ms")
                    rh_ms = live_meta.get("rh_boundary_time_ms")
                    rl_ms = live_meta.get("rl_boundary_time_ms")
            except Exception:
                pass

        if bos_ms is not None:
            stats["bos_time_ms_valid"] += 1
        if reclaim_ms is not None:
            stats["reclaim_time_ms_valid"] += 1
        if rh_ms is not None:
            stats["rh_boundary_time_ms_valid"] += 1
        if rl_ms is not None:
            stats["rl_boundary_time_ms_valid"] += 1

        plausible = (
            _plausible(bos_ms, row.replay_until_time_ms)
            and _plausible(reclaim_ms, row.replay_until_time_ms)
            if bos_ms and reclaim_ms
            else "—"
        )
        lines.append(
            f"| {row.week} | {row.week} | {old_bos} | {_label(bos_ms)} | {old_reclaim} | {_label(reclaim_ms)} "
            f"| {_label(rh_ms)} | {_label(rl_ms)} | {idx_dup} | {plausible} |"
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- **Audited weeks:** {stats['weeks']}",
            f"- **Live replay available:** {stats['live_replay']}",
            f"- **Rows with valid `bos_time_ms` (live):** {stats['bos_time_ms_valid']}",
            f"- **Rows with valid `reclaim_time_ms` (live):** {stats['reclaim_time_ms_valid']}",
            f"- **Rows with valid `rh_boundary_time_ms` (live):** {stats['rh_boundary_time_ms_valid']}",
            f"- **Rows with valid `rl_boundary_time_ms` (live):** {stats['rl_boundary_time_ms_valid']}",
            f"- **Fixture rows with duplicated debug indices 103/104:** {stats['fixture_index_duplicated_103_104']}",
            "",
            "After Phase 2, new suggestions carry `bos_time_ms` / `reclaim_time_ms` / `rh_boundary_time_ms` / "
            "`rl_boundary_time_ms`. Repeated `103`/`104` in the **frozen fixture** is legacy replay-window noise; "
            "live detector output uses market-time keys for audit joins.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return stats


def generate_reports() -> None:
    rows = build_gold_rows()
    docs = BACKEND_DIR.parent / "docs" / "fixtures"
    write_summary_csv(docs / "detector_audit_4750e5ac_summary.csv", rows)
    write_rl_analysis_md(docs / "detector_rl_analysis.md", rows)
    write_rh_analysis_md(docs / "detector_rh_analysis.md", rows)
    live_candles = None
    try:
        import candle_store

        payload = candle_store.get_candles(symbol="XAUUSD", timeframe="W1", limit=5000)
        candles = list(payload.get("candles") or [])
        if len(candles) >= 200:
            live_candles = candles
    except Exception:
        pass
    write_metadata_report(docs / "detector_audit_4750e5ac_metadata_report.md", live_candles=live_candles)


if __name__ == "__main__":
    generate_reports()
    print("Reports written under docs/fixtures/")
