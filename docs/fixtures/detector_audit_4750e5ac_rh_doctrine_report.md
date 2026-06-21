# RH doctrine report — audit run 4750e5ac

Phase 4 **plan only**. Doctrine discovery from Josh’s 2025 XAUUSD W1 audit corrections. **No detector code was changed.**

## Scope note

The audit CSV lists **12 EDIT** weeks; **10** are tagged `WRONG_RH` and **2** are `WRONG_RL` (2025-06-22, 2025-06-29 — RH already matched Josh). This report analyzes all **10 EDIT / WRONG_RH** weeks in detail. Two **REJECT / WRONG_RH** weeks (2025-12-07, 2025-12-28) had ΔRH = 0 and are noted in the appendix.

## Data available vs missing

| Field | Present in fixture? |
|-------|---------------------|
| `detector_suggested_rh` / `retracement_impulse_high` | Yes — equal in 14/14 weeks (detector RH = BOS-bar high) |
| `boundary_selection_reason` | Yes — `LAST_OPPOSITE_SWING_BEFORE_BOS` (RL-side label in legacy export) |
| `selected_rh_source` | **No** (pre–boundary-trace export) |
| `boundary_trace` / candidate swing list | **No** |
| Josh `suggested_rh` + `suggested_rh_time_ms` | Yes — in `final_snapshot_json` |
| `range_end_time` | Yes — on each suggestion |

**Inference rule used:** compare Josh’s `suggested_rh_time_ms` to reclaim time and `range_end_time`; compare Josh RH price to `retracement_impulse_high`, `seed_rh`, and prior corrected RH values. No doctrine label was assumed without this evidence.

## Doctrine options (reference)

| Option | Definition |
|--------|------------|
| **A** | Highest structural swing **after** reclaim close |
| **B** | Highest swing in **full impulse leg** (pre-BOS / range body) |
| **C** | Highest visible **parent/container** high in local lookback |
| **D** | **Seed** / previous range high carried forward |
| **E** | Other / unknown |

---

## Per-week analysis (10 EDIT / WRONG_RH)

| week | detector RH | Josh RH | RH Δ | candidate highs in meta | selected_rh_source (inferred) | boundary reason | seed_rh | replay_until | bucket | one-line explanation |
|------|-------------|---------|------|-------------------------|-------------------------------|-----------------|---------|--------------|--------|----------------------|
| 2025-01-12 | 2697.75 | 2726.06 | +28.31 | impulse_high 2697.75; seed 2685.54 | BOS_BAR (`retracement_impulse_high`) | LAST_OPPOSITE_SWING_BEFORE_BOS | 2685.54 | 2025-01-12 | **B** | Josh RH time = `range_end` 2025-01-05 (before reclaim 2025-01-12); price above BOS bar → impulse-leg ceiling, not post-reclaim. |
| 2025-01-19 | 2724.66 | 2785.89 | +61.23 | impulse_high 2724.66; seed 2697.75 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 2697.75 | 2025-01-19 | **B** | Josh RH @ 2025-01-12 = `range_end`; still pre-reclaim; +61 vs BOS bar. |
| 2025-02-02 | 2817.05 | 2956.15 | +139.10 | impulse_high 2817.05; seed 2790.01 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 2790.01 | 2025-02-02 | **B** | Josh RH @ 2025-01-26 = `range_end`; largest Jan–Feb gap; still impulse-leg high, not seed. |
| 2025-06-08 | 3403.23 | 3499.88 | +96.65 | impulse_high 3403.23; seed 3365.89 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3365.89 | 2025-06-08 | **B** | Josh RH @ 2025-06-01 = `range_end`; pre-reclaim structural high above BOS bar. |
| 2025-06-15 | 3446.72 | 3430.86 | −15.86 | impulse_high 3446.72; seed 3403.23 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3403.23 | 2025-06-15 | **B** | Josh RH @ 2025-06-08 = `range_end` and **below** BOS bar — rejects BOS-bar RH in favor of earlier impulse-leg swing. |
| 2025-07-06 | 3451.19 | 3453.82 | +2.63 | impulse_high 3451.19; seed 3451.19 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3451.19 | 2025-07-06 | **B** | Near-match week; Josh RH @ 2025-06-15 = `range_end`; tiny +2.6 above BOS bar. |
| 2025-07-13 | 3368.63 | 3499.88 | +131.25 | impulse_high 3368.63; seed 3365.89; prior Josh RH 3499.88 (06-08) | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3365.89 | 2025-07-13 | **B** | Price equals earlier corrected RH 3499.88, but `suggested_rh_time_ms` = `range_end` 2025-07-06 — time evidence favors impulse-leg week high, not seed carry (D). |
| 2025-07-20 | 3377.43 | 4381.25 | +1003.82 | impulse_high 3377.43; seed 3368.63 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3368.63 | 2025-07-20 | **B** | Josh RH @ 2025-07-13 = `range_end`; detector BOS bar ~3377 stale vs real weekly high 4381 — same doctrine, scan-window mismatch. |
| 2025-07-27 | 3438.81 | 4545.98 | +1107.17 | impulse_high 3438.81; seed 3377.43 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3377.43 | 2025-07-27 | **B** | Josh RH @ 2025-07-20 = `range_end`; pre-reclaim; detector still on low BOS-bar pool. |
| 2025-08-10 | 3407.59 | 5598.08 | +2190.49 | impulse_high 3407.59; seed 3365.89 | BOS_BAR | LAST_OPPOSITE_SWING_BEFORE_BOS | 3365.89 | 2025-08-10 | **B** | Josh RH @ 2025-08-03 = `range_end`; largest error; same impulse-leg rule, detector BOS bar far below rally high. |

