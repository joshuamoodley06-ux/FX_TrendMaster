# RANGE Profile Analytics Plan

**Status:** **PLANNING ONLY** — no code, no schema migration, no detector changes authorized.  
**Date:** 2026-06-17  
**Prerequisites:** Generic range detection (`RANGE_CANDIDATE`, `range_scale=UNKNOWN`) ✓ · Review confirms validity only ✓  
**Related docs:** `RANGE_V2_IMPLEMENTATION_PLAN.md` §17 · `PHASE_0_DETECTION_BRAIN_CONTRACTS.md` §5 · `PYTHON_ANALYST_V1_1_PLAN.md` · `range_analytics_classifier.py` (stub)

> **Scope:** After valid ranges exist across a date period, analytics classifies **what happened after each range formed**. Detection and review are frozen. This plan defines Layer 3 measurement only.

---

## 1. Purpose

### 1.1 Problem statement

The detector answers: *“Is this a valid range container (RH/RL)?”*  
Review answers: *“Do I confirm this range as structural truth?”*  
Analytics must answer: *“What profile did this range exhibit after it formed?”*

Major/minor hierarchy is **not** set during review. It is **derived later** from containment, child-range counts, and post-formation behavior (`DERIVED_MAJOR`, `DERIVED_MINOR`, etc. — separate classifier).

### 1.2 Hard boundaries

| Rule | Meaning |
|------|---------|
| **No detector changes** | `pipeline.py`, `range_v2.py`, `range_candidate.py` untouched |
| **No auto-promotion** | Analytics reads confirmed structure; never writes `map_ranges` / `map_events` |
| **No manual MAJOR/MINOR** | `map_ranges.range_scale` stays `UNKNOWN` on confirm; profiles are analytics labels |
| **Read-only inputs** | `map_ranges`, `map_events`, `candles`, optional `retracement_measurements` |
| **Replay-safe** | All measurements use candle windows ≤ evaluation cut; no future leak |

### 1.3 Three-layer placement

```text
LAYER 1 — Suggestions     detector_suggestions (RANGE_CANDIDATE)
LAYER 2 — Confirmed       map_ranges (UNKNOWN scale), map_events (BOS, etc.)
LAYER 3 — Profile analytics   range_profile_snapshots (proposed) + aggregate views
```

---

## 2. Core idea

```text
Date period
  → Detector emits RANGE_CANDIDATE rows (multiple RH/RL candidates)
  → User confirms validity → map_ranges rows (range_scale = UNKNOWN)
  → Analytics engine walks forward from each range’s formation time
  → Assigns one primary RANGE_PROFILE + stores factual metrics
  → Hierarchy classifier (later) reads profiles + containment → DERIVED_MAJOR / DERIVED_MINOR
```

**Unit of analysis:** one **confirmed range** (`old_range_id` at profile start), evaluated from its active/formation time through a configurable **lookahead window** (or until terminal event).

---

## 3. Profile taxonomy

Primary profile label — `range_profile` (analytics-only enum):

| # | Profile | Definition |
|---|---------|------------|
| 1 | `ABANDONED` | Range breaks (BOS beyond boundary) and **never** validly reclaims per doctrine reclaim rule within lookahead. May correlate with `map_ranges.status = ABANDONED` or explicit `ABANDON_RANGE` if present. |
| 2 | `NEVER_RECLAIMED` | Price leaves the range (post-break excursion) and **does not** return inside old RH/RL during lookahead. Distinct from `ABANDONED` when break semantics differ (e.g. wick-only vs confirmed BOS). |
| 3 | `SHALLOW_RECLAIM` | Price reclaims into old range body but **shallow** — does not breach deep mitigation thresholds. Example band: respects ~70% / 75% fib of impulse (see §5.3). |
| 4 | `DEEP_RECLAIM` | Price reclaims **deep** into old range — breaches 61.8% or deeper into prior body. |
| 5 | `CONTINUATION_SURVIVED` | After reclaim, price **continues in original BOS direction** without invalidating the new range (no opposite-side break of new container within survival window). |
| 6 | `FAILED_CONTINUATION` | After reclaim, price **invalidates** — breaks the **opposite** side of the new/post-reclaim range (failed follow-through). |

