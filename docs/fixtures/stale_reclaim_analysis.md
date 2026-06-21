# Stale Reclaim Analysis — 2025 XAUUSD W1

Analysis-only report. No detector, lifecycle, or scan-runner code was changed.

Focus: five baseline weeks lost in leg + `reviewed_truth_only` run **bd1500c3** with rejection `Reclaim cycle completed before active replay week` (classified as `reclaim_cycle_stale_before_active_week`).

## Where the stale rule lives

| Item | Location |
|------|----------|
| Freshness check | `backend/detector/range_v2.py` → `_reclaim_cycle_is_fresh()` |
| Rejection text | `detect_range_v2_suggestions()` after `derive_boundaries()` succeeds |
| Lag constant | `backend/detector/range_scan_runner.py` → `SCAN_MAX_RECLAIM_LAG_BARS = 1` |
| Lag injection | `range_scan_runner.py` sets `max_reclaim_lag_bars` when `working_seed is not None` |
| Related (chain mode) | `historical_range_chain.py` — separate bootstrap stale messaging |

## Exact trigger condition

```python
# range_v2._reclaim_cycle_is_fresh
lag = ctx.detection_window_meta['max_reclaim_lag_bars']  # historical scan: 1
fresh = lifecycle.chain.reclaim_index >= ctx.active_index - lag
```

When `max_reclaim_lag_bars` is **unset**, the check is **skipped** (always fresh).

With `lag = 1`, reclaim must land on the **active bar** or **one bar before** it. If reclaim completed earlier, lifecycle may still be `RECLAIMED_*` and boundaries may compute, but emission becomes `NO_VALID_RANGE` with reason `Reclaim cycle completed before active replay week`.

## Summary table

| Week | BOS time | Reclaim time | Replay week | Age bars | Threshold | Josh final RH/RL | Leg RH/RL (no stale) | Leg ≈ Josh? | Likely Josh-active? |
|------|----------|--------------|-------------|----------|-----------|------------------|----------------------|-------------|---------------------|
| 2025-06-08 | 2025-01-26 | 2025-02-02 | 2025-06-08 | 18 | 1 | 3499.88/2956.66 | 2956.15/2730.40 | NO | YES |
| 2025-06-15 | 2024-06-23 | 2025-03-09 | 2025-06-15 | 14 | 1 | 3430.86/3120.81 | 3499.88/2293.60 | NO | YES |
| 2025-06-29 | 2025-04-20 | 2025-04-27 | 2025-06-29 | 9 | 1 | 3451.19/3248.86 | 3499.88/3120.81 | NO | YES |
| 2025-07-06 | 2025-05-18 | 2025-05-25 | 2025-07-06 | 6 | 1 | 3453.82/3248.86 | 3451.19/3204.56 | NO | YES |
| 2025-07-13 | 2025-05-18 | 2025-05-25 | 2025-07-13 | 7 | 1 | 3499.88/3120.81 | 3453.82/3204.56 | NO | YES |

## Per-week detail

### 2025-06-08

| Field | Value |
|-------|-------|
| Baseline replay week | 2025-06-08 |
| Baseline detector RH/RL | 3403.23 / 3120.81 |
| Josh final RH/RL | 3499.88 / 2956.66 |
| Seed source (leg replay) | PROMOTED_RANGE |
| Promoted seed RH/RL | 2956.15 / 2772.07 |
| BOS time | 2025-01-26 (index 32) |
| Reclaim time | 2025-02-02 (index 33) |
| Active replay index | 51 |
| Stale age (active − reclaim) | **18 bars** |
| Threshold (`max_reclaim_lag_bars`) | **1** |
| Fresh? | False |
| Lifecycle before stale gate | `RECLAIMED_UP` |
| Baseline lifecycle at same week | `RECLAIMED_DOWN` |
| Boundary stage reached? | YES |
| Leg RH/RL if stale disabled | 2956.15 / 2730.4 |
| Josh likely structurally active? | YES — user EDITED range at this replay week |

### 2025-06-15

