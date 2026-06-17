# RANGE_V2 Doctrine Contract

**Status:** **LOCKED** — `RANGE_V2_DOCTRINE_LOCKED = TRUE` (2026-06-17)  
**Schema version:** `detection_brain_v0` (unchanged)  
**Scope:** Doctrine and contract only. No detector code, no Electron UI, no threshold tuning.

> **Implementation gate:** Doctrine is locked. `RANGE_V2` code must not start until prerequisite fixes (§11.3) are complete and an implementation plan is reviewed.

---

## 1. Verdict

A valid FX TrendMaster range is **not** generally defined as:

```text
latest swing high + latest swing low
```

That method is **non-doctrinal**. It pairs swings by recency alone, without structural break, reclaim, or opposite-boundary linkage.

**RANGE_V2 must not use latest-swing-pair logic as its range formation rule.**

FX TrendMaster ranges are **event-driven containers**. Boundaries emerge from a lifecycle sequence — not from a geometric snapshot of the two most recent swing pivots.

---

## 2. RANGE_V1 status

`RANGE_V1` is frozen with the following classification:

| Attribute | Status |
|-----------|--------|
| Purpose | Bootstrap heuristic |
| Allowed use | Smoke-test only — exercises suggestion → review → promotion → correction loop |
| Doctrinal validity | **Non-doctrinal** |
| Production range doctrine | **Not allowed** |
| Threshold / swing tuning | **Not allowed** — do not improve RANGE_V1 accuracy |
| Code changes | May remain in repo for loop testing; no functional investment |

**RANGE_V1 rule (current implementation):** takes the latest `SWING_HIGH` and latest `SWING_LOW` at or before the active candle and proposes them as `suggested_rh` / `suggested_rl`.

That rule exists to validate plumbing (storage, API, Electron review panel, corrections, replay context). It does **not** represent how Josh maps structure.

---

## 3. RANGE_V2 definition

`RANGE_V2` is a **stateful, event-driven** range detector.

Required formation sequence:

```text
Existing Range or Manual Seed Anchors
  → BOS (structure break)
  → Reclaim (close back inside / validates per doctrine)
  → Opposite Swing Boundary (linked to transition)
  → Range Suggestion
```

`RANGE_V2` runs **downstream** of break and reclaim context. It does not invent a range from swings alone.

Pipeline order (doctrinal target):

```text
SWING_V*  →  BOS_V*  →  RECLAIM_V*  →  RANGE_V2
```

---

## 4. Required inputs

`RANGE_V2` requires all of the following before it may emit a range suggestion:

| Input | Required | Notes |
|-------|----------|-------|
| `symbol` | Yes | e.g. `XAUUSD` |
| `source_timeframe` | Yes | Single-TF per run (Phase 0 rule) |
| `structure_layer` | Yes | e.g. `WEEKLY`, `DAILY`, `INTRADAY` |
| `replay_until_time` | Yes | Market-time cut; no future candles |
| Existing active range context **or** explicit manual seed anchors | Yes | At least one must be present |
| Broken boundary | Yes | Which side of the old container was breached (`HIGH` \| `LOW`) |
| BOS event or BOS candidate | Yes | Direction + candle + broken level |
| Reclaim event or reclaim candidate | Yes | Close-back validation per doctrine |
| Swing candidates | Yes | Available before and/or around reclaim window |

**Hard rule:** `RANGE_V2` must **not** run as a standalone latest-swing-pair detector.

If break, reclaim, or linked swing context is missing, the detector must not force a range suggestion (see §6 `NO_VALID_RANGE`).

### 4.1 Existing range vs manual seed

| Context type | Meaning |
|--------------|---------|
| **Existing active range** | Confirmed `map_ranges` row or equivalent in-flight detector context with known RH/RL and `range_id` |
| **Manual seed anchors** | User-set `SET_INITIAL_ANCHOR` / `SET_ANCHOR` facts (HIGH + LOW) with no prior BOS cycle — initial container birth |

Initial seed is doctrinally manual. `RANGE_V2` may **consume** seed anchors as input but must not silently replace manual range birth doctrine.

---

## 5. Boundary rules

Boundary selection is **transition-linked**, not recency-linked.

### 5.1 Bullish transition (BOS UP)