### 3.1 Profile decision order (proposed)

Evaluate terminal states first; assign **one primary** profile per range episode:

```text
1. No BOS in window           → profile = NEVER_RECLAIMED (or UNRESOLVED if range still active)
2. BOS, no reclaim            → NEVER_RECLAIMED or ABANDONED (per break + abandon rules)
3. Reclaim shallow            → SHALLOW_RECLAIM (may upgrade if continuation evaluated)
4. Reclaim deep               → DEEP_RECLAIM (may upgrade if continuation evaluated)
5. Post-reclaim continuation  → CONTINUATION_SURVIVED
6. Post-reclaim opposite break → FAILED_CONTINUATION
```

**Sub-labels (optional, stored in `meta_json`):**

- `reclaim_depth_class`: `SHALLOW` | `MID` | `DEEP` | `EXTREME` (aligns with Python Analyst v1.1)
- `continuation_outcome`: `SURVIVED` | `FAILED` | `PENDING` | `UNRESOLVED`

### 3.2 Relationship to existing contracts

| Existing concept | Profile analytics use |
|------------------|----------------------|
| `retracement_measurements` (Phase 0 §5) | Overlapping factual fields; profile engine may **populate** or **reference** rows — not replace |
| Python Analyst `retracement_stats.csv` | Research export; profile table is durable DB truth for cockpit queries |
| `range_analytics_classifier` stub | Consumes profile snapshots + containment for `DERIVED_MAJOR` / `DERIVED_MINOR` |
| RANGE_V2 lifecycle `RECLAIMED_*` | Detector suggestion state only; profile uses **confirmed** `map_events` + candles |

---

## 4. Inputs

### 4.1 Required sources

| Source | Fields used |
|--------|-------------|
| `map_ranges` | `id`, `range_high_price`, `range_low_price`, `range_high_time`, `range_low_time`, `active_from_time`, `parent_range_id`, `status`, `confirmed_from_suggestion_id`, `structure_layer`, `source_timeframe` |
| `map_events` | BOS events (`BOS_UP` / `BOS_DOWN`), reclaim-linked events, `break_level_price`, `event_time`, `active_range_id`, `old_range_id`, `new_range_id` |
| `candles` | OHLC series for `symbol` + `source_timeframe` in `[range_start, lookahead_end]` |
| Child ranges | Other `map_ranges` rows with `parent_range_id = old_range_id` formed before profile milestones |

### 4.2 Date-period batch context

| Parameter | Meaning |
|-----------|---------|
| `symbol` | e.g. `XAUUSD` |
| `structure_layer` | e.g. `WEEKLY` |
| `source_timeframe` | e.g. `W1` |
| `date_from` / `date_to` | Evaluation cohort window (which confirmed ranges to profile) |
| `lookahead_bars` or `lookahead_ms` | How far forward to observe post-formation behavior per range |
| `break_rule` | HTF wick vs LTF body-close — must match layer (from `break_rules.py`) |

### 4.3 Child range counting

Count **confirmed** child ranges (`map_ranges` with `parent_range_id` linked, directly or via containment graph) whose `active_from_time` falls **before** each milestone:

| Milestone | Counter field |
|-----------|---------------|
| First reclaim close inside old boundary | `number_of_child_ranges_before_reclaim` |
| Continuation confirmed (same-direction BOS or structural hold) | `number_of_child_ranges_before_continuation` |
| Failure (opposite break of new range) | `number_of_child_ranges_before_failure` |

**Note:** At profile time, parent links may still be `UNKNOWN` scale — use **price containment** + time nesting when `parent_range_id` is null.

---

## 5. Metrics contract

### 5.1 Linkage fields (required)

| Field | Type | Description |
|-------|------|-------------|
| `old_range_id` | INTEGER | Range under profile (the container being studied) |
| `new_range_id` | INTEGER NULL | Post-BOS / post-reclaim range if one formed |
| `bos_event_id` | INTEGER NULL | `map_events.id` for initiating BOS |
| `reclaim_event_id` | INTEGER NULL | Event or synthetic reclaim marker id if stored |

### 5.2 Time window fields

