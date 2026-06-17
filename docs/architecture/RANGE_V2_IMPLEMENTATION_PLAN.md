# RANGE_V2 Implementation Plan

**Status:** **DRAFT** — pending Josh review. No code authorized until this plan is accepted.  
**Doctrine source:** `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md` (**LOCKED** 2026-06-17)  
**Prerequisites:** Replay-context fix ✓ · Review Candidate compact UI ✓

> **Scope:** Planning only. No detector code, no schema migration, no Electron changes, no threshold tuning.

---

## 1. Current state audit

### 1.1 Detector pipeline today

`backend/detector/pipeline.py` runs all domains in one pass on a single `DetectionContext`:

```text
run_detector_v1(ctx)
  → detect_swing_suggestions(ctx)      # SWING_V1
  → detect_range_suggestions(ctx)      # RANGE_V1  ← non-doctrinal
  → detect_bos_suggestions(ctx)        # BOS_V1
  → detect_sweep_suggestions(ctx)        # SWEEP_V1
  → detect_reclaim_suggestions(ctx)    # RECLAIM_V1
  → detect_ref_candle_suggestions(ctx)   # REF_CANDLE_V1
```

| Module | Version | File | What it does today |
|--------|---------|------|-------------------|
| **SWING_V1** | `SWING_V1` | `swing.py` | Local extrema + adaptive displacement; emits `SWING_HIGH` / `SWING_LOW` suggestions and populates `ctx.swings` |
| **RANGE_V1** | `RANGE_V1` | `range_candidate.py` | **Latest swing high + latest swing low** → `RANGE_MAJOR` / `RANGE_MINOR` suggestion |
| **BOS_V1** | `BOS_V1` | `bos.py` | Active candle breaks `ctx.range_high` / `ctx.range_low` per break rule (wick HTF, body-close M15) |
| **SWEEP_V1** | `SWEEP_V1` | `sweep.py` | Liquidity sweep beyond boundary, close inside |
| **RECLAIM_V1** | `RECLAIM_V1` | `reclaim.py` | Sweep-then-close-back pattern on prior candle; **not BOS-gated** |
| **REF_CANDLE_V1** | `REF_CANDLE_V1` | `ref_candle.py` | Ref candle candidates (separate pipeline per HTF contract) |

### 1.2 Architectural gaps (why RANGE_V2 is needed)

| Gap | Impact |
|-----|--------|
| **RANGE_V1 is parallel, not downstream** | Range suggestions ignore BOS/reclaim state |
| **RANGE_V1 uses swing pairing** | Violates FX TrendMaster event-driven doctrine |
| **RECLAIM_V1 ≠ HTF reclaim contract** | Electron v087.15: reclaim requires **accepted BOS first** + close back inside old boundary; current Python reclaim is sweep-based on active candle only |
| **No lifecycle state** | No `SEEDED` / `BREACHED_*` / `RECLAIMED_*` / `NO_VALID_RANGE` evaluation |
| **No opposite-swing linkage** | Boundaries not tied to transition window |

### 1.3 Why RANGE_V1 stays frozen

Per locked doctrine contract §2:

- **Bootstrap only** — validates suggestion → review → promotion → corrections loop
- **Non-doctrinal** — must not be tuned or promoted as production range logic
- **Remains callable** behind a flag for smoke tests until RANGE_V2 is proven

**Plan decision:** `RANGE_V1` stays in repo; `pipeline.py` switches range output source via flag (see §10 phase D). Default for production path: **RANGE_V2 only** once enabled.

### 1.4 What already works (reuse, do not rewrite)

| Capability | Location | RANGE_V2 reuse |
|------------|----------|----------------|
| Replay window / `meta_json` context | `context_window.py`, `ohlc_loader.py`, `writer.py` | All RANGE_V2 drafts inherit `ctx.detection_window_meta` |
| Suggestion persistence + supersede | `writer.py`, `detection_brain_store.py` | Same write path |
| Review / promotion | `detection_brain_promotion.py`, Electron panel | `RANGE_MAJOR` / `RANGE_MINOR` unchanged |
| BOS break math | `bos.py`, `break_rules.py` | Input signal for lifecycle (not rewritten) |
| Swing list | `swing.py` `detect_swings()` | Opposite-boundary candidate pool |

---

## 2. Proposed RANGE_V2 module layout