Prerequisites:

1. An existing range (or seed) with a known old RH and old RL.
2. Price **breaks above old RH** (BOS UP — wick or body per timeframe break rule).
3. Price **reclaims** per doctrine (close back inside / validates the transition — not a standalone sweep).

Boundary selection after valid reclaim:

| Boundary | Rule |
|----------|------|
| **RL (suggested)** | The **opposite swing low** linked to this transition — the swing low that formed in the break→reclaim window and is structurally opposite to the bullish break direction. Not the arbitrary latest swing low on chart. |
| **RH (suggested)** | Derived from the **broken / new structural high context** — the high established by the BOS UP leg (broken old RH or the post-break structural high that defines the new container ceiling). Not the arbitrary latest swing high on chart. |

### 5.2 Bearish transition (BOS DOWN)

Prerequisites:

1. An existing range (or seed) with a known old RH and old RL.
2. Price **breaks below old RL** (BOS DOWN).
3. Price **reclaims** per doctrine.

Boundary selection after valid reclaim:

| Boundary | Rule |
|----------|------|
| **RH (suggested)** | The **opposite swing high** linked to this transition — the swing high that formed in the break→reclaim window and is structurally opposite to the bearish break direction. Not the arbitrary latest swing high on chart. |
| **RL (suggested)** | Derived from the **broken / new structural low context** — the low established by the BOS DOWN leg (broken old RL or the post-break structural low that defines the new container floor). Not the arbitrary latest swing low on chart. |

### 5.3 Opposite swing linkage (language lock)

**Opposite swing** means: the swing pivot on the **non-broken side** of the transition that is **causally associated** with the BOS→reclaim cycle — i.e. the swing that would become the new boundary anchor when the range rebases, not merely the most recent pivot of that kind anywhere on the chart.

Exact index-selection algorithm is deferred to implementation. This contract locks the **doctrinal reason**, not the code.

### 5.4 Rebase vs new container

| Outcome | When |
|---------|------|
| **Rebased range** | Prior range existed; BOS + reclaim completed; new RH/RL replace active container while old range is preserved for measurement (retracement, profile stats). |
| **New child range** | MINOR leg inside MAJOR, or nested resolution per §7. |

---

## 6. State machine

`RANGE_V2` operates over a legal range lifecycle. States:

| State | Meaning |
|-------|---------|
| `SEEDED` | Manual seed anchors set; container exists but no BOS cycle yet |
| `ACTIVE_RANGE` | Confirmed RH/RL container; no open breach |
| `BREACHED_UP` | Wick/body break above RH; reclaim not yet confirmed |
| `BREACHED_DOWN` | Wick/body break below RL; reclaim not yet confirmed |
| `RECLAIMED_UP` | Bearish-side breach context resolved with bullish reclaim validation |
| `RECLAIMED_DOWN` | Bullish-side breach context resolved with bearish reclaim validation |
| `REBASED` | New RH/RL confirmed after reclaim; old range preserved for stats |
| `ABANDONED` | Range abandoned per doctrine (`ABANDON_RANGE`); no active container |
| `NO_VALID_RANGE` | Detector cannot derive a doctrinally valid range at this replay position |

### 6.1 Transition sketch

```text
SEEDED → ACTIVE_RANGE
ACTIVE_RANGE → BREACHED_UP | BREACHED_DOWN
BREACHED_UP → RECLAIMED_DOWN → REBASED → ACTIVE_RANGE
BREACHED_DOWN → RECLAIMED_UP → REBASED → ACTIVE_RANGE
ACTIVE_RANGE | REBASED → ABANDONED
(any) → NO_VALID_RANGE   # when inputs or lifecycle preconditions fail
```

### 6.2 `NO_VALID_RANGE` is mandatory

`NO_VALID_RANGE` is a **valid detector output**, not an error.

The detector **must not** force a `RANGE_MAJOR` or `RANGE_MINOR` suggestion when:

- No existing range and no seed anchors
- BOS context missing
- Reclaim context missing
- Opposite swing cannot be linked to the transition
- Replay window truncates away required events
- Lifecycle state is `BREACHED_*` without reclaim (boundaries must not update early)

---

## 7. Major / Minor rules