| Field | Type | Description |
|-------|------|-------------|
| `reclaim_start_time` | TEXT / ms | First candle entering reclaim observation window (typically post-BOS) |
| `reclaim_end_time` | TEXT / ms NULL | Candle where reclaim completes (close back inside old boundary) |
| `failure_time` | TEXT / ms NULL | Opposite-side invalidation time for `FAILED_CONTINUATION` |

### 5.3 Price / depth fields

| Field | Type | Description |
|-------|------|-------------|
| `deepest_reclaim_price` | REAL NULL | Deepest price penetration into old range body during reclaim window |
| `max_reclaim_percent` | REAL NULL | 0.0–1.0+ depth vs impulse leg (see Phase 0 §5.4 formulas) |
| `breached_618` | INTEGER 0/1 | Reclaim depth crossed 61.8% of impulse |
| `breached_70` | INTEGER 0/1 | Reclaim respected / breached 70% level (contract TBD) |
| `breached_75` | INTEGER 0/1 | Reclaim respected / breached 75% level |
| `reclaimed_to_midpoint` | INTEGER 0/1 | Price touched old range midpoint during reclaim |

**Example thresholds (not locked — tune in implementation phase):**

```text
SHALLOW_RECLAIM:  max_reclaim_percent < 0.618 OR (breached_70 = 0 AND breached_75 = 0)
DEEP_RECLAIM:     breached_618 = 1 OR max_reclaim_percent >= 0.618
```

Align with Python Analyst classes: shallow 0–0.33, mid 0.33–0.66, deep 0.66–1.00 — profile plan uses **61.8% / 70% / 75%** as Josh-specified research bands.

### 5.4 Continuation fields

| Field | Type | Description |
|-------|------|-------------|
| `continuation_direction` | TEXT NULL | `UP` \| `DOWN` — original BOS direction |
| `continuation_confirmed` | INTEGER 0/1 | Same-direction structural follow-through held |

### 5.5 Timing counters (candles)

| Field | Type | Description |
|-------|------|-------------|
| `candles_to_reclaim` | INTEGER NULL | Bars from BOS candle to reclaim close |
| `candles_to_continuation` | INTEGER NULL | Bars from reclaim to continuation confirmation |
| `candles_to_failure` | INTEGER NULL | Bars from reclaim (or continuation) to opposite break |

### 5.6 Child range counters

| Field | Type | Description |
|-------|------|-------------|
| `number_of_child_ranges_before_reclaim` | INTEGER | Child/nested ranges formed before reclaim |
| `number_of_child_ranges_before_continuation` | INTEGER | Before continuation milestone |
| `number_of_child_ranges_before_failure` | INTEGER | Before failure milestone |

### 5.7 Profile output field

| Field | Type | Description |
|-------|------|-------------|
| `range_profile` | TEXT | Primary enum: §3 table |
| `profile_confidence` | TEXT | `HIGH` \| `MEDIUM` \| `LOW` |
| `profile_reason_text` | TEXT | Human-readable trace |
| `meta_json` | JSON | Thresholds used, lookahead config, audit warnings |

---

## 6. Proposed storage (future — not implemented)

### 6.1 Table: `range_profile_snapshots`

Append-only analytics facts per range episode (one row per profiling run, versioned by `profile_run_id`):