**Do not create these files until plan is accepted.**

```text
backend/detector/
  range_state.py       # Lifecycle state types + evaluate_state(ctx, events) → RangeLifecycleState
  range_lifecycle.py   # Transition rules: seed → active → breached → reclaimed → rebase
  range_boundary.py    # Opposite-swing selection + RH/RL derivation (doctrine-facing)
  range_v2.py          # detect_range_v2_suggestions(ctx, upstream_drafts) → list[SuggestionDraft]
```

### 2.1 Module responsibilities

| File | Owns | Does not own |
|------|------|--------------|
| `range_state.py` | State enum, input bundle (`RangeContext`), `NO_VALID_RANGE` reason codes | Candle loading, DB access |
| `range_lifecycle.py` | Scan candles ≤ replay_until for BOS then reclaim sequence against known RH/RL | Swing detection thresholds |
| `range_boundary.py` | Linked opposite swing + structural high/low for rebased RH/RL | BOS/reclaim detection (consumes upstream) |
| `range_v2.py` | Orchestration, `SuggestionDraft` assembly, `meta_json` linkage fields | Promotion, map_ranges writes |

### 2.2 `versions.py` addition (future)

```text
RANGE_V2 = "RANGE_V2"
DEFAULT_VERSIONS["RANGE"] = RANGE_V2   # when flag enabled
```

`RANGE_V1` constant remains for smoke-test flag path.

---

## 3. RANGE_V2 inputs

### 3.1 From `DetectionContext` (existing)

| Field | Required | Use |
|-------|----------|-----|
| `symbol` | Yes | Suggestion scope |
| `source_timeframe` | Yes | Break rule + derived codes |
| `structure_layer` | Yes | Suggestion + filter scope |
| `candles` | Yes | Already replay-truncated |
| `active_index` | Yes | Evaluation cursor |
| `replay_until_time_ms` | Yes | Hard ceiling (also in `detection_window_meta`) |
| `visible_from_time_ms` | If supplied | Window floor |
| `detection_run_id` | Yes | `meta_json` |
| `range_high` / `range_low` | If active range or seed | Old container boundaries |
| `range_scale` | Yes | `MAJOR` / `MINOR` on output |
| `parent_range_id` | If nested | MINOR linkage |
| `active_range_id` | If rebasing | `old_range_id` in meta |
| `swings` | Yes | From `detect_swings()` or pre-filled on ctx |

### 3.2 From upstream detector drafts (same run)

RANGE_V2 orchestrator receives **in-memory** drafts from BOS/RECLAIM/SWEEP already computed for `ctx`:

| Input | Source | Notes |
|-------|--------|-------|
| BOS candidate(s) | `BOS_UP` / `BOS_DOWN` drafts | Candle index, broken level, `meta_json.range_high/low` |
| Reclaim candidate(s) | `RECLAIM_UP` / `RECLAIM_DOWN` drafts | Candle index, reclaimed level |
| Confirmed events (future) | Optional `map_events` loader | Phase 2+ — not required for v1 of RANGE_V2 |

**Plan decision (v1):** RANGE_V2 v1 pairs **lifecycle-detected** BOS+reclaim from candle scan, cross-checks against upstream drafts when present. Upstream drafts provide `bos_suggestion_id` / `reclaim_suggestion_id` linkage when indices match.

### 3.3 Seed vs active range

| Mode | Condition | Lifecycle start state |
|------|-----------|----------------------|
| **Seed** | `range_high` + `range_low` set, no `active_range_id`, no prior BOS in window | `SEEDED` → `ACTIVE_RANGE` |
| **Active range** | `active_range_id` + RH/RL | `ACTIVE_RANGE` |
| **Neither** | No RH/RL | `NO_VALID_RANGE` immediately |

---

## 4. State machine design

### 4.1 States

| State | Meaning |
|-------|---------|
| `SEEDED` | Manual/seed anchors present; no breach in replay window |
| `ACTIVE_RANGE` | Container RH/RL valid; no open breach at active candle |
| `BREACHED_UP` | Price broke above old RH (BOS UP detected); reclaim not yet satisfied |
| `BREACHED_DOWN` | Price broke below old RL (BOS DOWN detected); reclaim not yet satisfied |
| `RECLAIMED_UP` | Bearish breach path: reclaim validation complete (bullish reclaim after BOS DOWN context) |
| `RECLAIMED_DOWN` | Bullish breach path: reclaim validation complete (bearish reclaim after BOS UP context) |
| `REBASED` | New RH/RL computable; suggestion emitted |
| `ABANDONED` | `ABANDON_RANGE` fact or explicit abandon in context (future input) |
| `NO_VALID_RANGE` | Valid terminal — cannot or should not suggest range |