`RANGE_V2` must support Phase 0 major/minor contracts.

### 7.1 `range_scale`

| Value | Meaning |
|-------|---------|
| `MAJOR` | Active structural container for the timeframe |
| `MINOR` | Internal leg inside a MAJOR parent |

### 7.2 `range_role`

| Value | Meaning |
|-------|---------|
| `ACTIVE_CONTAINER` | Primary living range for the layer |
| `INTERNAL_LEG` | Minor leg inside parent MAJOR |
| `EXPANSION_LEG` | Price travelled major boundary → major boundary without clean minors |

### 7.3 `internal_structure_status`

| Value | Meaning |
|-------|---------|
| `HAS_MINORS` | One or more MINOR ranges exist inside the MAJOR |
| `NO_MINOR_STRUCTURE` | MAJOR completed with no clean minors — **explicit stored fact** |
| `UNKNOWN` | Minor detection not yet resolved |

**Hard rule:** `NO_MINOR_STRUCTURE` must be **explicitly stored**. It must not be inferred from missing rows or empty query results.

### 7.4 Major reset

A MAJOR resets only when a MINOR breaks and confirms **beyond the MAJOR boundary** per doctrine (Phase 0 §2.2). `RANGE_V2` suggestions must respect parent linkage (`parent_range_id`) and not collapse hierarchy.

---

## 8. Replay context rule

`RANGE_V2` must be replay-safe (same contract as replay-context fix for `RANGE_V1` plumbing).

### 8.1 Candle window

Detector may only use candles where:

```text
candle_time <= replay_until_time
```

If `visible_from_time` is supplied:

```text
visible_from_time <= candle_time <= replay_until_time
```

No future candle leak is allowed. Replay position is the market-time truth cut.

### 8.2 Required `meta_json` fields (every RANGE_V2 suggestion)

| Field | Required |
|-------|----------|
| `detection_run_id` | Yes |
| `replay_until_time` | Yes |
| `replay_until_time_ms` | Yes |
| `visible_from_time` | If supplied in request |
| `visible_from_time_ms` | If supplied in request |
| `first_candle_time` | Yes |
| `first_candle_time_ms` | Yes |
| `last_candle_time` | Yes |
| `last_candle_time_ms` | Yes |
| `candle_count_used` | Yes |

---

## 9. Suggestion output contract

### 9.1 Allowed `candidate_kind` values

| `candidate_kind` | When |
|------------------|------|
| `RANGE_MAJOR` | Doctrinally valid MAJOR range after BOS → reclaim → opposite boundary |
| `RANGE_MINOR` | Doctrinally valid MINOR leg with `parent_range_id` |
| `NO_VALID_RANGE` | Lifecycle preconditions missing; no forced suggestion |
| `NO_MINOR_STRUCTURE` | MAJOR confirmed with explicit no-minor outcome (see §7.3) |

### 9.2 Required fields on range suggestions

| Field | Required |
|-------|----------|
| `suggested_rh` | On `RANGE_MAJOR` / `RANGE_MINOR` |
| `suggested_rl` | On `RANGE_MAJOR` / `RANGE_MINOR` |
| `candidate_kind` | Yes |
| `range_scale` | Yes (`MAJOR` \| `MINOR`) |
| `range_role` | Yes |
| `internal_structure_status` | Yes when applicable |
| `detector_version` | `RANGE_V2` |
| `engine_source` | `python_detector` |
| `parent_range_id` | When MINOR or nested |
| `bos_suggestion_id` or `bos_event_id` | Yes — links to break context |
| `reclaim_suggestion_id` or `reclaim_event_id` | Yes — links to reclaim context |
| `old_range_id` | When rebasing from prior container |
| `broken_boundary` | `HIGH` \| `LOW` |
| `opposite_swing_index` | Index of linked opposite swing |
| `boundary_selection_reason` | In `meta_json` — human-readable doctrinal justification |

### 9.3 `boundary_selection_reason` (meta_json)

Must explain **why** this RH/RL was chosen — e.g.:

```text
"BOS_UP above old RH 2410.50; RECLAIM_DOWN confirmed; opposite swing low at index 42 selected as RL"
```

Not merely `"swing high X + swing low Y"`.

