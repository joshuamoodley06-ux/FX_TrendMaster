# Phase 0: Detection Brain Contracts

**Status:** **LOCKED** — `PHASE_0_CONTRACTS_LOCKED = TRUE` (2026-06-17)  
**Schema version:** `detection_brain_v0`

> **Lock note:** No Phase 1+ schema work may violate these contracts without an explicit architecture revision documented in `docs/architecture/`.  
**Scope:** Lock database and event contracts before Phase 1 (suggestion storage) and Phase 2 (Python Detector V1).

---

## 0. Purpose and boundaries

### 0.1 What Phase 0 locks

This document defines contracts only. No Electron UI changes, no detector logic, no `main.tsx` refactors, and no migration scripts in this phase.

Phase 0 exists so Phase 1 and Phase 2 can be implemented without inventing parallel truth models.

### 0.2 Operating model (from doctrine)

```text
Python suggests  →  User approves / edits / rejects  →  Save final truth  →  Continue automatically
```

```text
Store facts first. Interpret later.
Detector suggests. Human confirms. Database stores truth. Analytics measures outcomes.
```

### 0.3 Hard restrictions (carry forward)

| Rule | Meaning |
|------|---------|
| Current timeframe only | Detector V1 inspects one `source_timeframe` per run. No multi-TF inference inside the detector. |
| No AI / ML | Deterministic OHLC rules only. |
| No live signals / auto-trading | Detection accelerates mapping; it does not trade. |
| No strategy interpretation in mapping tables | Mapping tables store structure facts, not trade plans. |
| Electron stays dumb for durable truth | Electron may display suggestions; it does not become the compiler of record. |

### 0.4 Relationship to existing systems

| System | Role in Detection Brain | Phase 0 action |
|--------|-------------------------|----------------|
| `raw_mapping_events` (`raw_mapping_v1`) | Append-only evidence locker for human/auto raw clicks | **Unchanged.** Still authoritative for raw event replay and processor input. |
| `map_ranges` / `map_events` | Confirmed structural truth after review | **Documented** as confirmed-structure target. New link fields defined here; columns added in Phase 1. |
| `electron/python_analyst/` | Post-confirmation statistics on saved structure | **Unchanged.** Reads confirmed facts; does not write suggestions. |
| `processor/` | Compiles raw ledger → structure (future) | **Unchanged.** Not part of Phase 0/1 detector path. |
| Electron `analyseHTFSemiAuto` | Legacy in-process detector | **Untouched in Phase 0.** Contract defines the target shape so Python can replace it in Phase 2+. |

### 0.5 Three-layer truth model

```text
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — SUGGESTIONS (non-authoritative, detector output)     │
│  detector_suggestions, ref_candle fields, retrace suggestions   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ user_action: APPROVE | EDIT | REJECT
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2 — CONFIRMED STRUCTURE (authoritative mapping truth)    │
│  map_ranges, map_events (+ optional raw_mapping_events mirror)  │
└───────────────────────────────┬─────────────────────────────────┘
                                │ analytics / research
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — MEASUREMENTS & RESEARCH (derived from confirmed)     │
│  retracement_measurements (factual), analyst reports, stats     │
└─────────────────────────────────────────────────────────────────┘
```

**Rule:** Suggestions never overwrite confirmed structure. Approval is an explicit promotion step.

### 0.6 Database placement

Logical split (per `.cursorrules` intent):

| Database | Contents |
|----------|----------|
| `raw_mapping_v159.db` | `raw_mapping_cases`, `raw_mapping_events` |
| `market_memory.db` (or unified VPS DB today) | `candles`, `map_ranges`, `map_events`, **new** detector tables |

**Phase 1 note:** New detector tables live alongside `map_ranges` in the market-memory database file. They are logically separate tables, not mixed into `map_ranges` rows until promotion.

**Canonical column:** `range_scale` (`MAJOR` \| `MINOR`). This is the contract name in all new tables and APIs. Phase 1 migration renames the existing `map_ranges.range_scope` column to `range_scale`. No alias — `range_scale` only.

---

## 1. Suggestion schema

### 1.1 Table: `detector_suggestions`

Non-authoritative detector output. One row per candidate presented to the user.