### 4.2 Transition conditions (planning language)

```text
[no RH/RL]
  → NO_VALID_RANGE (reason: no_seed_or_active_range)

[SEEDED or ACTIVE_RANGE]
  → BREACHED_UP
      when: first candle at or before active_index where BOS_UP breaks old RH per break_rule
  → BREACHED_DOWN
      when: first candle where BOS_DOWN breaks old RL per break_rule

[BREACHED_UP]
  → RECLAIMED_DOWN
      when: after breach candle, a candle satisfies reclaim-after-BOS-UP doctrine
            (see OPEN QUESTIONS §11 — close inside old RH)
  → NO_VALID_RANGE (at active_index)
      when: still BREACHED_UP and reclaim not yet seen

[BREACHED_DOWN]
  → RECLAIMED_UP
      when: after breach candle, reclaim-after-BOS-DOWN doctrine satisfied
  → NO_VALID_RANGE
      when: still BREACHED_DOWN and no reclaim

[RECLAIMED_DOWN]  # came from bullish break path
  → REBASED
      when: opposite swing low linked + structural RH derivable
  → NO_VALID_RANGE
      when: reclaim seen but opposite swing not linkable

[RECLAIMED_UP]    # came from bearish break path
  → REBASED
      when: opposite swing high linked + structural RL derivable
  → NO_VALID_RANGE
      when: reclaim seen but opposite swing not linkable

[REBASED]
  → (emit RANGE_MAJOR or RANGE_MINOR suggestion)
  → ACTIVE_RANGE (conceptual next cycle after user approves — not auto)

[ABANDONED]
  → NO_VALID_RANGE (reason: range_abandoned)

[expansion path, no minor]
  → NO_MINOR_STRUCTURE or EXPANSION_LEG suggestion (see OPEN QUESTIONS §11)
```

### 4.3 Evaluation scope

- Scan only `ctx.candles[0 .. active_index]` (already ≤ `replay_until_time`).
- Use **most recent completed** BOS→reclaim chain in window, not the first historical one (plan default — confirm with Josh).
- If multiple chains exist, prefer the chain whose reclaim candle is closest to `active_index` without exceeding it.

---

## 5. Boundary selection algorithm

**Josh doctrine decisions (2026-06-17) — LOCKED for implementation.**

### 5.1 Bullish transition (BOS UP → reclaim → range suggestion)

**Preconditions:** `RECLAIMED_DOWN` state (bullish BOS, then reclaim closes back inside old RH).

| Output | Rule |
|--------|------|
| **New RH** | **BOS high** — the high on the BOS candle that broke old RH. Causally linked to BOS leg. **Not** arbitrary latest high. |
| **New RL** | Opposite **swing low** linked to break/reclaim transition (§5.4) |

### 5.2 Bearish transition (BOS DOWN → reclaim → range suggestion)

**Preconditions:** `RECLAIMED_UP` state.

| Output | Rule |
|--------|------|
| **New RL** | **BOS low** — the low on the BOS candle that broke old RL. Causally linked to BOS leg. **Not** arbitrary latest low. |
| **New RH** | Opposite **swing high** linked to break/reclaim transition (§5.4) |

### 5.3 Reclaim rule (RANGE_V2 lifecycle)

Reclaim = **close back inside old active range after BOS** in the same cycle.

| Path | BOS | Reclaim |
|------|-----|---------|
| Bullish | Break **above** old RH | Later candle **closes ≤ old RH** (inside or at boundary) |
| Bearish | Break **below** old RL | Later candle **closes ≥ old RL** (inside or at boundary) |

- Reclaim **must** follow BOS in same lifecycle cycle.
- **No** reclaim before BOS.
- **No** sweep-only reclaim.

Implemented in `range_lifecycle.py` — independent of `RECLAIM_V1` sweep semantics.

### 5.4 Opposite swing linkage (Josh Q8)