```sql
-- PLAN ONLY — not migrated
CREATE TABLE range_profile_snapshots (
    profile_snapshot_id     TEXT PRIMARY KEY,
    schema_version          TEXT NOT NULL DEFAULT 'range_profile_v0',
    profile_run_id          TEXT NOT NULL,
    range_profile           TEXT NOT NULL,
    profile_confidence      TEXT NOT NULL DEFAULT 'MEDIUM',

    old_range_id            INTEGER NOT NULL,
    new_range_id            INTEGER NULL,
    bos_event_id            INTEGER NULL,
    reclaim_event_id        INTEGER NULL,

    symbol                  TEXT NOT NULL,
    structure_layer         TEXT NOT NULL,
    source_timeframe        TEXT NOT NULL,
    case_ref                TEXT NULL,

    reclaim_start_time_ms   INTEGER NULL,
    reclaim_end_time_ms     INTEGER NULL,
    failure_time_ms         INTEGER NULL,

    deepest_reclaim_price   REAL NULL,
    max_reclaim_percent     REAL NULL,
    breached_618            INTEGER NOT NULL DEFAULT 0,
    breached_70             INTEGER NOT NULL DEFAULT 0,
    breached_75             INTEGER NOT NULL DEFAULT 0,
    reclaimed_to_midpoint   INTEGER NOT NULL DEFAULT 0,

    continuation_direction  TEXT NULL,
    continuation_confirmed  INTEGER NOT NULL DEFAULT 0,

    candles_to_reclaim      INTEGER NULL,
    candles_to_continuation INTEGER NULL,
    candles_to_failure      INTEGER NULL,

    number_of_child_ranges_before_reclaim       INTEGER NOT NULL DEFAULT 0,
    number_of_child_ranges_before_continuation  INTEGER NOT NULL DEFAULT 0,
    number_of_child_ranges_before_failure       INTEGER NOT NULL DEFAULT 0,

    lookahead_bars          INTEGER NULL,
    date_from_ms            INTEGER NULL,
    date_to_ms              INTEGER NULL,

    profile_reason_text     TEXT DEFAULT '',
    meta_json               TEXT NULL,
    created_at_utc_ms       INTEGER NOT NULL
);
```

**Indexes (proposed):** `(old_range_id)`, `(profile_run_id, range_profile)`, `(symbol, structure_layer, source_timeframe)`.

### 6.2 Overlap with `retracement_measurements`

| Approach | Recommendation |
|----------|----------------|
| Merge into one table | **No** — retracement is BOS-pair factual measurement; profile is episode outcome |
| Foreign key link | `range_profile_snapshots.meta_json.retracement_measurement_id` optional |
| Shared formulas | Reuse Phase 0 §5.4 math; single implementation in `profile_metrics.py` |

---

## 7. Proposed module layout (future)

```text
backend/analytics/   (or backend/detector/analytics/ — TBD at implementation)
  range_profile_engine.py    # orchestrate cohort profiling for date period
  range_profile_rules.py     # ABANDONED / RECLAIM / CONTINUATION decision tree
  profile_metrics.py         # deepest_reclaim, fib flags, candle counters
  profile_child_counts.py    # nested range counting before milestones
  profile_queries.py         # aggregate answers for §8 questions
```

**Execution model:**

```text
run_range_profile_analytics(
    symbol, structure_layer, source_timeframe,
    date_from, date_to,
    lookahead_bars=...,
) → list[RangeProfileSnapshot]   # writes to range_profile_snapshots only
```

Read-only against Layer 2. No calls to `run_detector_v1`.

---

## 8. Analytics questions this plan must answer

| # | Question | Query basis |
|---|----------|-------------|
| Q1 | How many ranges were abandoned? | `COUNT(*) WHERE range_profile = 'ABANDONED'` |
| Q2 | How many were never reclaimed? | `range_profile = 'NEVER_RECLAIMED'` |
| Q3 | How many shallow reclaimed then continued? | `SHALLOW_RECLAIM` + `continuation_confirmed = 1` |
| Q4 | How many deep reclaimed then continued? | `DEEP_RECLAIM` + `continuation_confirmed = 1` |
| Q5 | How many minors formed before major reclaim? | `number_of_child_ranges_before_reclaim` distribution (after derived hierarchy) |
| Q6 | How many minors formed before continuation? | `number_of_child_ranges_before_continuation` |
| Q7 | How many minors formed before failure? | `number_of_child_ranges_before_failure` |
| Q8 | What retracement depth is most common before continuation? | Histogram of `max_reclaim_percent` where `continuation_confirmed = 1` |
| Q9 | What profile has highest survival rate? | `CONTINUATION_SURVIVED / (CONTINUATION_SURVIVED + FAILED_CONTINUATION)` by profile subclass |

**Derived hierarchy questions (feeds `range_analytics_classifier`):**

- Which `UNKNOWN` ranges behave as containers (high child count + outermost span)?
- Do `DEEP_RECLAIM` profiles correlate with later `DERIVED_MAJOR` labels?

---

## 9. Processing pipeline (conceptual)