```sql
-- CONTRACT ONLY — not migrated in Phase 0
CREATE TABLE detector_suggestions (
    suggestion_id           TEXT PRIMARY KEY,          -- UUID v4
    schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',

    -- Detector provenance
    detector_version        TEXT NOT NULL,             -- e.g. RANGE_V1, BOS_V1
    engine_source           TEXT NOT NULL,             -- python_detector | electron_legacy
    candidate_kind          TEXT NOT NULL,             -- see §9.2
    candidate_index         INTEGER NOT NULL DEFAULT 0,  -- disambiguates multiple candidates in same window
    status                  TEXT NOT NULL DEFAULT 'PENDING',
    -- PENDING | APPROVED | REJECTED | EDITED | SUPERSEDED | EXPIRED

    -- Case / market context
    symbol                  TEXT NOT NULL,
    structure_layer         TEXT NOT NULL,             -- MACRO | WEEKLY | DAILY | INTRADAY
    source_timeframe        TEXT NOT NULL,             -- detector input TF (current TF only)
    chart_timeframe         TEXT NOT NULL,             -- UI chart TF (may equal source_timeframe)
    case_id                 INTEGER NULL,
    case_ref                TEXT NULL,
    raw_case_id             TEXT NULL,

    -- Structural context (nullable when not applicable)
    parent_range_id         INTEGER NULL,
    active_range_id         INTEGER NULL,
    old_range_id            INTEGER NULL,

    -- Anchor candle
    candle_time_utc_ms      INTEGER NOT NULL,
    candle_index            INTEGER NULL,

    -- Range suggestion fields (nullable unless candidate_kind = RANGE_*)
    suggested_rh            REAL NULL,
    suggested_rl            REAL NULL,
    suggested_rh_time_ms    INTEGER NULL,
    suggested_rl_time_ms    INTEGER NULL,
    suggested_rh_price_int  INTEGER NULL,
    suggested_rl_price_int  INTEGER NULL,
    price_scale             INTEGER NULL,
    range_scale             TEXT NULL,               -- MAJOR | MINOR
    range_role              TEXT NULL,               -- ACTIVE_CONTAINER | INTERNAL_LEG | EXPANSION_LEG
    internal_structure_status TEXT NULL,             -- HAS_MINORS | NO_MINOR_STRUCTURE | UNKNOWN

    -- Event suggestion fields (nullable unless candidate_kind = BOS | SWEEP | RECLAIM | SWING)
    event_side              TEXT NULL,               -- HIGH | LOW | UP | DOWN | REF | NONE
    event_price             REAL NULL,
    event_price_int         INTEGER NULL,
    break_rule              TEXT NULL,               -- WICK | BODY_CLOSE
    movement_rule           TEXT NULL,               -- stable rule id, e.g. STRUCTURE_BOS_UP
    primitive               TEXT NULL,               -- BREACH | SWEEP | RECLAIM | SWING | REF
    derived_event_code      TEXT NULL,               -- e.g. W1_BOS_UP

    -- Quality / explainability
    confidence              TEXT NOT NULL DEFAULT 'MEDIUM',  -- LOW | MEDIUM | HIGH
    reason_text             TEXT NOT NULL DEFAULT '',
    meta_json               TEXT NULL,               -- detector-specific payload; preserve unknown keys

    -- Review outcome (filled on user action)
    user_action             TEXT NULL,               -- APPROVE | EDIT | REJECT | SKIP
    reviewed_at_utc_ms      INTEGER NULL,
    reviewed_by             TEXT NOT NULL DEFAULT 'josh',

    -- Promotion linkage (filled when promoted to confirmed structure)
    promoted_range_id       INTEGER NULL,              -- map_ranges.id
    promoted_event_id       INTEGER NULL,            -- map_events.id
    promoted_raw_event_id   TEXT NULL,               -- raw_mapping_events.event_id

    -- Session / supersession
    session_id              TEXT NULL,
    supersedes_suggestion_id TEXT NULL,
    correction_id           TEXT NULL,

    created_at_utc_ms       INTEGER NOT NULL,
    updated_at_utc_ms       INTEGER NULL
);
```

**Indexes (Phase 1):**

```text
idx_detector_suggestions_case_status   (case_ref, status, candidate_kind)
idx_detector_suggestions_session       (session_id, status)
idx_detector_suggestions_candle        (symbol, source_timeframe, candle_time_utc_ms)
idx_detector_suggestions_active_range  (active_range_id, status)
```

### 1.2 Uniqueness constraint (anti-spam)

Autopilot must not create duplicate open suggestions for the same logical slot.

**Unique key dimensions:**

```text
symbol + source_timeframe + structure_layer + parent_range_id + candidate_kind + candidate_index
```

**Partial unique index (Phase 1):**

```sql
CREATE UNIQUE INDEX uq_detector_suggestions_open_slot
ON detector_suggestions (
    symbol,
    source_timeframe,
    structure_layer,
    COALESCE(parent_range_id, -1),
    candidate_kind,
    candidate_index
)
WHERE status = 'PENDING';
```

| Rule | Detail |
|------|--------|
| Scope | Applies only while `status = 'PENDING'`. Reviewed rows (`APPROVED`, `REJECTED`, `EDITED`, `SUPERSEDED`, `EXPIRED`) are excluded. |
| `candidate_index` | Zero-based index when one detector pass emits multiple candidates of the same `candidate_kind` in the same window (e.g. two swing highs). |
| `parent_range_id` | `NULL` coalesced to `-1` so root-level majors share one namespace. |
| On conflict | Supersede the existing `PENDING` row (`status = SUPERSEDED`) before inserting the replacement, or reject insert with audit warning. Never silently duplicate. |

### 1.3 Suggestion lifecycle rules

| Rule | Detail |
|------|--------|
| Immutability of detector output | Once written, `suggested_*` fields are not edited in place. User edits create `status = EDITED` and store final values in `detector_corrections` + promotion targets. |
| Supersession | New detector pass for the same `(active_range_id, candidate_kind, movement_rule, candle_time_utc_ms)` marks prior `PENDING` rows as `SUPERSEDED`. |
| Expiration | `EXPIRED` when replay moves past validity window (defined per detector in Phase 2; store `valid_until_candle_time_utc_ms` in `meta_json` for now). |
| No silent promotion | `APPROVED` alone does not create confirmed rows. Promotion requires explicit write to `map_ranges` / `map_events` / `raw_mapping_events` with back-links. |

### 1.4 Suggested vs final fields

| Field group | Lives on | Authoritative? |
|-------------|----------|----------------|
| `suggested_rh`, `suggested_rl`, `suggested_*` | `detector_suggestions` | No |
| `final_rh`, `final_rl` (doctrine language) | `map_ranges.range_high_price`, `map_ranges.range_low_price` after promotion | **Yes** |
| `suggested_range_scale`, `final_range_scale` | suggestion row → `map_ranges.range_scale` | Final only on `map_ranges` |
| `internal_structure_status` | promoted to `map_ranges.internal_structure_status` on MAJOR confirm | **Yes** on confirmed MAJOR |
| `user_action` | `detector_suggestions` + `detector_corrections` | Audit only |

---

## 2. Confirmed-structure schema

### 2.1 Authoritative tables

Confirmed structure remains in existing tables. Detection Brain adds **link-back fields** in Phase 1 (not Phase 0 migration).

#### `map_ranges` (confirmed range truth)

Existing columns retained. Phase 0 locks these as required semantic fields:

| Column | Type | Required semantics |
|--------|------|-------------------|
| `id` | INTEGER PK | Stable range id |
| `symbol` | TEXT | Instrument |
| `structure_layer` | TEXT | `MACRO` \| `WEEKLY` \| `DAILY` \| `INTRADAY` |
| `source_timeframe` | TEXT | Range mapping TF |
| `chart_timeframe` | TEXT | Chart TF used when saved |
| `range_high_price` / `range_low_price` | REAL | **Final RH/RL** (doctrine: `final_rh` / `final_rl`) |
| `range_high_time` / `range_low_time` | TEXT | Final anchor times (ISO-8601 UTC) |
| `range_scale` | TEXT | `MAJOR` \| `MINOR` |
| `range_role` | TEXT | **NEW Phase 1:** `ACTIVE_CONTAINER` \| `INTERNAL_LEG` \| `EXPANSION_LEG` |
| `internal_structure_status` | TEXT | **NEW Phase 1:** `HAS_MINORS` \| `NO_MINOR_STRUCTURE` \| `UNKNOWN` |
| `parent_range_id` | INTEGER NULL | MINOR → parent MAJOR; lower-TF MAJOR → higher-TF MINOR |
| `old_range_id` / `new_range_id` | INTEGER NULL | BOS transition linkage |
| `created_by_event_id` | INTEGER NULL | Event that created this range |
| `broken_by_event_id` | INTEGER NULL | Event that broke this range |
| `status` | TEXT | `ACTIVE` \| `BROKEN` \| `ABANDONED` \| `INACTIVE` |
| `direction_of_break` | TEXT | `UP` \| `DOWN` \| NULL |
| `active_from_time` / `inactive_from_time` | TEXT | Visibility window |
| `case_id` / `case_ref` / `raw_case_id` | mixed | Case filtering |
| `structure_version` | TEXT | Structural ruleset id at save time |
| `meta_json` | TEXT | Non-authoritative overflow |

**Phase 1 additions (contracted now, migrated later):**

| New column | Type | Purpose |
|------------|------|---------|
| `confirmed_from_suggestion_id` | TEXT NULL | FK → `detector_suggestions.suggestion_id` |
| `detector_version_at_confirm` | TEXT NULL | e.g. `RANGE_V1` |
| `user_action_at_confirm` | TEXT NULL | `APPROVE` \| `EDIT` |

#### `map_events` (confirmed event truth)

| Column | Semantics |
|--------|-----------|
| `event_type` / `structural_event` | Canonical structural event name |
| `derived_event_code` | Stable code (e.g. `W1_BOS_UP`) |
| `movement_rule` | Stable rule id (e.g. `STRUCTURE_BOS_UP`) |
| `active_range_id` / `parent_range_id` | Range context |
| `old_range_id` / `new_range_id` | Transition context |
| `event_time` / `event_price` | Market-time key |
| `candle_open/high/low/close` | OHLC at event candle |
| `calculation_engine_version` | Analytics engine version (existing) |
| `logic_version` | **Maps to `detector_version`** for auto-detected events |
| `candidate_id` | **Maps to `suggestion_id`** for promoted suggestions |
| `engine_source` | **Required.** `python_detector` \| `electron_legacy` \| `manual` \| `import` |
| `candidate_status` | `ACCEPTED` \| `REJECTED` \| `EDITED` — for audit rows only |

**`engine_source` labelling rules (mandatory):**

| Value | When |
|-------|------|
| `python_detector` | Any suggestion or auto-event produced by Python Detector V1+ |
| `electron_legacy` | Any output from `analyseHTFSemiAuto` until retirement |
| `manual` | Direct user mapping with no detector pass |
| `import` | Bulk import |

Never store Python and legacy suggestions without `engine_source`. Research and correction stats depend on this separation.

**Phase 1 additions:**

| New column | Purpose |
|------------|---------|
| `confirmed_from_suggestion_id` | TEXT NULL → `detector_suggestions` |
| `detector_version_at_confirm` | TEXT NULL |

#### `raw_mapping_events` (raw evidence mirror)

When a confirmed event originates from detector review, optionally mirror to raw ledger:

| Raw event type | When |
|----------------|------|
| `SET_ANCHOR` / `SET_INITIAL_ANCHOR` / `ADJUST_ANCHOR` | RH/RL confirmation |
| `AUTO_BOS` | Auto-detected BOS after confirmed RH/RL |
| `MANUAL_BOS` | User-edited BOS |
| `RECLAIM` | Confirmed reclaim |
| `NOTE` | Ref candle notes, audit annotations |

`raw_payload_json` must include:

```json
{
  "semantic_side": "HIGH|LOW|UP|DOWN|REF|NONE",
  "suggestion_id": "<uuid>",
  "detector_version": "BOS_V1",
  "user_action": "APPROVE|EDIT|REJECT",
  "promoted_from": "detector_suggestions"
}
```

### 2.2 Major / minor confirmation rules

| Rule | Detail |
|------|--------|
| MAJOR | Active structural container for the timeframe. |
| MINOR | Internal leg inside a MAJOR container. Requires `parent_range_id` → MAJOR parent. |
| Major reset | When a MINOR breaks and confirms beyond the MAJOR boundary, the MAJOR resets (new MAJOR range; old MAJOR → `BROKEN`). |
| Expansion leg | `range_role = EXPANSION_LEG` when price travels Major boundary → Major boundary without clean minors. |
| No minor structure | `internal_structure_status = NO_MINOR_STRUCTURE` when a MAJOR completes with no clean minors. This is a **valid stored fact**, not missing data. |
| Has minors | `internal_structure_status = HAS_MINORS` when one or more MINOR ranges exist inside the MAJOR. |
| Unknown | `internal_structure_status = UNKNOWN` until minor detection pass completes or user declares outcome. |
| Expansion path | When user or detector confirms expansion-only movement: set `range_role = EXPANSION_LEG` + `internal_structure_status = NO_MINOR_STRUCTURE`, skip minor review, proceed to `AUTO_BOS`. |

### 2.3 Nested resolution order (autopilot target)

```text
Weekly MAJOR
  → Weekly MINOR(s)
    → Daily MAJOR inside Weekly MINOR
      → Daily MINOR(s)
        → Intraday MAJOR inside Daily MINOR
          → Intraday MINOR(s)
            → Micro CHoCH / first-break only
              → Return to parent
```