**Search order:**

1. Opposite swing **between** BOS candle and reclaim candle (`bos_index < swing.index < reclaim_index`)
2. If none: **last significant opposite swing before BOS** (lookback 50 candles)
3. If still unclear: **`NO_VALID_RANGE`** — prefer no fake precision

**`boundary_selection_reason` values:**

| Code | Meaning |
|------|---------|
| `OPPOSITE_SWING_BETWEEN_BOS_RECLAIM` | Swing found in break→reclaim window |
| `LAST_OPPOSITE_SWING_BEFORE_BOS` | Fallback swing before BOS leg |
| `UNCLEAR_OPPOSITE_SWING` | Evidence insufficient → `NO_VALID_RANGE` |

### 5.5 Multiple BOS cycles (Josh Q7)

- Process **one lifecycle cycle** at a time using active range state.
- Second BOS **same direction** before reclaim: stay `BREACHED_*`, update extreme only.
- **Opposite** break before reclaim: `UNRESOLVED_TRANSITION` → `NO_VALID_RANGE`.
- Conservative — no range suggestion until clean BOS→reclaim sequence.

### 5.6 Profile / S&R (Josh Q5)

- RANGE_V2 suggests structural container **after BOS + reclaim only**.
- **Do not** classify S&R vs S&D inside RANGE_V2.
- Continuation BOS later is measurement/stats — not range birth.

### 5.7 Expansion / no minor (Josh Q6)

When expansion has no internal minor:

```text
candidate_kind           = NO_MINOR_STRUCTURE
range_role               = EXPANSION_LEG
internal_structure_status = NO_MINOR_STRUCTURE
```

### 5.8 SEEDED behavior (Josh Q9)

- RANGE_V2 **must not** invent first active range from swing pair.
- Valid seed: confirmed `map_range`, manual RH/RL anchors, approved seed suggestion.
- **No seed → `NO_VALID_RANGE`**
- Seed only, no BOS cycle → no range suggestion (`SEED_ONLY_NO_BOS`)

### 5.9 RECLAIM_V1 alignment gap

Current `RECLAIM_V1` detects sweep patterns, not BOS-gated close-inside-boundary per Electron v087.15.

**Plan decision:** `range_lifecycle.py` implements **its own reclaim check** for RANGE_V2 lifecycle (BOS required first). It may still **link** to `RECLAIM_V1` draft when indices match, but must not depend on RECLAIM_V1 semantics alone.

**Non-goal for RANGE_V2 phase 1:** Rewriting `RECLAIM_V1` globally (separate future `RECLAIM_V2` if needed).

---

## 6. NO_VALID_RANGE behavior

Explicit valid output — never an exception, never a silent skip.

| Condition | `reason_text` (example) | `meta_json.lifecycle_state` |
|-----------|-------------------------|----------------------------|
| No seed / active RH/RL | `No seed or active range context` | `NO_VALID_RANGE` |
| BOS without reclaim at active_index | `BOS detected; reclaim not yet confirmed` | `BREACHED_UP` or `BREACHED_DOWN` |
| Reclaim without linkable opposite swing | `Reclaim confirmed; no linked opposite swing` | `RECLAIMED_*` |
| Range abandoned | `Active range abandoned` | `ABANDONED` |
| Replay window truncates BOS/reclaim | `Replay window ends before reclaim` | `BREACHED_*` |
| Expansion, no valid minor | `Expansion leg; no minor structure` | `ACTIVE_RANGE` or custom |
| SEEDED only, no transition | `Seed anchors only; no BOS cycle` | `SEEDED` or `ACTIVE_RANGE` |

**Emit rules:**

- Write **at most one** `NO_VALID_RANGE` suggestion per detection run (candidate_index = 0).
- `suggested_rh` / `suggested_rl` = null.
- Still persist replay `meta_json` fields.
- User may **Reject** with error category (e.g. `OTHER`) to log intentional skip; **Approve** blocked in promotion layer (see §8).

**When not to emit NO_VALID_RANGE:** If a valid `RANGE_MAJOR` / `RANGE_MINOR` suggestion is emitted for the same run, suppress separate `NO_VALID_RANGE` row.

---

## 7. Suggestion output mapping

### 7.1 `detector_suggestions` row mapping

