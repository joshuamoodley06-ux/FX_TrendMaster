# 2025 W1 Range Loss Report

Compares baseline historical scan **4750e5ac** (pre-leg boundary, in-scan seed roll) against latest leg-doctrine scan **bd1500c3** (`reviewed_truth_only`, `PROMOTED_RANGE` seeds, leg boundaries).

## Run metadata

| | Baseline | Leg doctrine |
|--|----------|--------------|
| Run ID | `4750e5ac-46d0-47db-82f0-ac183d0671a2` | `bd1500c3-628c-4c82-96f8-edb76acca6cf` |
| RANGE_CANDIDATE rows | 14 | 6 |
| Boundary doctrine | `LAST_OPPOSITE_SWING_BEFORE_BOS` | `STRUCTURAL_SWING_*` + `htf_leg_trace` |
| Seed policy | `bootstrap_candidate` / `previous_range_candidate` | `reviewed_truth_only` → `PROMOTED_RANGE` |
| Diagnostics replay | local W1 candles (500 bars) | audit export |

## Summary

- **Baseline weeks reviewed:** 14
- **Ranges retained** (RANGE_CANDIDATE at same `replay_until`): **4 / 14**
- **Ranges lost:** **10 / 14**
- **New-only weeks in leg run:** 2 — 2025-10-12, 2025-10-19
- **Dominant loss reason:** `reclaim_cycle_stale_before_active_week`

### Loss reason histogram

- `reclaim_cycle_stale_before_active_week`: **5**
- `boundary_selection_failed`: **2**
- `bos_without_confirmed_reclaim`: **2**
- `scan_step_skipped_despite_isolated_candidate`: **1**

## Per-week comparison