### 2.4 Promotion contract (suggestion → confirmed)

```text
1. User submits user_action on detector_suggestions
2. If APPROVE or EDIT:
   a. Write map_ranges and/or map_events (and raw_mapping_events if applicable)
   b. Set confirmed_from_suggestion_id on confirmed rows
   c. Set detector_suggestions.status and promotion_* ids
   d. Write detector_corrections row
3. If REJECT:
   a. Set detector_suggestions.status = REJECTED
   b. Write detector_corrections row
   c. Do NOT write map_ranges / map_events
```

---

## 3. Detector version contract

### 3.1 Version string format

```text
{DOMAIN}_V{integer}
```

| Domain | Example | Owns |
|--------|---------|------|
| `RANGE` | `RANGE_V1` | Swing/range candidate detection (bootstrap only — see §3.5) |
| `SWING` | `SWING_V1` | Swing pivot candidates |
| `BOS` | `BOS_V1` | Break of structure |
| `SWEEP` | `SWEEP_V1` | Liquidity sweep |
| `RECLAIM` | `RECLAIM_V1` | Reclaim after sweep/BOS |
| `REF_CANDLE` | `REF_CANDLE_V1` | Ref candle candidates |
| `RETRACE` | `RETRACE_V1` | Retracement into old range |
| `PROFILE` | `PROFILE_V1` | S&R / S&D classification |
| `WORKFLOW` | `WORKFLOW_V1` | Guided workflow state machine |

**Bundle example (session):** `{"RANGE":"RANGE_V1","BOS":"BOS_V1","RETRACE":"RETRACE_V1"}`

### 3.2 Version rules

| Rule | Detail |
|------|--------|
| Mandatory on suggestions | Every `detector_suggestions` row has `detector_version`. |
| Mandatory on auto-events | Every auto-saved `map_events` / `raw_mapping_events` from detector carries version in `logic_version` / payload. |
| Monotonic per domain | `RANGE_V1` → `RANGE_V2` only when rules change materially. |
| No silent cross-domain reuse | BOS detector bump does not imply RANGE bump unless documented. |
| Legacy mapping | Electron `logic_version` values map forward to `detector_version` until Python replaces in-process detection. |

### 3.3 RANGE detector doctrine (V1 vs V2)

**`RANGE_V1` is non-doctrinal** and retained only for detector-loop smoke testing (suggestion → review → promotion → corrections). It pairs latest swing high + latest swing low and must **not** be improved through threshold tuning or treated as final range doctrine.

**`RANGE_V2` doctrine is LOCKED** — `RANGE_V2_DOCTRINE_LOCKED = TRUE` (2026-06-17). See `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md`. Event-driven sequence: existing range or seed anchors → BOS → reclaim → opposite swing boundary → range suggestion.

**`RANGE_V2` code is not authorized yet.** Prerequisite order (§11.3 of doctrine contract): (1) replay-context bug fix, (2) Review Candidate compact/collapsible UI fix, (3) implementation plan, (4) code.

### 3.4 Optional registry table (Phase 1)

```sql
CREATE TABLE detector_version_registry (
    detector_version    TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,
    major_number        INTEGER NOT NULL,
    release_notes       TEXT NOT NULL DEFAULT '',
    rule_summary_json   TEXT NULL,
    supersedes_version  TEXT NULL,
    created_at_utc_ms   INTEGER NOT NULL
);
```

### 3.5 Improvement loop (Phase 8 target, contracted now)

```text
User correction logged → error_category recorded → rules adjusted manually
→ detector_version incremented → future mappings use new version only
```

Corrections never rewrite historical `detector_version` on old rows.

---

## 4. Correction log contract

### 4.1 Table: `detector_corrections`

Append-only audit of every approve / edit / reject.

```sql
CREATE TABLE detector_corrections (
    correction_id           TEXT PRIMARY KEY,          -- UUID v4
    schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',

    suggestion_id           TEXT NOT NULL,             -- FK → detector_suggestions
    session_id              TEXT NULL,

    -- What was reviewed
    candidate_kind          TEXT NOT NULL,
    detector_version        TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    structure_layer         TEXT NOT NULL,
    source_timeframe        TEXT NOT NULL,

    -- User outcome
    user_action             TEXT NOT NULL,             -- APPROVE | EDIT | REJECT | SKIP
    error_category          TEXT NOT NULL,             -- required on every logged review; see §4.2
    notes                   TEXT NOT NULL DEFAULT '',

    -- Snapshots (immutable JSON at review time)
    suggested_snapshot_json TEXT NOT NULL,
    final_snapshot_json     TEXT NULL,                 -- populated on APPROVE/EDIT

    -- Promotion result
    promoted_range_id       INTEGER NULL,
    promoted_event_id       INTEGER NULL,
    promoted_raw_event_id   TEXT NULL,

    created_at_utc_ms       INTEGER NOT NULL
);
```

### 4.2 Error categories (closed enum)

| `error_category` | When to use |
|------------------|-------------|
| `NO_ERROR` | **Required on `APPROVE`.** Detector got it right; logs clean approvals for improvement stats. |
| `MISSED_SWING` | Detector failed to propose a swing user expected |
| `FALSE_SWING` | Detector proposed a swing that should not exist |
| `WRONG_BOS` | BOS candidate wrong (direction, candle, or rule) |
| `MISSED_RECLAIM` | Reclaim not proposed |
| `FALSE_RECLAIM` | Reclaim proposed incorrectly |
| `WRONG_RH` | Range high wrong |
| `WRONG_RL` | Range low wrong |
| `MAJOR_MINOR_ERROR` | Wrong scope (Major vs Minor) or parent linkage |
| `WRONG_REF_CANDLE` | Ref candle candidate wrong type or location |
| `WRONG_PROFILE` | S&R / S&D classification wrong |
| `OTHER` | Explicit notes required |

### 4.3 Correction rules