### 9.4 `NO_VALID_RANGE` output shape

When emitting `NO_VALID_RANGE`:

- `suggested_rh` / `suggested_rl` = null
- `reason_text` = explicit missing precondition (e.g. `"No reclaim candidate after BREACHED_UP"`)
- `meta_json.lifecycle_state` = current evaluated state
- Still write `detector_version = RANGE_V2` and replay context fields

---

## 10. Non-goals

This contract phase does **not** authorize:

| Non-goal | Status |
|----------|--------|
| Detector code implementation | Deferred until lock |
| Electron UI changes | Deferred |
| Swing threshold tuning | Forbidden |
| Displacement filter tuning | Forbidden |
| RANGE_V1 improvement | Forbidden |
| Autopilot / guided workflow | Deferred (Phase 4) |
| Research queries / Amy stats | Deferred |
| Live signals / auto-trading | Forbidden |

---

## 11. Gate before implementation

**Doctrine lock:** `RANGE_V2_DOCTRINE_LOCKED = TRUE` (2026-06-17). Josh accepted this contract.

**Code lock:** `RANGE_V2` implementation remains **blocked** until §11.3 prerequisites are done and an implementation plan is reviewed. A doctrinally correct detector is useless if it sees future candles or displays stale suggestions.

### 11.1 Review checklist

| # | Item | Accepted |
|---|------|----------|
| 1 | `RANGE_V1` frozen as non-doctrinal smoke-test heuristic only | ✓ |
| 2 | `RANGE_V2` event sequence accepted (seed/range → BOS → reclaim → opposite boundary) | ✓ |
| 3 | `NO_VALID_RANGE` accepted as valid output (no forced suggestions) | ✓ |
| 4 | Replay context rule accepted (no future candle leak + meta_json fields) | ✓ |
| 5 | Major / minor inheritance and `NO_MINOR_STRUCTURE` explicit storage accepted | ✓ |
| 6 | Suggestion output contract accepted (linkage ids, `boundary_selection_reason`) | ✓ |

### 11.2 Lock procedure

1. ~~Josh reviews this document.~~ **Done (2026-06-17).**
2. ~~All checklist items marked accepted.~~ **Done.**
3. ~~Update header: `Status: LOCKED — RANGE_V2_DOCTRINE_LOCKED = TRUE`.~~ **Done.**
4. Open implementation only after §11.3 prerequisites and implementation plan review.

### 11.3 Prerequisite work order (before `RANGE_V2` code)

```text
1. Replay-context bug fix     — detector must not see future candles; stale suggestions must not display as current
2. Review Candidate compact/collapsible UI fix — panel must not obstruct Structural Map workflow
3. RANGE_V2 implementation plan — scoped plan doc only; no code yet
4. RANGE_V2 code              — backend/detector only; follows this contract
```

| Step | Status | Notes |
|------|--------|-------|
| 1. Replay-context bug fix | **Done** (2026-06-17) | Window filter, supersede-by-scope, strict `detection_run_id` filter, Electron context label |
| 2. Review Candidate compact UI | **Done** (2026-06-17) | Collapsed chip default; compact drawer; expanded details on demand |
| 3. RANGE_V2 implementation plan | **Done** (2026-06-17) | See `docs/architecture/RANGE_V2_IMPLEMENTATION_PLAN.md` |
| 4. RANGE_V2 code | **Blocked** | After Phase B tests pass + Phase C |

Do **not** tune `RANGE_V1` swing thresholds or improve swing-pair logic during steps 1–2.

---

## 12. References

- `docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md` — suggestion schema, major/minor rules, detector versions
- `docs/architecture/ARCHITECTURE_LOCK.md` — raw ledger doctrine
- `electron/README_ELECTRON_V087_15_HTF_CORE_STATE_CONTRACT.txt` — ACTIVE_RANGE → BREACHED → RECLAIMED lifecycle
- `electron/README_ELECTRON_V087_10_HTF_STATE_MEMORY_REBASE.txt` — rebase after BOS + reclaim
- `docs/architecture/PYTHON_PROCESSOR_PLAN.md` — `range_builder.py` lifecycle pass
- `backend/detector/range_candidate.py` — `RANGE_V1` implementation (frozen, non-doctrinal)
