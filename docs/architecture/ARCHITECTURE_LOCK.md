# Architecture Lock

## Locked doctrine

```text
Electron = visual interpreter + raw event emitter / keylogger
VPS FastAPI = master raw event ledger / evidence locker
Main PC / Python = processing brain / compiler
Amy = future reader/explainer of processed summaries
```

## Electron is not allowed to derive durable truth

Electron may display temporary UI visuals:

```text
active high/low lines
frozen boxes
W1 overlays on D1
markers
selected candle HUD
```

Electron must not permanently write:

```text
parent_range_id
zone_percent
profile_type
phase
objective
training labels
feature rows
processed ranges
```

## Raw mapping events allowed

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

## Ledger rules

- Append-only.
- No hard deletes.
- A delete is represented by `DELETE_RECORD`.
- `DELETE_RECORD.supersedes_event_id` points at the target record.
- Undo delete is another `DELETE_RECORD` targeting the previous delete.
- `candle_time_utc_ms` is the relational market-time key.
- `candle_index` is informational only.
- `price_int` + `price_scale` should be used for comparisons.
- `schema_version = raw_mapping_v1`.
- Export must contain `ledger_hash`.

## Processing order

```text
created_order = intent/order-of-recording
candle_time_utc_ms = market timeline order
```

Processor should first resolve intent order, then build market timeline.

## Detection Brain (Phase 0 — contracts only)

The Python Detection & Research Brain adds a suggestion → confirm → promote layer on top of the raw ledger.

Phase 0 contracts are locked in:

```text
docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md
```

**Phase 0:** `PHASE_0_CONTRACTS_LOCKED = TRUE`

**Phase 1:** Storage foundations only (see `PHASE_0_DETECTION_BRAIN_CONTRACTS.md` §10).

- Detector tables + `map_ranges`/`map_events` column migrations
- No Python Detector V1 implementation yet
- No Electron guided-mapping UI
- Existing `analyseHTFSemiAuto` in Electron remains untouched

**Phase 2:** Python Detector V1 (suggestions only) — `backend/detector/`

**Phase 3:** Electron Review Candidate Panel + promotion API — suggest → decide → save truth

**Phase 3.5:** Detector performance measurement — `backend/detector_performance.py`

- Metrics from `detector_corrections` (approval/edit/rejection rates)
- Analytics view `v_detector_correction_facts`
- CLI scorecard + health summary
- Guided Workflow Engine readiness gates (measurement only; no automation)

**Phase 4 (future):** Guided Workflow Engine — machine suggests/navigates; human confirms. Not autopilot.

**Before Phase 4:** Complete production smoke test — `docs/architecture/PRODUCTION_SMOKE_TEST_PLAN_PHASE_0_3_5.md`