| Rule | Detail |
|------|--------|
| Append-only | Never update or delete correction rows. |
| Always write on review | Every `user_action` except `SKIP` creates a correction row. |
| `APPROVE` | Must set `error_category = NO_ERROR`. Keeps approval rate and error rate statistically separable. |
| `EDIT` / `REJECT` | Must set a non-`NO_ERROR` category from §4.2. |
| `SKIP` | No correction row; suggestion may become `EXPIRED`. |
| Research use | Corrections feed manual rule patches and version bumps; not auto-training in V1. |

---

## 5. Retracement measurement contract

### 5.1 Purpose

Store **factual** retracement-into-old-range data after BOS. Distinct from analyst CSV reports: this is durable structure evidence for mapping and later statistics.

### 5.2 Table: `retracement_measurements`

```sql
CREATE TABLE retracement_measurements (
    measurement_id          TEXT PRIMARY KEY,          -- UUID v4
    schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',
    detector_version        TEXT NOT NULL,             -- RETRACE_V1, PROFILE_V1
    measurement_status      TEXT NOT NULL DEFAULT 'SUGGESTED',
    -- SUGGESTED | CONFIRMED | REJECTED

    -- Linkage
    case_ref                TEXT NULL,
    case_id                 INTEGER NULL,
    old_range_id            INTEGER NOT NULL,
    new_range_id            INTEGER NOT NULL,
    bos_event_id            INTEGER NOT NULL,            -- map_events.id
    suggestion_id           TEXT NULL,                 -- if originated as suggestion
    session_id              TEXT NULL,

    -- Context
    symbol                  TEXT NOT NULL,
    structure_layer         TEXT NOT NULL,
    source_timeframe        TEXT NOT NULL,
    bos_direction           TEXT NOT NULL,             -- UP | DOWN

    -- Retracement direction (into old range)
    retracement_direction   TEXT NOT NULL,             -- INTO_OLD_RANGE_UP | INTO_OLD_RANGE_DOWN
    old_range_boundary_touched TEXT NOT NULL,          -- HIGH | LOW | BOTH | NONE

    -- Measurement window
    retrace_start_time_ms   INTEGER NOT NULL,
    retrace_end_time_ms     INTEGER NULL,
    retrace_high            REAL NULL,
    retrace_low             REAL NULL,
    deepest_retrace_price   REAL NULL,                 -- deepest price into old range
    max_retrace_percent     REAL NULL,                 -- 0.0–1.0+ ; peak depth in window
    retrace_depth_percent   REAL NULL,                 -- alias of max_retrace_percent at confirm time

    -- Level respect / breach flags
    respected_level         REAL NULL,                 -- price level that held (if any)
    breached_618            INTEGER NOT NULL DEFAULT 0,
    breached_70             INTEGER NOT NULL DEFAULT 0,
    breached_75             INTEGER NOT NULL DEFAULT 0,

    -- Profile (factual classification)
    profile_classification  TEXT NULL,                 -- S_AND_R | S_AND_D | UNRESOLVED

    meta_json               TEXT NULL,
    user_action             TEXT NULL,                 -- APPROVE | EDIT | REJECT
    reviewed_at_utc_ms      INTEGER NULL,
    created_at_utc_ms       INTEGER NOT NULL,
    updated_at_utc_ms       INTEGER NULL
);
```

### 5.3 Retracement direction semantics

| `retracement_direction` | Meaning |
|-------------------------|---------|
| `INTO_OLD_RANGE_UP` | After bullish BOS, price retraces downward into the old range body |
| `INTO_OLD_RANGE_DOWN` | After bearish BOS, price retraces upward into the old range body |

| `old_range_boundary_touched` | Meaning |
|------------------------------|---------|
| `HIGH` | Retrace touched old range high boundary only |
| `LOW` | Retrace touched old range low boundary only |
| `BOTH` | Retrace touched both boundaries |
| `NONE` | No boundary touch recorded in measurement window |

### 5.4 Measurement formulas

**Bullish BOS (`retracement_direction = INTO_OLD_RANGE_UP`):**

```text
impulse_high = new_range.range_high_price
impulse_low  = new_range.range_low_price
deepest_retrace_price = lowest low between retrace_start and retrace_end
max_retrace_percent = (impulse_high - deepest_retrace_price) / (impulse_high - impulse_low)
```

**Bearish BOS (`retracement_direction = INTO_OLD_RANGE_DOWN`):**

```text
deepest_retrace_price = highest high in retrace window
max_retrace_percent = (deepest_retrace_price - impulse_low) / (impulse_high - impulse_low)
```

At confirm time, `retrace_depth_percent` is set equal to `max_retrace_percent`.

**Profile thresholds (contracted):**

| Profile | Conditions |
|---------|------------|
| `S_AND_R` | Shallow retrace; respects ~70%; `breached_70 = 0` or marginal; structure continues |
| `S_AND_D` | Deep retrace; `breached_618 = 1`; often breaches 70–75%; mitigation then continuation |
| `UNRESOLVED` | Insufficient data or conflicting signals |

### 5.5 Lifecycle

```text
BOS confirmed → detector proposes retracement_measurement (SUGGESTED)
→ user APPROVE/EDIT/REJECT → CONFIRMED or REJECTED
→ CONFIRMED rows are factual inputs for analyst/research
```

---

## 6. Ref candle candidate contract

### 6.1 Scope

Ref candles are **candidates**, not ranges. They do not create `map_ranges` rows until separately confirmed as structural anchors (if ever).

### 6.2 Storage

Primary storage: `detector_suggestions` with `candidate_kind = REF_CANDLE`.

Optional denormalized view fields in `meta_json`:

```json
{
  "ref_candle_type": "SWEEP_OHCL | SWEEP_BEARISH_ENGULF | BEARISH_ENGULF_ONLY | OHCL_MANIPULATION_ONLY",
  "ref_role": "REF_CANDLE_CANDIDATE",
  "sweep_level_price": 2650.50,
  "sweep_candle_time_ms": 1735689600000,
  "engulf_candle_time_ms": 1735693200000,
  "bos_event_id": 12345,
  "parent_range_id": 678,
  "ohcl_pattern": "bearish_manipulation"
}
```