| Field | Value |
|-------|-------|
| Baseline replay week | 2025-06-15 |
| Baseline detector RH/RL | 3446.72 / 3120.81 |
| Josh final RH/RL | 3430.86 / 3120.81 |
| Seed source (leg replay) | PROMOTED_RANGE |
| Promoted seed RH/RL | 3499.88 / 2956.66 |
| BOS time | 2024-06-23 (index 1) |
| Reclaim time | 2025-03-09 (index 38) |
| Active replay index | 52 |
| Stale age (active − reclaim) | **14 bars** |
| Threshold (`max_reclaim_lag_bars`) | **1** |
| Fresh? | False |
| Lifecycle before stale gate | `RECLAIMED_UP` |
| Baseline lifecycle at same week | `RECLAIMED_DOWN` |
| Boundary stage reached? | YES |
| Leg RH/RL if stale disabled | 3499.88 / 2293.6 |
| Josh likely structurally active? | YES — user EDITED range at this replay week |

### 2025-06-29

| Field | Value |
|-------|-------|
| Baseline replay week | 2025-06-29 |
| Baseline detector RH/RL | 3451.19 / 3256.12 |
| Josh final RH/RL | 3451.19 / 3248.86 |
| Seed source (leg replay) | PROMOTED_RANGE |
| Promoted seed RH/RL | 3451.19 / 3120.81 |
| BOS time | 2025-04-20 (index 44) |
| Reclaim time | 2025-04-27 (index 45) |
| Active replay index | 54 |
| Stale age (active − reclaim) | **9 bars** |
| Threshold (`max_reclaim_lag_bars`) | **1** |
| Fresh? | False |
| Lifecycle before stale gate | `RECLAIMED_DOWN` |
| Baseline lifecycle at same week | `RECLAIMED_UP` |
| Boundary stage reached? | YES |
| Leg RH/RL if stale disabled | 3499.88 / 3120.81 |
| Josh likely structurally active? | YES — user EDITED range at this replay week |

### 2025-07-06

| Field | Value |
|-------|-------|
| Baseline replay week | 2025-07-06 |
| Baseline detector RH/RL | 3451.19 / 3248.86 |
| Josh final RH/RL | 3453.82 / 3248.86 |
| Seed source (leg replay) | PROMOTED_RANGE |
| Promoted seed RH/RL | 3451.19 / 3248.86 |
| BOS time | 2025-05-18 (index 48) |
| Reclaim time | 2025-05-25 (index 49) |
| Active replay index | 55 |
| Stale age (active − reclaim) | **6 bars** |
| Threshold (`max_reclaim_lag_bars`) | **1** |
| Fresh? | False |
| Lifecycle before stale gate | `RECLAIMED_UP` |
| Baseline lifecycle at same week | `RECLAIMED_UP` |
| Boundary stage reached? | YES |
| Leg RH/RL if stale disabled | 3451.19 / 3204.56 |
| Josh likely structurally active? | YES — user EDITED range at this replay week |

### 2025-07-13

| Field | Value |
|-------|-------|
| Baseline replay week | 2025-07-13 |
| Baseline detector RH/RL | 3368.63 / 3248.86 |
| Josh final RH/RL | 3499.88 / 3120.81 |
| Seed source (leg replay) | PROMOTED_RANGE |
| Promoted seed RH/RL | 3453.82 / 3248.86 |
| BOS time | 2025-05-18 (index 48) |
| Reclaim time | 2025-05-25 (index 49) |
| Active replay index | 56 |
| Stale age (active − reclaim) | **7 bars** |
| Threshold (`max_reclaim_lag_bars`) | **1** |
| Fresh? | False |
| Lifecycle before stale gate | `RECLAIMED_UP` |
| Baseline lifecycle at same week | `RECLAIMED_DOWN` |
| Boundary stage reached? | YES |
| Leg RH/RL if stale disabled | 3453.82 / 3204.56 |
| Josh likely structurally active? | YES — user EDITED range at this replay week |

## Key questions

### 1. Where is `reclaim_cycle_stale_before_active_week` produced?

Classification label in `backend/tests/generate_range_loss_report.py` maps the detector string `Reclaim cycle completed before active replay week` from `range_v2.detect_range_v2_suggestions()` (after boundaries are valid, before coherence check).