| Week | Present? | Baseline RH/RL | Leg RH/RL | Baseline seed | Leg / replay seed | Rejection (if lost) | Lifecycle | BOS | Reclaim | Boundary stage? |
|------|----------|----------------|-----------|---------------|-------------------|---------------------|-----------|-----|---------|-----------------|
| 2025-01-12 | **NO** | 2726.06/2586.4 | — | bootstrap_candidate | bootstrap_candidate (no prior promoted truth) | Historical scan did not persist RANGE_CANDIDATE at this replay week (isolated leg repla... | RECLAIMED_DOWN | BOS HIGH @ 2025-01-05 | RECLAIM_TOUCH @ 2025-01-12 | YES |
| 2025-01-19 | YES | 2785.89/2586.4 | 2790.01/2536.75 | previous_range_candidate | PROMOTED_RANGE | — | RECLAIMED_UP | BOS LOW @ 2024-11-17 | RECLAIM_CLOSE @ 2024-11-24 | YES |
| 2025-02-02 | YES | 2956.15/2772.07 | 2817.05/2586.4 | bootstrap_candidate | PROMOTED_RANGE | — | RECLAIMED_DOWN | BOS HIGH @ 2025-01-26 | RECLAIM_TOUCH @ 2025-02-02 | YES |
| 2025-06-08 | **NO** | 3499.88/2956.66 | — | bootstrap_candidate | PROMOTED_RANGE | Reclaim cycle completed before active replay week | RECLAIMED_UP | BOS LOW @ 2025-01-26 | RECLAIM_CLOSE @ 2025-02-02 | YES |
| 2025-06-15 | **NO** | 3430.86/3120.81 | — | previous_range_candidate | PROMOTED_RANGE | Reclaim cycle completed before active replay week | RECLAIMED_UP | BOS LOW @ 2024-06-23 | RECLAIM_CLOSE @ 2025-03-09 | YES |
| 2025-06-22 | YES | 3451.19/3120.81 | 2956.15/2772.07 | previous_range_candidate | PROMOTED_RANGE | — | RECLAIMED_DOWN | BOS HIGH @ 2025-06-08 | RECLAIM_CLOSE @ 2025-06-15 | YES |
| 2025-06-29 | **NO** | 3451.19/3248.86 | — | previous_range_candidate | PROMOTED_RANGE | Reclaim cycle completed before active replay week | RECLAIMED_DOWN | BOS HIGH @ 2025-04-20 | RECLAIM_CLOSE @ 2025-04-27 | YES |
| 2025-07-06 | **NO** | 3453.82/3248.86 | — | previous_range_candidate | PROMOTED_RANGE | Reclaim cycle completed before active replay week | RECLAIMED_UP | BOS LOW @ 2025-05-18 | RECLAIM_CLOSE @ 2025-05-25 | YES |
| 2025-07-13 | **NO** | 3499.88/3120.81 | — | bootstrap_candidate | PROMOTED_RANGE | Reclaim cycle completed before active replay week | RECLAIMED_UP | BOS LOW @ 2025-05-18 | RECLAIM_CLOSE @ 2025-05-25 | YES |
| 2025-07-20 | **NO** | 4381.25/3886.56 | — | previous_range_candidate | PROMOTED_RANGE | Reclaim confirmed; no leg boundary candidates | RECLAIMED_UP | BOS LOW @ 2025-04-06 | RECLAIM_CLOSE @ 2025-04-13 | NO |
| 2025-07-27 | **NO** | 4545.98/3886.56 | — | previous_range_candidate | PROMOTED_RANGE | BOS detected; reclaim not yet confirmed | BREACHED_DOWN | broken_boundary=LOW | reclaim not confirmed | NO |
| 2025-08-10 | **NO** | 5598.08/4274.6 | — | bootstrap_candidate | PROMOTED_RANGE | BOS detected; reclaim not yet confirmed | BREACHED_DOWN | broken_boundary=LOW | reclaim not confirmed | NO |
| 2025-12-07 | **NO** | 4264.46/3997.99 | — | bootstrap_candidate | PROMOTED_RANGE | Reclaim confirmed; no leg boundary candidates | RECLAIMED_UP | BOS LOW @ 2025-10-26 | RECLAIM_CLOSE @ 2025-12-07 | NO |
| 2025-12-28 | YES | 4549.7/3997.99 | 4545.98/3886.56 | bootstrap_candidate | PROMOTED_RANGE | — | RECLAIMED_UP | BOS LOW @ 2025-12-14 | RECLAIM_CLOSE @ 2025-12-21 | YES |

## Retained weeks

- **2025-01-19** — baseline 2785.89/2586.4 → leg 2790.01/2536.75 · seed `PROMOTED_RANGE` · boundary `STRUCTURAL_SWING_IMPULSE_LEG`
- **2025-02-02** — baseline 2956.15/2772.07 → leg 2817.05/2586.4 · seed `PROMOTED_RANGE` · boundary `STRUCTURAL_SWING_FLOOR_BEFORE_BOS`
- **2025-06-22** — baseline 3451.19/3120.81 → leg 2956.15/2772.07 · seed `PROMOTED_RANGE` · boundary `STRUCTURAL_SWING_FLOOR_BEFORE_BOS`
- **2025-12-28** — baseline 4549.7/3997.99 → leg 4545.98/3886.56 · seed `PROMOTED_RANGE` · boundary `STRUCTURAL_SWING_IMPULSE_LEG`

## Lost weeks — detail

### 2025-01-12 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 2726.06/2586.4 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `bootstrap_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Historical scan did not persist RANGE_CANDIDATE at this replay week (isolated leg replay would emit a candidate)
- **Lifecycle state (leg replay):** RECLAIMED_DOWN
- **BOS state:** BOS HIGH @ 2025-01-05
- **Reclaim state:** RECLAIM_TOUCH @ 2025-01-12
- **Seed source:** bootstrap_candidate (no prior promoted truth)
- **Boundary stage reached:** YES

### 2025-06-08 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 3499.88/2956.66 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `bootstrap_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Reclaim cycle completed before active replay week
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2025-01-26
- **Reclaim state:** RECLAIM_CLOSE @ 2025-02-02
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** YES

### 2025-06-15 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 3430.86/3120.81 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `previous_range_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Reclaim cycle completed before active replay week
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2024-06-23
- **Reclaim state:** RECLAIM_CLOSE @ 2025-03-09
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** YES

### 2025-06-29 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 3451.19/3248.86 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `previous_range_candidate` · lifecycle `RECLAIMED_UP`
- **Rejection reason:** Reclaim cycle completed before active replay week
- **Lifecycle state (leg replay):** RECLAIMED_DOWN
- **BOS state:** BOS HIGH @ 2025-04-20
- **Reclaim state:** RECLAIM_CLOSE @ 2025-04-27
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** YES

### 2025-07-06 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 3453.82/3248.86 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `previous_range_candidate` · lifecycle `RECLAIMED_UP`
- **Rejection reason:** Reclaim cycle completed before active replay week
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2025-05-18
- **Reclaim state:** RECLAIM_CLOSE @ 2025-05-25
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** YES

### 2025-07-13 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 3499.88/3120.81 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `bootstrap_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Reclaim cycle completed before active replay week
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2025-05-18
- **Reclaim state:** RECLAIM_CLOSE @ 2025-05-25
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** YES

### 2025-07-20 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 4381.25/3886.56 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `previous_range_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Reclaim confirmed; no leg boundary candidates
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2025-04-06
- **Reclaim state:** RECLAIM_CLOSE @ 2025-04-13
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** NO

### 2025-07-27 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 4545.98/3886.56 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `previous_range_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** BOS detected; reclaim not yet confirmed
- **Lifecycle state (leg replay):** BREACHED_DOWN
- **BOS state:** broken_boundary=LOW
- **Reclaim state:** reclaim not confirmed
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** NO

### 2025-08-10 (baseline EDIT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 5598.08/4274.6 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `bootstrap_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** BOS detected; reclaim not yet confirmed
- **Lifecycle state (leg replay):** BREACHED_DOWN
- **BOS state:** broken_boundary=LOW
- **Reclaim state:** reclaim not confirmed
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** NO

### 2025-12-07 (baseline REJECT)

- **Present in leg run:** NO
- **Baseline:** RH/RL 4264.46/3997.99 · `LAST_OPPOSITE_SWING_BEFORE_BOS` · seed `bootstrap_candidate` · lifecycle `RECLAIMED_DOWN`
- **Rejection reason:** Reclaim confirmed; no leg boundary candidates
- **Lifecycle state (leg replay):** RECLAIMED_UP
- **BOS state:** BOS LOW @ 2025-10-26
- **Reclaim state:** RECLAIM_CLOSE @ 2025-12-07
- **Seed source:** PROMOTED_RANGE
- **Boundary stage reached:** NO

## Why ranges were lost

1. **Reclaim freshness gate (dominant)** — With `PROMOTED_RANGE` seeds, many baseline weeks hit `Reclaim cycle completed before active replay week`. The BOS→reclaim cycle tied to promoted truth finished on an earlier bar, so the walk does not emit a new RANGE_CANDIDATE at the baseline replay week.
2. **Scan cadence vs isolated replay** — Week **2025-01-12** still produces a candidate in isolated leg replay (bootstrap seed) but bd1500c3's first written candidate is **2025-01-19** (promoted seed from range 15).
3. **Boundary failures** — **2025-07-20** and **2025-12-07**: reclaim confirmed but `Reclaim confirmed; no leg boundary candidates` (boundary stage **NO**).
4. **Open BOS** — **2025-07-27** and **2025-08-10**: `BOS detected; reclaim not yet confirmed` under promoted seeds.
5. **Trade-off** — Leg run adds **2025-10-12** and **2025-10-19** (not in baseline) while dropping eight Jun–Aug baseline weeks.

## Notes

- Baseline fixture: `docs/fixtures/detector_audit_4750e5ac.json`
- Leg audit: `docs/fixtures/detector_audit_bd1500c3.json`
- Match key: `replay_until_time` (same W1 bar close).
- Lost-week diagnostics: leg-doctrine isolated replay with promoted seeds from prior-week Josh `final_snapshot_json`.