### 6.3 Ref candle types (closed enum)

| `ref_candle_type` | Definition |
|-------------------|------------|
| `SWEEP_OHCL` | Sweep of previous high/low with OHCL manipulation behavior |
| `SWEEP_BEARISH_ENGULF` | Sweep plus bearish engulfing confirmation |
| `BEARISH_ENGULF_ONLY` | Bearish engulf without prior sweep |
| `OHCL_MANIPULATION_ONLY` | OHCL manipulation without sweep/engulf |

### 6.4 Rules

| Rule | Detail |
|------|--------|
| No range creation | `REF_CANDLE` suggestions must not auto-create `map_ranges`. |
| Promotion | Approval may write `map_events` and/or `raw_mapping_events` with `semantic_side: REF` and/or `NOTE`. |
| Search window | Detector searches **after BOS** within configurable lookback (stored in `meta_json`). |
| Termination research | `retracement_measurements` and ref candle rows link for “what ref candles terminate retraces” queries (Phase 9). |

---

## 7. Session persistence contract

### 7.1 Table: `mapping_sessions`

Durable resume state for guided mapping.

```sql
CREATE TABLE mapping_sessions (
    session_id              TEXT PRIMARY KEY,          -- UUID v4
    schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',

    -- Identity
    symbol                  TEXT NOT NULL,
    case_id                 INTEGER NULL,
    case_ref                TEXT NULL,
    raw_case_id             TEXT NULL,

    -- Layer / timeframe
    structure_layer         TEXT NOT NULL,
    source_timeframe        TEXT NOT NULL,
    chart_timeframe         TEXT NOT NULL,

    -- Replay position
    replay_candle_time_utc_ms INTEGER NULL,
    replay_candle_index     INTEGER NULL,

    -- Active structural pointers
    current_parent_range_id INTEGER NULL,
    current_active_range_id INTEGER NULL,
    current_old_range_id    INTEGER NULL,

    -- Workflow
    workflow_mode           TEXT NOT NULL DEFAULT 'GUIDED',
    -- GUIDED | MANUAL | AUTOPILOT_PAUSED
    autopilot_step          TEXT NULL,                 -- see §8.2
    target_range_scale      TEXT NOT NULL DEFAULT 'MAJOR',
    internal_structure_status TEXT NULL,             -- HAS_MINORS | NO_MINOR_STRUCTURE | UNKNOWN
    path_outcome            TEXT NULL,                 -- see §8.6; includes NO_MINOR_STRUCTURE

    -- Active review
    active_suggestion_id    TEXT NULL,
    active_candidate_kind   TEXT NULL,

    -- Detector bundle at session start/resume
    detector_versions_json  TEXT NOT NULL DEFAULT '{}',

    -- Overflow for UI-specific ephemeral state
    state_json              TEXT NULL,

    status                  TEXT NOT NULL DEFAULT 'ACTIVE',
    -- ACTIVE | PAUSED | COMPLETED | ARCHIVED

    created_at_utc_ms       INTEGER NOT NULL,
    updated_at_utc_ms       INTEGER NULL,
    last_resumed_at_utc_ms  INTEGER NULL
);
```

### 7.2 Required `state_json` keys (when present)

| Key | Type | Purpose |
|-----|------|---------|
| `range_high` / `range_low` | number | Draft range under review |
| `range_window` | `{start,end}` | Active candle window |
| `rejected_suggestion_ids` | string[] | Session-local rejects |
| `accepted_movement_rules` | string[] | Locks synced from legacy HTF semi-auto |
| `htf_legacy_snapshot` | object | Bridge until Python detector replaces Electron detection |

### 7.3 Electron local storage (ephemeral until Phase 6 sync)

Existing keys remain valid during transition. Phase 6 must map them into `mapping_sessions`:

| localStorage key | Maps to |
|------------------|---------|
| `fx_tm_range_scope_v1` (legacy key name) | `target_range_scale` |
| `fx_tm_htf_accepted_suggestion_locks_v087_16` | `state_json.accepted_movement_rules` |
| Case/replay keys in `main.tsx` | `replay_candle_*`, `case_ref` |

**Rule:** localStorage is UI cache only. `mapping_sessions` is durable resume truth.

### 7.4 Session rules

| Rule | Detail |
|------|--------|
| One active session per `(symbol, case_ref, structure_layer)` recommended | Avoid parallel conflicting workflows. |
| Resume | Reload pointers + `active_suggestion_id` + `autopilot_step` + replay position. |
| Archive | On case complete or explicit user archive; no hard delete. |

---

## 8. Guided workflow state contract

### 8.1 Workflow modes

| `workflow_mode` | Meaning |
|-----------------|---------|
| `GUIDED` | Python suggests; user reviews each candidate |
| `MANUAL` | User maps without detector suggestions (legacy path) |
| `AUTOPILOT_PAUSED` | Autopilot sequence halted mid-step awaiting user |

### 8.2 Autopilot steps (`autopilot_step`)

```text
DETECT_MAJOR
REVIEW_MAJOR
DETECT_MINORS
REVIEW_MINOR
NO_MINOR_STRUCTURE
AUTO_BOS
MEASURE_RETRACE
CLASSIFY_PROFILE
DETECT_REF_CANDLE
REVIEW_REF_CANDLE
COMPLETE_LAYER
DROP_TIMEFRAME
RETURN_PARENT
DONE
```

### 8.3 State machine