### Key time alignment (all 10 weeks)

Josh `suggested_rh_time_ms` matches the suggestion’s `range_end_time` week in **10/10** cases. In **0/10** cases is Josh RH time at or after reclaim (`retracement_time_ms`). This rules out **A** for this audit slice.

### Key price alignment

| Compare Josh RH to | Matches (10 EDIT weeks) |
|--------------------|---------------------------|
| `retracement_impulse_high` (detector / BOS bar) | 0/10 |
| `seed_rh` | 0/10 (07-06 within 2.6 pts only) |
| Prior corrected RH price only | 1/10 (07-13 = 06-08 price; time still = range_end) |
| `range_end` week (via `suggested_rh_time_ms`) | **10/10** |

---

## Summary

### Counts per doctrine bucket (EDIT / WRONG_RH)

| Bucket | Count | Share |
|--------|-------|-------|
| **A** — post-reclaim high | 0 | 0% |
| **B** — impulse-leg / range-end structural high | **10** | **100%** |
| **C** — parent/container high | 0 | 0% |
| **D** — seed carry-forward | 0 | 0% |
| **E** — unknown | 0 | 0% |

### Biggest RH errors (absolute Δ)

| Rank | week | ΔRH | Josh RH | detector RH |
|------|------|-----|---------|-------------|
| 1 | 2025-08-10 | +2190.49 | 5598.08 | 3407.59 |
| 2 | 2025-07-27 | +1107.17 | 4545.98 | 3438.81 |
| 3 | 2025-07-20 | +1003.82 | 4381.25 | 3377.43 |
| 4 | 2025-02-02 | +139.10 | 2956.15 | 2817.05 |
| 5 | 2025-07-13 | +131.25 | 3499.88 | 3368.63 |

### Does one doctrine explain the majority?

**Yes.** Option **B** explains **10/10** EDIT / WRONG_RH weeks when grounded in audit timestamps: Josh selects the **high of the `range_end` week** (impulse-leg ceiling before reclaim), not the BOS candle high the detector emitted as `retracement_impulse_high`.

Current detector failure mode (from `detector_rh_analysis.md`): RH ≡ `retracement_impulse_high` (BOS bar) in **14/14** weeks — the opposite of Josh’s rule on every edited RH week.

### Jan–Feb vs Jul–Aug

| Period | Weeks | Avg \|ΔRH\| | Doctrine bucket | Pattern |
|--------|-------|-------------|-----------------|---------|
| Jan–Feb (01-12 → 02-02) | 3 | 76.21 | B (3/3) | Small gaps; Josh `range_end` high modestly above stale BOS bar. |
| Jul–Aug (07-06 → 08-10) | 5 | 889.07 | B (5/5) | **Same doctrine**; errors explode because detector BOS bar stays ~3365–3451 (replay-window artifact `bos@103`) while Josh `range_end` highs track the summer rally (3453 → 5598). |

Jul–Aug is **not** a different RH doctrine — it is the same **B** rule with a broken event/window linkage (see seed-simulation report: bootstrap resets, compounding wrong BOS context).

### Appendix: REJECT / WRONG_RH (no Josh RH change)

| week | detector RH | Josh RH | ΔRH | note |
|------|-------------|---------|-----|------|
| 2025-12-07 | 4264.46 | 4264.46 | 0 | Josh accepted detector RH |
| 2025-12-28 | 4549.7 | 4549.7 | 0 | Josh accepted detector RH |

These do not contradict **B**; they indicate the detector happened to align that week (or Josh did not need to move RH).

---

## Recommendation

**IMPLEMENT RH DOCTRINE OPTION B**

Select RH as the **highest structural swing high in the impulse leg** (equivalently: the high at the range’s `range_end` week in this audit), **not** the BOS-bar high (`retracement_impulse_high`).

### Implementation guardrails (plan only — not coded here)

1. **Do not** use post-reclaim highs (**A**) — 0/10 audit support.
2. **Do not** default RH to BOS candle high when a higher pre-BOS / impulse-leg swing exists (06-15 proves Josh may pick **below** BOS bar too).
3. Emit `selected_rh_source` + `boundary_trace` on future runs so C vs B can be re-tested with swing lists.
4. Jul–Aug large residuals likely need **correct BOS/range window** (separate from doctrine) before RH doctrine alone is measured as “fixed.”

### What would trigger NEED MORE AUDIT DATA instead

Not reached for bucket selection — **B** is unanimous on time evidence. Additional audit would still help to:

- confirm parent/container rule (**C**) on other symbols or layers,
- validate **B** when `boundary_trace` candidate lists are present,
- separate RH doctrine from seed-chain / scan-bootstrap issues in Jul–Aug.

---

*Sources: `detector_audit_4750e5ac.json`, `detector_audit_4750e5ac_summary.csv`, `detector_rh_analysis.md`, `detector_rl_analysis.md`, `detector_audit_4750e5ac_seed_simulation_report.md`.*