### 2. What exact condition triggers it?

`reclaim_index < active_index - 1` when `max_reclaim_lag_bars` is set (historical scan uses **1**).
Observed ages: **6–18 bars** — all far beyond threshold 1.

### 3. Is the stale rule intended to prevent old cycles on later weeks, or carry-forward?

**Prevent stamping ancient BOS→reclaim cycles onto later replay bars** during historical walk. Comment in `range_scan_runner.py`: *"After seed rolls forward, ignore reclaim cycles that completed before scan period."* The lag gate is a **bar-proximity** filter on which reclaim counts as "this week's" birth event.

### 4. Are we conflating stale candidate discovery with active range persistence?

**Yes, partially.** With `PROMOTED_RANGE` seeds, `evaluate_lifecycle()` re-scans the full replay window from promoted RH/RL and may attach a **completed reclaim from months earlier**. The stale gate then blocks emitting that discovery on the active week — but Josh's baseline edits show he **does** want a range labeled at that replay week (often with a **different** BOS/reclaim aligned to the active bar).

Baseline run **4750e5ac** used in-scan seed roll, so each week re-derived structure near the active bar. Leg + reviewed truth re-anchors to promoted truth and surfaces **older** reclaim cycles.

### 5. Is the Weekly detector treating a valid range as expired too early?

**For discovery emission: yes — relative to Josh's week labels.** All five weeks are Josh-EDITED (structurally active in his review). **5/5** reached leg boundary selection before the stale gate; **0/5** leg boundaries (if emitted) would match Josh RH/RL within tolerance.

The rule is doing what it was coded to do (reclaim must be within 1 bar of active index). The mismatch is **doctrine**: Josh labels ranges at the replay week using **that week's** BOS/reclaim context; promoted-seed replay finds **earlier** reclaim completion and the lag=1 gate refuses to stamp it forward.

## Common pattern

| Pattern | Observation |
|---------|-------------|
| Promoted seed | All 5 weeks seed from prior-week Josh `PROMOTED_RANGE` |
| Reclaim age | **6–18** W1 bars before active (threshold **1**) |
| Lifecycle | `RECLAIMED_UP` or `RECLAIMED_DOWN` — cycle **completed** |
| Boundaries | **5/5** computed before stale rejection |
| Josh alignment | Leg boundaries without stale gate match Josh on **0/5** weeks |
| Baseline contrast | Baseline used reclaim **on** replay week (touch/close at active bar) |

## Stale reason count

- `reclaim_cycle_stale_before_active_week`: **5** (this report)
- Threshold: `SCAN_MAX_RECLAIM_LAG_BARS = 1`
- Age range: 6–18 W1 bars

## Recommendation

**SPLIT DISCOVERY VS PERSISTENCE**

Data supports keeping **some** anti-stale guard for bootstrap/chain hygiene, but the current `lag=1` gate combined with `PROMOTED_RANGE` replay is **rejecting Josh-valid weekly labels** because it finds an old reclaim against promoted anchors instead of discovering the **active-week** cycle.

Do **not** simply remove the gate without separating:

1. **Persistence** — promoted `map_ranges` truth as seed context (keep).
2. **Discovery** — which BOS→reclaim **birth event** attaches to the active replay bar (needs week-local cycle, as baseline roll did).

Next step (future, not this task): audit whether stale check should apply only to **in-scan temp seed roll**, not when re-discovering from promoted truth; or require reclaim at active bar for **new** candidate emission while still allowing promoted seed for boundary context only.

**Not recommended now:** blanket `RELAX STALE RULE` — would re-stamp Feb reclaim ranges onto Jun–Jul replay weeks with leg RH/RL that do **not** match Josh (see table).

**Not recommended now:** `KEEP STALE RULE` unchanged with `reviewed_truth_only` — loses 5/14 baseline weeks with valid Josh edits.

## Inputs

- `docs/fixtures/2025_w1_range_loss_report.md`
- `docs/fixtures/detector_audit_4750e5ac.json`
- `docs/fixtures/detector_audit_bd1500c3.json`
- Local W1 candles (FXTM_Research DB)