```text
                    ┌──────────────┐
                    │    IDLE      │
                    └──────┬───────┘
                           │ start / resume
                           ▼
                    ┌──────────────┐
               ┌───│ DETECT_MAJOR │───┐
               │   └──────┬───────┘   │
               │          ▼           │
               │   ┌──────────────┐   │
               │   │ REVIEW_MAJOR │   │
               │   └──────┬───────┘   │
               │     approve/edit     │
               │          ▼           │
               │   ┌──────────────┐   reject → log correction → re-detect
               │   │ DETECT_MINORS│
               │   └──────┬───────┘
               │    no clean minors
               │          ├──────────────────────┐
               │          ▼                      ▼
               │   ┌──────────────┐    ┌───────────────────┐
               │   │ REVIEW_MINOR │    │ NO_MINOR_STRUCTURE │  (valid path outcome)
               │   └──────┬───────┘    └─────────┬─────────┘
               │          │ more minors          │ store fact:
               │          │ approve              │ internal_structure_status
               │          ▼                      │ = NO_MINOR_STRUCTURE
               │   ┌──────────────┐              │
               │   │   AUTO_BOS   │◄─────────────┘
               │   └──────┬───────┘
               │          ▼
               │   ┌────────────────┐
               │   │ MEASURE_RETRACE│
               │   └──────┬─────────┘
               │          ▼
               │   ┌─────────────────┐
               │   │ CLASSIFY_PROFILE│
               │   └──────┬──────────┘
               │          ▼
               │   ┌──────────────────┐
               │   │ DETECT_REF_CANDLE │
               │   └──────┬───────────┘
               │          ▼
               │   ┌───────────────────┐
               │   └ REVIEW_REF_CANDLE │
               │          │
               │          ▼
               │   ┌──────────────┐
               │   │COMPLETE_LAYER│
               │   └──────┬───────┘
               │          ▼
               │   ┌───────────────┐
               └──►│ DROP_TIMEFRAME│──► RETURN_PARENT ──► DONE
                   └───────────────┘
```

### 8.4 Transition rules

| Event | Next step |
|-------|-----------|
| Major approved | `DETECT_MINORS` |
| Minors found | `REVIEW_MINOR` → on approve, loop or `AUTO_BOS` |
| No clean minors detected / user confirms expansion | `NO_MINOR_STRUCTURE` → set `internal_structure_status = NO_MINOR_STRUCTURE` on MAJOR, `path_outcome = NO_MINOR_STRUCTURE`, then `AUTO_BOS` |
| Minor approved | `REVIEW_MINOR` if more minors queued, else `AUTO_BOS` |
| BOS auto-saved | `MEASURE_RETRACE` |
| Retrace confirmed | `CLASSIFY_PROFILE` |
| Profile confirmed | `DETECT_REF_CANDLE` |
| Ref approved/rejected | `COMPLETE_LAYER` |
| Layer complete + child TF exists | `DROP_TIMEFRAME` |
| Layer complete + no child TF | `RETURN_PARENT` |
| User pause | `workflow_mode = AUTOPILOT_PAUSED`; preserve `autopilot_step` |

### 8.5 Review panel actions (Phase 3 UI — contracted only)

| Action | `user_action` | Effect |
|--------|---------------|--------|
| Approve | `APPROVE` | Promote to confirmed structure |
| Edit | `EDIT` | Promote with edited values |
| Reject | `REJECT` | Log correction; no promotion |
| Save Final | `APPROVE` or `EDIT` | Alias of promote + continue |
| Next Candidate | `SKIP` or auto-advance | Move to next `PENDING` suggestion |

### 8.6 Path outcomes (`path_outcome`)

Valid workflow outcomes stored on `mapping_sessions` and promoted to `map_ranges.internal_structure_status` where applicable.

| `path_outcome` | Stored fact | Next step |
|----------------|-------------|-----------|
| `HAS_MINORS` | MAJOR contains confirmed MINOR ranges | Continue minor review or `AUTO_BOS` |
| `NO_MINOR_STRUCTURE` | MAJOR completed with expansion only; no clean minors | `AUTO_BOS` (not a failure state) |
| `UNKNOWN` | Minor detection not yet run or inconclusive | `DETECT_MINORS` |

**Rule:** `NO_MINOR_STRUCTURE` must never be stored as NULL, empty, or implied by absence of rows. It is an explicit affirmative outcome.

---

## 9. Event naming and types contract

### 9.1 Three namespaces (do not mix)

| Namespace | Storage | Purpose |
|-----------|---------|---------|
| **A. Raw ledger types** | `raw_mapping_events.event_type` | Append-only evidence |
| **B. Detector candidate kinds** | `detector_suggestions.candidate_kind` | Non-authoritative suggestions |
| **C. Confirmed structural codes** | `map_events.derived_event_code`, `movement_rule` | Authoritative interpreted events |

### 9.2 Detector `candidate_kind` (closed enum)

```text
RANGE_MAJOR
RANGE_MINOR
SWING_HIGH
SWING_LOW
BOS_UP
BOS_DOWN
SWEEP_HIGH
SWEEP_LOW
RECLAIM_UP
RECLAIM_DOWN
REF_CANDLE
RETRACE_MEASUREMENT
PROFILE_CLASSIFICATION
```

### 9.3 Raw ledger event types (unchanged — do not extend without approval)

```text
SET_INITIAL_ANCHOR
SET_ANCHOR
ADJUST_ANCHOR
MANUAL_BOS
AUTO_BOS
RECLAIM
ABANDON_RANGE
DELETE_RECORD
NOTE
```

**Semantic sides** (in `raw_payload_json.semantic_side`):

```text
HIGH | LOW | REF | UP | DOWN | NONE
```

**Backend-safe sides** (`raw_mapping_events.event_side`):

```text
HIGH | LOW | NONE
```

### 9.4 Confirmed structural `movement_rule` ids

Stable ids for promotion and correction logging:

| `movement_rule` | `derived_event_code` | `candidate_kind` |
|-----------------|------------------------|------------------|
| `STRUCTURE_BOS_UP` | `{TF}_BOS_UP` | `BOS_UP` |
| `STRUCTURE_BOS_DOWN` | `{TF}_BOS_DOWN` | `BOS_DOWN` |
| `STRUCTURE_RECLAIM_UP` | `{TF}_RECLAIM_UP` | `RECLAIM_UP` |
| `STRUCTURE_RECLAIM_DOWN` | `{TF}_RECLAIM_DOWN` | `RECLAIM_DOWN` |
| `STRUCTURE_SWEEP_HIGH` | `{TF}_SWEEP_HIGH` | `SWEEP_HIGH` |
| `STRUCTURE_SWEEP_LOW` | `{TF}_SWEEP_LOW` | `SWEEP_LOW` |
| `STRUCTURE_RANGE_MAJOR` | `{TF}_RANGE_MAJOR` | `RANGE_MAJOR` |
| `STRUCTURE_RANGE_MINOR` | `{TF}_RANGE_MINOR` | `RANGE_MINOR` |
| `STRUCTURE_SWING_HIGH` | `{TF}_SWING_HIGH` | `SWING_HIGH` |
| `STRUCTURE_SWING_LOW` | `{TF}_SWING_LOW` | `SWING_LOW` |
| `STRUCTURE_REF_CANDLE` | `{TF}_REF_CANDLE` | `REF_CANDLE` |

`{TF}` = timeframe prefix (`W1`, `D1`, `H4`, `H1`, `M15`, `M5`, `M1`).

### 9.5 BOS break rules by timeframe

| Timeframe group | `break_rule` | Raw event on confirm |
|-----------------|--------------|----------------------|
| Weekly, Daily, H4, H1 | `WICK` | `AUTO_BOS` (or `MANUAL_BOS` if edited) |
| M15, Micro | `BODY_CLOSE` | `AUTO_BOS` (or `MANUAL_BOS` if edited) |

### 9.6 `engine_source` values (mandatory labelling)

Every `detector_suggestions` row and every auto-saved `map_events` row must carry `engine_source`.

```text
python_detector     -- Python Detector V1+ output (suggestions and promotions)
electron_legacy     -- analyseHTFSemiAuto output until retirement
manual              -- direct user mapping without detector
import              -- bulk import
```

**Separation rule:** Python V1 suggestions (`engine_source = python_detector`) and legacy Electron semi-auto output (`engine_source = electron_legacy`) must never be mixed in queries, stats, or correction loops without explicit filtering.

### 9.7 Display aliases (UI only — never stored as primary keys)

| Display label | Canonical |
|---------------|-----------|
| `RANGE_HIGH` / `RANGE_LOW` | `SET_ANCHOR` + `semantic_side` |
| `BOS_UP` / `BOS_DOWN` | `AUTO_BOS` / `MANUAL_BOS` + `bos_direction` |
| `RECLAIM_UP` / `RECLAIM_DOWN` | `RECLAIM` + semantic side |

---

## 10. Phase status

**Phase 0:** `PHASE_0_CONTRACTS_LOCKED = TRUE` (2026-06-17)

**Phase 1:** Storage foundations (migrations + backend helpers). No detector logic, no Electron UI.

**Phase 2:** Python Detector V1 — writes `detector_suggestions` only (`backend/detector/`).

**Phase 3:** Electron Review Candidate Panel + promotion API — suggest → decide → save truth.

**Phase 3.5:** Detector performance measurement — `backend/detector_performance.py`; source of truth `detector_corrections`; analytics view `v_detector_correction_facts`; CLI scorecard + Guided Workflow Engine readiness gates (measurement only).

**Phase 4 (future):** Guided Workflow Engine — machine suggests/navigates; human confirms. Not autopilot.

### Phase 0 acceptance checklist

- [x] Josh confirms three-layer truth model
- [x] `range_scale` canonical (`MAJOR` \| `MINOR`); Phase 1 renames legacy `range_scope`
- [x] `NO_MINOR_STRUCTURE` valid path outcome
- [x] `internal_structure_status` on MAJOR ranges
- [x] Suggestion table shape + uniqueness constraint accepted
- [x] Promotion flow (suggestion → map_ranges/map_events/raw) accepted
- [x] Correction categories incl. `NO_ERROR` on approve accepted
- [x] Retracement direction + boundary fields accepted
- [x] `engine_source` labelling (`python_detector` \| `electron_legacy`) accepted
- [x] Session + workflow state machine accepted
- [x] Raw ledger event types remain unchanged
- [x] BOS break rules match trading doctrine

**Phase 2 delivered:** `backend/detector/` (see `backend/detector/main.py`).

**Phase 3 delivered:** Review Candidate panel + `detection_brain_promotion.py` + `/api/v1/detection-brain/*`.

**Phase 3.5 delivered:** `detector_performance.py` — approval/edit/rejection rates by version, kind, timeframe, layer, scale; error category analysis; health summary; Guided Workflow readiness thresholds.

---

## 11. Document index

| § | Contract |
|---|----------|
| 1 | Suggestion schema → `detector_suggestions` (+ uniqueness §1.2) |
| 2 | Confirmed-structure schema → `map_ranges`, `map_events`, `raw_mapping_events` |
| 3 | Detector version contract → `detector_version`, registry |
| 4 | Correction log contract → `detector_corrections` |
| 5 | Retracement measurement contract → `retracement_measurements` |
| 6 | Ref candle candidate contract → `candidate_kind = REF_CANDLE` + `meta_json` |
| 7 | Session persistence contract → `mapping_sessions` |
| 8 | Guided workflow state contract → `workflow_mode`, `autopilot_step`, `path_outcome`, state machine |
| 9 | Event naming/types contract → raw vs candidate vs confirmed namespaces |

---

## 12. References

- `docs/architecture/ARCHITECTURE_LOCK.md` — raw ledger doctrine
- `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md` — RANGE_V2 event-driven range doctrine (**LOCKED** 2026-06-17)
- `docs/architecture/RANGE_V2_IMPLEMENTATION_PLAN.md` — RANGE_V2 coding plan (pending review)
- `project rules.md` — solo-user, strong structural storage
- `electron/src/rawMapping.ts` — raw event types and payload rules
- `backend/candle_store.py` — existing `map_ranges` / `map_events` / `raw_mapping_events`
- `electron/python_analyst/analyst/models/records.py` — analyst read models
- Detection Brain Doctrine (2026) — source requirements document