| Field | RANGE_MAJOR / RANGE_MINOR | NO_VALID_RANGE | NO_MINOR_STRUCTURE |
|-------|---------------------------|----------------|---------------------|
| `candidate_kind` | `RANGE_MAJOR` / `RANGE_MINOR` | `NO_VALID_RANGE` | `NO_MINOR_STRUCTURE` |
| `detector_version` | `RANGE_V2` | `RANGE_V2` | `RANGE_V2` |
| `engine_source` | `python_detector` | `python_detector` | `python_detector` |
| `suggested_rh` / `suggested_rl` | computed | null | per doctrine |
| `range_scale` | from ctx | null or ctx | `MAJOR` typical |
| `range_role` | `ACTIVE_CONTAINER` / `INTERNAL_LEG` / `EXPANSION_LEG` | null | `EXPANSION_LEG` candidate |
| `parent_range_id` | when MINOR | null | parent MAJOR id |
| `reason_text` | boundary_selection summary | precondition text | expansion path text |

### 7.2 `meta_json` (required)

| Key | Always | Notes |
|-----|--------|-------|
| `detection_run_id` | Yes | From ctx |
| `replay_until_time` / `_ms` | Yes | From `detection_window_meta` |
| `visible_from_time` / `_ms` | If supplied | |
| `first_candle_time` / `_ms` | Yes | |
| `last_candle_time` / `_ms` | Yes | |
| `candle_count_used` | Yes | |
| `lifecycle_state` | Yes | State at evaluation |
| `old_range_id` | When rebasing | From `active_range_id` |
| `broken_boundary` | When BOS | `HIGH` / `LOW` |
| `bos_suggestion_id` | When matched | UUID from upstream draft |
| `bos_event_id` | Future | Confirmed event id |
| `reclaim_suggestion_id` | When matched | UUID |
| `reclaim_event_id` | Future | |
| `bos_candle_index` | When BOS | |
| `reclaim_candle_index` | When reclaim | |
| `opposite_swing_index` | When linked | |
| `opposite_swing_kind` | When linked | `SWING_HIGH` / `SWING_LOW` |
| `boundary_selection_reason` | Yes | Human-readable |
| `internal_structure_status` | When applicable | `HAS_MINORS` / `NO_MINOR_STRUCTURE` / `UNKNOWN` |

### 7.3 Schema changes

**None required for phase 1.** `candidate_kind` is `TEXT NOT NULL` without enum constraint. `meta_json` is already flexible.

**Future (optional):** `detector_version_registry` row for `RANGE_V2` rule summary — documentation only.

---

## 8. Compatibility with existing review flow

### 8.1 Unchanged principles

```text
Python suggests → User approves / edits / rejects → map_ranges / map_events
```

- RANGE_V2 **never** auto-writes confirmed structure.
- `write_suggestions()` path unchanged.
- Replay context + supersede-by-scope unchanged.

### 8.2 Promotion behavior by `candidate_kind`

| Kind | Approve | Edit + Approve | Reject |
|------|---------|----------------|--------|
| `RANGE_MAJOR` / `RANGE_MINOR` | Promotes to `map_ranges` (existing) | Existing | Existing |
| `NO_VALID_RANGE` | **Block** — return 400 `non_promotable_kind` | Block | Allowed — logs correction, no map write |
| `NO_MINOR_STRUCTURE` | **OPEN** — metadata-only row or special map field (§11) | OPEN | Allowed |

**Plan decision (default):** `NO_VALID_RANGE` approve blocked in `detection_brain_promotion.py` with clear error. User rejects to clear panel.

### 8.3 Electron Review Candidate panel

**No UI changes in RANGE_V2 code phase.** Existing compact panel already:

- Filters by `detection_run_id`
- Shows `Context: up to YYYY-MM-DD`
- Supports Approve / Edit+Approve / Reject

`NO_VALID_RANGE` rows appear as list items with kind label; RH/RL empty — acceptable for v1.

### 8.4 RANGE_V1 coexistence

| Flag | Pipeline behavior |
|------|-------------------|
| `DETECTOR_RANGE_MODE=smoke_v1` | Emit RANGE_V1 only (smoke tests) |
| `DETECTOR_RANGE_MODE=v2` (default after cutover) | Emit RANGE_V2 only; RANGE_V1 not called |
| `DETECTOR_RANGE_MODE=both` | Dev compare only — not production |