```text
1. SELECT confirmed map_ranges in [date_from, date_to]
     WHERE range_scale = 'UNKNOWN' (or all confirmed)
2. FOR each range R:
     a. Load candles from R.active_from_time → lookahead_end
     b. Find first BOS against R (from map_events or candle scan)
     c. If BOS: locate new_range_id, set bos_event_id
     d. Scan reclaim window → deepest_reclaim_price, max_reclaim_percent, fib flags
     e. Classify SHALLOW vs DEEP reclaim
     f. Scan continuation window → continuation_confirmed or failure_time
     g. Count child ranges before each milestone
     h. Assign primary range_profile
     i. INSERT range_profile_snapshots row
3. Emit aggregate report / API summary for §8
```

### 9.1 Reclaim detection (analytics-side)

Must align with locked HTF doctrine (close back inside **old** boundary after BOS):

- **Bullish BOS:** reclaim when `close <= old_RH` after break above `old_RH`
- **Bearish BOS:** reclaim when `close >= old_RL` after break below `old_RL`

Use same `break_rule` as detector for BOS detection consistency, but profile engine is **independent code path** (no import of suggestion emitters).

### 9.2 Continuation vs failure

| BOS direction | Continuation signal | Failure signal |
|---------------|--------------------|----------------|
| UP | New range holds; same-direction structural progress | Break **below** new range RL |
| DOWN | New range holds; same-direction structural progress | Break **above** new range RH |

---

## 10. Implementation phases (authorized only after plan acceptance)

| Phase | Deliverable | Detector touch |
|-------|-------------|----------------|
| **P0** | This plan + Josh review | None |
| **P1** | `range_profile_snapshots` schema migration | None |
| **P2** | `profile_metrics.py` — depth math + fib flags | None |
| **P3** | `range_profile_rules.py` — six profiles | None |
| **P4** | `range_profile_engine.py` — date-period batch | None |
| **P5** | `profile_queries.py` + smoke tests on fixture DB | None |
| **P6** | Wire `range_analytics_classifier` to read profiles + containment | None |
| **P7** | Optional Electron read-only profile panel | UI only |

---

## 11. Non-goals

- Changing detector thresholds or `RANGE_V2` lifecycle
- Auto-setting `range_scale` to MAJOR/MINOR on profile result
- Writing profiles into `map_ranges` as durable mapping truth
- Live trading signals or strategy labels
- Replacing `electron/python_analyst/` in first profile release

---

## 12. Open questions (Josh review)

| # | Question | Default proposal |
|---|----------|------------------|
| OQ1 | Lookahead window default for W1 vs D1? | Layer-specific bar counts (e.g. W1: 52 bars, D1: 126 bars) |
| OQ2 | `ABANDONED` vs `NEVER_RECLAIMED` — single bucket or strict split? | Split: `ABANDONED` requires explicit abandon signal or opposite BOS without reclaim; `NEVER_RECLAIMED` is lookahead timeout |
| OQ3 | 70% / 75% — measured from impulse leg or full old range width? | Impulse leg (new range after BOS), consistent with Phase 0 retracement |
| OQ4 | One profile per range or versioned re-profile on new data? | Versioned snapshots keyed by `profile_run_id`; latest wins for dashboards |
| OQ5 | Child count when parent_range_id unset? | Price-time containment graph over `UNKNOWN` ranges in same layer |

---

## 13. Acceptance criteria (plan complete)

- [x] Document created at `docs/architecture/RANGE_PROFILE_ANALYTICS_PLAN.md`
- [x] Six profiles defined with decision order
- [x] Full metrics list specified
- [x] Analytics questions mapped to query patterns
- [x] Detector explicitly out of scope
- [x] Major/minor deferred to derived classifier
- [ ] Josh review / plan acceptance
- [ ] Implementation phases authorized

---

## 14. References

- `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md` — reclaim after BOS, abandoned state
- `docs/architecture/RANGE_V2_IMPLEMENTATION_PLAN.md` §17 — generic detection + deferred hierarchy
- `docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md` §5 — retracement measurements
- `docs/architecture/PYTHON_ANALYST_V1_1_PLAN.md` — reclaim/abandon/outcome models (research alignment)
- `backend/detector/range_analytics_classifier.py` — derived hierarchy stub
