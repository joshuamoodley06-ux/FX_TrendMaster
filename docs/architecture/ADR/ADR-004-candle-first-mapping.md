# ADR-004: Candle-First Mapping (Josh Workflow Contract)

**Status:** Accepted (product contract — partial automation)  
**Date:** 2026-06-19  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../../project%20rules.md)  
**Authority:** Candle-First Mapping Rule, Machine Responsibility Rule, Workflow Over Detector Rule, Python Truth Engine Rule (§31)

**See also:** [`DATA_FLOW_CONTRACTS.md`](../DATA_FLOW_CONTRACTS.md) flow D · [`PILOT_BACKSTOP_CHECKLIST.md`](../PILOT_BACKSTOP_CHECKLIST.md)

---

## Context

Josh maps structure by **reading candles** and marking checkpoints. The UI provides shortcuts; the **machine** commits durable facts to VPS backend via `inspectorCommit`. Campaign Manager sequences work; Hierarchy Explorer browses; Audit verifies.

---

## User interaction contract

| Input | Action |
|-------|--------|
| Click candle | Select bar / anchor time for RH, RL, BOS |
| **H** | Set **Range High (RH)** on selected candle |
| **L** | Set **Range Low (RL)** on selected candle |
| **↑** | **BOS_UP** (break high) |
| **↓** | **BOS_DOWN** (break low) |
| **← / →** | Replay step back / forward |
| **U** | Undo draft (in-session; not backend delete unless explicit) |
| **Esc** | Clear selection / cancel draft |

All mark actions require **`assertCandleFeedReady`** (ADR-003).

---

## Role separation

| Actor | Responsibility |
|-------|------------------|
| **User** | Choose candles, layer, parent context, replay position |
| **Machine** | Persist checkpoints, chain links, lifecycle fields, quiet refresh |
| **Campaign Manager** | Sequence: next parent, gap, layer — **no structural writes** |
| **Hierarchy (Explorer)** | Browse, jump, select range — **no saves** |
| **Audit** | Verify backend truth — **read-only** |
| **Detector** | Suggestions only — never auto-save without feed + context verification |

Primary workflow buttons (Save Range, Refresh Campaign, etc.) may exist under **advanced/correction** tools but are **not required** for normal mapping.

---

## Machine checkpoint: RH + RL complete

When both RH and RL are set on verified feed:

```text
User: H, L on selected candles
Machine:
  → create or update working range (inspectorCommit structural_range)
  → set parent_range_id per hierarchy rules
  → link active_structural_range_id in UI
  → refresh saved ranges + hierarchy/campaign quietly (no camera refit)
  → solid range lines on chart
```

Backend requirements (`map_ranges`):

- `range_high_price`, `range_low_price`, anchor times
- `structure_layer`, `source_timeframe`, `range_scope`
- `case_id` / `raw_case_id` / `case_ref`
- `parent_range_id` when child MAJOR
- `status` ACTIVE for working range

---

## Machine checkpoint: BOS

When BOS_UP or BOS_DOWN marked:

```text
User: ↑ or ↓ (with valid RH/RL context)
Machine:
  → save structural event (inspectorCommit structural_event)
  → link active_range_id on event
  → mark old range BROKEN on backend:
      status = BROKEN
      broken_by_event_id
      direction_of_break
      inactive_from_time
  → prepare next range draft context (clear RH/RL draft, keep parent)
```

Backend requirements (`map_events` + range lifecycle):

- Event: `BOS_UP` / `BOS_DOWN` (or layer-prefixed structural codes)
- Event: price, time, candle OHLC, `movement_rule`
- Range patch: broken range lifecycle fields populated

---

## Machine checkpoint: Next RH + RL after BOS

When next range anchors set after break:

```text
User: H, L for next range
Machine:
  → create/update next range
  → old_range_id / new_range_id chain links
  → created_by_event_id from breaking BOS
  → parent_range_id preserved or derived per layer rules
  → refresh hierarchy/campaign
```

---

## Campaign interaction

- **Campaign Continue** selects next gap → guided mapping / child layer setup.
- Campaign does **not** save ranges; user still marks H/L/BOS on candles.
- Campaign may switch TF/layer — must wait for feed valid before shortcuts enable.

---

## Hierarchy interaction

- **Jump** / select row → `jumpToStructuralRange` / `selectSavedStructuralRange`
- Sets context overlays and candle window — **no backend mutation**
- Reparent / archive are **advanced** explicit actions via `inspectorCommit`

---

## Audit interaction

- `refreshHierarchyAudit` → display PASS/WARN/FAIL
- Export audit JSON reads VPS only
- Audit failure does not auto-fix structure; user maps corrections

---

## Detector boundary

Detector may suggest candidates; must **not**:

- Auto-switch layer or TF without feed verification
- Auto-save BOS/range to backend in primary workflow
- Override user's selected candle

---

## Raw mapping vs structural

Manual keylogger marks may still write **raw_mapping_events** (evidence locker). Formal campaign checkpoints use **structural** `map_ranges` / `map_events` via `inspectorCommit`.

Pilot must not collapse these layers without explicit approval.

---

## Related files

- `electron/src/inspectorCommit.ts` — durable write funnel
- `electron/src/main.tsx` — `saveStructuralRange`, `saveStructuralBos`, shortcuts
- `electron/src/mappingCampaignManager.ts` — derived campaign tasks
- `project rules.md` — Machine Responsibility Rule