---

## 9. Test plan

Tests in `backend/tests/test_range_v2.py` (new file, phase E).

| # | Test | Acceptance |
|---|------|------------|
| 1 | No seed / no RH/RL | `NO_VALID_RANGE`; reason mentions missing context |
| 2 | Seed only, no BOS | `NO_VALID_RANGE` or no range suggestion (not RANGE_V1 pair) |
| 3 | BOS UP without reclaim | `NO_VALID_RANGE`; lifecycle `BREACHED_UP` |
| 4 | BOS DOWN without reclaim | `NO_VALID_RANGE`; lifecycle `BREACHED_DOWN` |
| 5 | Bullish BOS + reclaim + linked swing | `RANGE_MAJOR` with RH/RL; meta linkage fields |
| 6 | Bearish BOS + reclaim + linked swing | `RANGE_MAJOR` with RH/RL |
| 7 | March replay cut | April+ candles do not affect output |
| 8 | March run then June run | New `detection_run_id`; supersede stale pending |
| 9 | `meta_json` trace | All required keys present |
| 10 | MINOR scale + parent_range_id | `RANGE_MINOR` preserved |
| 11 | Safety | `map_ranges` / `map_events` counts unchanged after run |
| 12 | RANGE_V1 smoke flag | RANGE_V1 still callable when `smoke_v1` mode |
| 13 | No latest-swing-pair | RH/RL differ from RANGE_V1 pair on same fixture where doctrine differs |

**Fixtures:** Extend `test_detector_replay_context.py` timed swing series; add BOS+reclaim scripted OHLC sequences.

---

## 10. Implementation phases

### Phase A — `range_state` helpers

- `RangeLifecycleState` enum
- `RangeContext` dataclass (RH, RL, ids, scale, layer)
- `NoRangeReason` enum
- Unit tests for state typing only

**Exit:** Importable types, no pipeline hook.

### Phase B — `range_boundary` + `range_lifecycle` helpers

- `find_bos_reclaim_chain(candles, rh, rl, active_index, break_rule) → Chain | None`
- `select_opposite_swing(swings, chain, direction) → SwingPoint | None`
- `derive_rebased_boundaries(chain, opposite_swing) → (rh, rl, reason)`
- Unit tests with synthetic candles

**Exit:** Pure functions tested; no `SuggestionDraft` yet.

### Phase C — `range_v2.py` detector output

- `detect_range_v2_suggestions(ctx, upstream_drafts) → list[SuggestionDraft]`
- Assemble `meta_json` per §7
- Emit `NO_VALID_RANGE` when appropriate

**Exit:** Isolated tests calling `detect_range_v2_suggestions` directly.

### Phase D — Pipeline integration behind flag

- `DETECTOR_RANGE_MODE` env / `run_detector_v1(..., range_mode=)` override
- Allowed: `smoke_v1` (default) | `doctrine_v2`
- Unknown values: **default to `smoke_v1` with `RuntimeWarning`** (safe default)
- `doctrine_v2`: swings → bos/sweep/reclaim collected → `detect_range_v2_suggestions` (strict seed; no RANGE_V1)
- `smoke_v1`: unchanged RANGE_V1 path

**Exit:** Pipeline flag works; regression tests pass.

### Phase E — Tests

- Full suite §9
- Regression: existing `test_detector_replay_context.py`, `test_detector_v1.py` pass with RANGE_V1 smoke flag

### Phase F — CLI smoke

- Extend `smoke_test_detection_brain_loop.py` with `--range-mode v2`
- Document VPS restart + manual Structural Map check

### Phase G — Electron review compatibility

- Manual smoke only (no code): Run Detector → compact panel → Approve/Reject RANGE_V2 row
- Verify `NO_VALID_RANGE` display acceptable

---

## 11. Josh doctrine decisions (LOCKED 2026-06-17)

All open questions resolved. These are authoritative for Phase B+.

### Q1. After bullish BOS + reclaim, which high becomes RH?

**The broken high / BOS high** remains the RH candidate.

- Old RH is broken.
- Price reclaims back inside the old range.
- The **high that broke old RH** becomes the new RH candidate.
- The **opposite swing low** tied to break/reclaim transition becomes the new RL candidate.
- Do **not** select an arbitrary latest high. RH must be causally linked to the BOS leg.

### Q2. After bearish BOS + reclaim, which low becomes RL?

**The broken low / BOS low** remains the RL candidate.

- Old RL is broken.
- Price reclaims back inside the old range.
- The **low that broke old RL** becomes the new RL candidate.
- The **opposite swing high** tied to break/reclaim transition becomes the new RH candidate.
- Do **not** select an arbitrary latest low. RL must be causally linked to the BOS leg.

### Q3. What is reclaim?

For RANGE_V2, reclaim means price **closes back inside the old active range after BOS**.

| Path | Reclaim condition |
|------|-------------------|
| Bullish BOS | Break above old RH → later candle closes **≤ old RH** |
| Bearish BOS | Break below old RL → later candle closes **≥ old RL** |

Reclaim must follow BOS in the same lifecycle cycle. No reclaim before BOS. No sweep-only reclaim.

### Q4. Must reclaim follow BOS on same cycle?

**Yes.**

```text
ACTIVE_RANGE → BREACHED_UP / BREACHED_DOWN → RECLAIMED_* → RANGE_SUGGESTION
```

Reclaim without prior BOS in the active range cycle is invalid → `NO_VALID_RANGE`.

### Q5. Shallow S&R: rebase at reclaim or wait for continuation BOS?

**Do not rebase immediately for S&R profile in RANGE_V2.**

- RANGE_V2 suggests possible range after BOS + reclaim only.
- S&R vs S&D decided later via retracement measurement.
- Continuation BOS confirms survival statistics — not range birth.
- Do not mix profile classification into RANGE_V2.

### Q6. Expansion / no minor?

**Use both fields:**

```text
candidate_kind            = NO_MINOR_STRUCTURE
range_role                = EXPANSION_LEG
internal_structure_status = NO_MINOR_STRUCTURE
```

### Q7. Multiple BOS cycles inside same parent?

Process **one lifecycle cycle** at a time.

- Second BOS same direction before reclaim: maintain `BREACHED_*`, update extreme only.
- Opposite break before reclaim: prior transition unresolved → `NO_VALID_RANGE`.
- Conservative until clean sequence.

### Q8. Opposite swing tie-break?

1. Opposite swing **between** BOS and reclaim candles.
2. Else last significant opposite swing **before BOS**.
3. Else `NO_VALID_RANGE` (prefer over fake precision).

`boundary_selection_reason`: `OPPOSITE_SWING_BETWEEN_BOS_RECLAIM` | `LAST_OPPOSITE_SWING_BEFORE_BOS` | `UNCLEAR_OPPOSITE_SWING`

### Q9. SEEDED behavior?

Initial range from **manual seed anchors** or **confirmed active range** only.

- RANGE_V2 must **not** invent first range from latest swing pair.
- Valid: confirmed `map_range`, manual RH/RL, explicit approved seed.
- **No seed → `NO_VALID_RANGE`**

---

## 12. Non-goals (reaffirmed)

- RANGE_V2 code in this task
- Detector threshold tuning
- RECLAIM_V1 rewrite (unless Q3/Q4 forces minimal alignment)
- Review Candidate UI changes
- Guided workflow / autopilot
- Research engine / Amy
- `map_ranges` schema migration

---

## 13. Key design decisions (summary)

| Decision | Choice |
|----------|--------|
| Range formation | Event-driven BOS → reclaim → opposite swing; **never** latest H+L pair |
| RANGE_V1 | Frozen; smoke flag only |
| RECLAIM for lifecycle | Implement BOS-gated reclaim in `range_lifecycle.py`; do not rely on RECLAIM_V1 alone |
| Pipeline order | `… → BOS → RECLAIM → RANGE_V2` (replace RANGE_V1 when flag on) |
| Missing context | Explicit `NO_VALID_RANGE` suggestion |
| Schema | No migration phase 1 |
| Promotion | `NO_VALID_RANGE` not approvable |
| Replay safety | Reuse existing window meta + supersede (no rework) |

---

| RH on bullish path | **BOS candle high** (broke old RH) |
| RL on bullish path | Linked opposite swing low |
| RL on bearish path | **BOS candle low** (broke old RL) |
| RH on bearish path | Linked opposite swing high |
| Reclaim | Close inside old range after BOS; same cycle only |
| S&R profile | Not in RANGE_V2 |
| Expansion | `NO_MINOR_STRUCTURE` + `EXPANSION_LEG` + status field |
| Opposite swing unclear | `NO_VALID_RANGE` |
| Seed | Manual/confirmed only; no swing-pair birth |

---

## 14. Implementation status

### Phase A + B — **Done** (2026-06-17)

Modules (no pipeline hook):

- `backend/detector/range_state.py` ✓
- `backend/detector/range_lifecycle.py` ✓
- `backend/detector/range_boundary.py` ✓
- `backend/tests/test_range_v2_lifecycle.py` ✓ (15 tests)

### Phase C — **Done** (2026-06-17)

- `backend/detector/range_v2.py` ✓ — `detect_range_v2_suggestions()`
- `backend/tests/test_range_v2_emitter.py` ✓ (9 tests)

### Phase D — **Done** (2026-06-17)

- `backend/detector/range_mode.py` ✓ — `DETECTOR_RANGE_MODE` parsing + `build_pipeline_seed_context()`
- `backend/detector/pipeline.py` ✓ — flag branch in `run_detector_v1()`
- `backend/tests/test_range_v2_pipeline.py` ✓ (8 tests)

**Flag:** `DETECTOR_RANGE_MODE=doctrine_v2` enables RANGE_V2; default `smoke_v1` preserves RANGE_V1.

**Unknown mode:** defaults to `smoke_v1` with `RuntimeWarning`.

### Phase E — **Done** (2026-06-17)

- `backend/detector/range_seed.py` ✓ — `load_active_range_seed_context()`, `resolve_detector_seed_context()`
- `backend/detection_brain_api.py` ✓ — seed resolution for `doctrine_v2`; payload fields `active_range_id`, `range_high`/`range_low`, `range_scale`, `range_role`, `parent_range_id`
- `electron/src/reviewCandidatePanel.tsx` + `reviewCandidateClient.ts` ✓ — sends selected active range + `seed_from_electron`
- `backend/tests/test_range_v2_seed_context.py` ✓ (11 tests)

**Seed priority:** explicit payload / electron selected range → backend ACTIVE `map_ranges` lookup → `NO_VALID_RANGE`.

**Seed trace in `meta_json`:** `seed_source`, `active_range_id`, `seed_rh`, `seed_rl`, `seed_status`, `no_seed_context`, `seed_lookup_error` (when applicable).

RANGE_V2 now receives confirmed active range seed context when available; otherwise it returns `NO_VALID_RANGE` safely.

### Phase F — **Smoke test plan** (2026-06-17)

- `docs/architecture/RANGE_V2_SMOKE_TEST_PLAN.md` ✓ — manual `doctrine_v2` checklist, SQL snippets, bug boundary
- **Execution:** manual on XAUUSD W1/D1 — no new detector logic in Phase F

### Phase G+ — next

- Execute smoke plan on VPS with `DETECTOR_RANGE_MODE=doctrine_v2`
- Promotion block for `NO_VALID_RANGE` (separate task)
- Production cutover decision (`smoke_v1` vs `doctrine_v2` default)

---

## 15. References

- `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md` — locked doctrine
- `docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md` — suggestion schema, major/minor
- `backend/detector/pipeline.py` — current orchestration
- `backend/detector/range_candidate.py` — RANGE_V1 (frozen)
- `electron/README_ELECTRON_V087_15_HTF_CORE_STATE_CONTRACT.txt` — reclaim after BOS
- `docs/architecture/RANGE_V2_SMOKE_TEST_PLAN.md` — Phase F manual smoke (`doctrine_v2`)

---

## 16. Review gate

| Item | Status |
|------|--------|
| Plan document created | ✓ |
| Josh review | ✓ |
| Q1–Q9 answered | ✓ (2026-06-17) |
| `RANGE_V2_IMPLEMENTATION_LOCKED` | ✓ (doctrine section) |
| Phase A + B coding | ✓ Done (2026-06-17) |
| Phase C (`range_v2.py`) | ✓ Done (2026-06-17) |
| Phase D pipeline flag | ✓ Done (2026-06-17) |
| Phase E seed context wiring | ✓ Done (2026-06-17) |
| Phase F smoke test plan | ✓ Done (2026-06-17) |
| Phase F execution / Phase G | ☐ manual smoke on VPS |
