# RANGE_V2 Smoke Test Plan — Phase F (`doctrine_v2`)

**Status:** Ready to execute (manual)  
**Phase:** F only — validation on real chart data  
**Goal:** Confirm `DETECTOR_RANGE_MODE=doctrine_v2` behaves correctly end-to-end before any further RANGE_V2 logic, tuning, or promotion changes.

**Out of scope:** Detector rule changes, swing/BOS/reclaim tuning, guided workflow, promotion changes, new UI features, auto-confirm.

---

## 1. Prerequisites

| Item | Requirement |
|------|-------------|
| Code | Phases A–E merged; **66 automated tests** green locally |
| Backend env | `DETECTOR_RANGE_MODE=doctrine_v2` set **before** process start |
| Backend restart | **Required** after env change — flag is read at runtime via `os.environ` |
| Electron | Build with Review Candidate panel + seed payload (`range_role`, `seed_from_electron`) |
| Symbol | **XAUUSD** with OHLC loaded for **W1** and/or **D1** |
| Confirmed structure | At least one **ACTIVE** range in `map_ranges` for the layer/timeframe under test |
| DB access | Read-only SQL on VPS `market_memory.db` (path from `MARKET_MEMORY_DB_PATH` or default) |

### 1.1 Backend flag setup

**Windows (local / VPS service env):**

```text
DETECTOR_RANGE_MODE=doctrine_v2
```

**Linux (systemd / shell):**

```bash
export DETECTOR_RANGE_MODE=doctrine_v2
# restart uvicorn / gunicorn / your FastAPI service
```

**Verify flag is active (after restart):**

- Run detector once from Electron.
- Latest `detector_suggestions` rows must show `detector_version = RANGE_V2` (not `RANGE_V1`).
- If still `RANGE_V1`, flag was not applied or backend was not restarted.

**Rollback:** unset or set `DETECTOR_RANGE_MODE=smoke_v1` and restart — restores RANGE_V1 path.

### 1.2 Layer / timeframe alignment

| Chart TF | `structure_layer` | `source_timeframe` |
|----------|-------------------|---------------------|
| W1 | WEEKLY | W1 |
| D1 | DAILY | D1 |

Review Candidate panel filters by **both**. Mismatch = empty or stale-looking list.

### 1.3 Existing helpers (read-only)

| Helper | Purpose |
|--------|---------|
| `backend/smoke_test_detection_brain_loop.py` | API + DB verification for Phase 0–3.5 loop |
| `backend/tests/test_range_v2_seed_context.py` | Automated seed wiring (not a substitute for manual smoke) |

Phase F is **manual** on real charts. Use SQL snippets below after each run.

---

## 2. Manual test setup (Electron)

1. Open **Structural Map** in Electron.
2. Set symbol **XAUUSD**.
3. Start with **W1** or **D1** chart (one layer per session; repeat plan for second TF if needed).
4. Align replay candle to the scenario you are testing (move replay bar to known BOS/reclaim context).
5. **Select** an existing confirmed **ACTIVE** range in Structural Map (or deliberately leave unselected for Case 1).
6. Click **Run Python Detector** in Review Candidate panel.
7. Open **compact** or **expanded** drawer to inspect suggestions.

**Record per run:**

- `detection_run_id` (from panel message or API response)
- Replay context label: `Context: up to YYYY-MM-DD`
- Selected `active_range_id` (if any)
- Pass/fail for case under test

---

## 3. Expected cases — pass/fail table

| Case | Setup (summary) | `candidate_kind` | Key `meta_json` | Pass? |
|------|-----------------|------------------|-----------------|-------|
| **1** | No active range selected; no single ACTIVE backend lookup | `NO_VALID_RANGE` | `no_seed_context=true`; `seed_source` = `none` or `backend_active_lookup`; `seed_lookup_error` if multiple ACTIVE | ☐ |
| **2** | ACTIVE range selected; no BOS in replay window | `NO_VALID_RANGE` | `no_seed_context=false`; `active_range_id` present; `lifecycle_state` = `ACTIVE_RANGE`, `SEEDED`, or `NO_VALID_RANGE` (seed only, no cycle) | ☐ |
| **3** | ACTIVE range + BOS; no reclaim yet | `NO_VALID_RANGE` | `lifecycle_state` = `BREACHED_UP` or `BREACHED_DOWN`; `broken_boundary` = `HIGH` or `LOW`; `active_range_id` present | ☐ |
| **4** | ACTIVE range + BOS + reclaim + linked opposite swing | `RANGE_MAJOR` or `RANGE_MINOR` | `lifecycle_state` = `RECLAIMED_UP` or `RECLAIMED_DOWN`; `boundary_selection_reason` present; `opposite_swing_index` present; boundaries per §4 | ☐ |
| **5** | Reclaim without linkable opposite swing | `NO_VALID_RANGE` | `boundary_selection_reason` = `UNCLEAR_OPPOSITE_SWING` | ☐ |

### 3.1 Case 4 — boundary expectations (doctrine)

**Bullish transition (BOS above old RH, reclaim back inside):**

| Field | Expected |
|-------|----------|
| `suggested_rh` | BOS-leg **high** (broken high), not latest swing high |
| `suggested_rl` | Linked **opposite swing low** between BOS and reclaim (or fallback per doctrine) |

**Bearish transition (BOS below old RL, reclaim back inside):**

| Field | Expected |
|-------|----------|
| `suggested_rl` | BOS-leg **low** (broken low) |
| `suggested_rh` | Linked **opposite swing high** |

**Never expect:** latest swing high + latest swing low pairing.

### 3.2 Seed trace (all cases)

When seed resolved:

| Field | Expected |
|-------|----------|
| `seed_source` | `explicit_payload`, `electron_selected_range`, or `backend_active_lookup` |
| `seed_rh` / `seed_rl` | Match confirmed active range |
| `seed_status` | `ACTIVE` |
| `no_seed_context` | `false` |

When seed missing (Case 1):

| Field | Expected |
|-------|----------|
| `no_seed_context` | `true` |
| `seed_source` | `none` (or lookup attempted with error) |

---

## 4. Review Candidate panel checklist

After each detector run, verify in UI:

| Check | Pass? |
|-------|-------|
| Chip shows `Review Candidates (N)` with **N ≥ 1** for range output (or 1 `NO_VALID_RANGE`) | ☐ |
| Context line shows **up to** current replay candle date (`Context: up to YYYY-MM-DD`) | ☐ |
| Compact card shows `candidate_kind` | ☐ |
| `detector_version` = **RANGE_V2** (in Details / expanded row) | ☐ |
| Seed trace visible in Details: `active_range_id`, `seed_source`, `no_seed_context` | ☐ |
| `lifecycle_state` visible for range rows | ☐ |
| **No stale rows** from prior replay: only suggestions matching current `detection_run_id` or `replay_until_time_ms` | ☐ |
| Changing replay candle + re-run replaces context (no March suggestions when replay is June) | ☐ |

---

## 5. DB safety checklist

### 5.1 Immediately after detector run (before any review action)

| Table | Expected | Pass? |
|-------|----------|-------|
| `detector_suggestions` | New **PENDING** rows written | ☐ |
| `map_ranges` | **Row count unchanged** | ☐ |
| `map_events` | **Row count unchanged** | ☐ |
| `detector_corrections` | **Unchanged** until user Approve/Reject/Edit | ☐ |

### 5.2 After Approve / Reject / Edit + Approve

| Check | Expected | Pass? |
|-------|----------|-------|
| `detector_suggestions.status` | Updated to APPROVED / EDITED / REJECTED | ☐ |
| `detector_corrections` | New row on reject/edit (normal correction log) | ☐ |
| `map_ranges` / `map_events` | Change **only** on explicit **Approve** (or Edit+Approve) — never on detector run alone | ☐ |
| `NO_VALID_RANGE` | Approve blocked or non-promoting (if attempted) — no silent map write | ☐ |

---

## 6. SQL verification snippets

Run on VPS (read-only). Replace placeholders: `YOUR_SYMBOL`, `YOUR_RUN_ID`, `YOUR_REPLAY_MS`.

**DB path:** typically `market_memory.db` under backend data dir — confirm via `candle_store.DB_PATH` or env.

### 6.1 Latest RANGE_V2 suggestions

```sql
SELECT
  suggestion_id,
  candidate_kind,
  detector_version,
  engine_source,
  status,
  suggested_rh,
  suggested_rl,
  range_scale,
  range_role,
  active_range_id,
  candle_time_utc_ms,
  datetime(candle_time_utc_ms / 1000, 'unixepoch') AS candle_utc,
  json_extract(meta_json, '$.detection_run_id') AS detection_run_id,
  json_extract(meta_json, '$.replay_until_time') AS replay_until_time,
  json_extract(meta_json, '$.replay_until_time_ms') AS replay_until_time_ms,
  json_extract(meta_json, '$.seed_source') AS seed_source,
  json_extract(meta_json, '$.no_seed_context') AS no_seed_context,
  json_extract(meta_json, '$.lifecycle_state') AS lifecycle_state,
  json_extract(meta_json, '$.boundary_selection_reason') AS boundary_selection_reason,
  json_extract(meta_json, '$.opposite_swing_index') AS opposite_swing_index,
  json_extract(meta_json, '$.seed_lookup_error') AS seed_lookup_error
FROM detector_suggestions
WHERE symbol = 'XAUUSD'
  AND detector_version = 'RANGE_V2'
ORDER BY created_at_utc_ms DESC
LIMIT 10;
```

### 6.2 Filter by detection run

```sql
SELECT candidate_kind, suggested_rh, suggested_rl, meta_json
FROM detector_suggestions
WHERE symbol = 'XAUUSD'
  AND json_extract(meta_json, '$.detection_run_id') = 'YOUR_RUN_ID';
```

### 6.3 Required meta_json keys (spot check)

```sql
SELECT
  suggestion_id,
  candidate_kind,
  CASE WHEN json_extract(meta_json, '$.detection_run_id') IS NOT NULL THEN 1 ELSE 0 END AS has_run_id,
  CASE WHEN json_extract(meta_json, '$.replay_until_time_ms') IS NOT NULL
            OR json_extract(meta_json, '$.replay_until_time') IS NOT NULL THEN 1 ELSE 0 END AS has_replay,
  CASE WHEN json_extract(meta_json, '$.seed_source') IS NOT NULL THEN 1 ELSE 0 END AS has_seed_source,
  CASE WHEN json_extract(meta_json, '$.no_seed_context') IS NOT NULL THEN 1 ELSE 0 END AS has_no_seed_flag,
  CASE WHEN json_extract(meta_json, '$.lifecycle_state') IS NOT NULL THEN 1 ELSE 0 END AS has_lifecycle
FROM detector_suggestions
WHERE symbol = 'XAUUSD'
  AND detector_version = 'RANGE_V2'
ORDER BY created_at_utc_ms DESC
LIMIT 5;
```

**Pass:** all five flags = 1 for latest range suggestion row.

### 6.4 map_ranges count unchanged (snapshot diff)

**Before detector run:**

```sql
SELECT COUNT(*) AS map_ranges_before FROM map_ranges WHERE symbol = 'XAUUSD';
```

**After detector run (before review):**

```sql
SELECT COUNT(*) AS map_ranges_after FROM map_ranges WHERE symbol = 'XAUUSD';
```

**Pass:** `map_ranges_before` = `map_ranges_after`.

### 6.5 map_events count unchanged

```sql
SELECT COUNT(*) AS map_events_count FROM map_events WHERE symbol = 'XAUUSD';
```

Run before and after detector; counts must match.

### 6.6 detector_corrections unchanged until review

```sql
SELECT COUNT(*) AS corrections_count FROM detector_corrections WHERE symbol = 'XAUUSD';
```

Run immediately after detector (no UI action); count must equal pre-run snapshot.

### 6.7 Active seed source for Electron run

```sql
SELECT
  json_extract(meta_json, '$.seed_source') AS seed_source,
  json_extract(meta_json, '$.active_range_id') AS active_range_id,
  json_extract(meta_json, '$.seed_rh') AS seed_rh,
  json_extract(meta_json, '$.seed_rl') AS seed_rl
FROM detector_suggestions
WHERE symbol = 'XAUUSD'
  AND detector_version = 'RANGE_V2'
  AND candidate_kind IN ('RANGE_MAJOR', 'RANGE_MINOR', 'NO_VALID_RANGE', 'NO_MINOR_STRUCTURE')
ORDER BY created_at_utc_ms DESC
LIMIT 1;
```

**Pass (range selected in UI):** `seed_source` = `electron_selected_range` or `explicit_payload`; `active_range_id` matches Structural Map selection.

### 6.8 Optional: Python read-only check (local/VPS)

```bash
cd backend
python smoke_test_detection_brain_loop.py --verify-only --symbol XAUUSD
```

Use for schema health; combine with SQL above for RANGE_V2-specific fields.

---

## 7. Manual execution log (template)

| Date | TF | Case | Run ID | Seed ID | `candidate_kind` | `lifecycle_state` | Boundaries OK? | Panel OK? | DB safe? | Result |
|------|-----|------|--------|---------|------------------|-------------------|----------------|-----------|----------|--------|
| | W1/D1 | 1 | | — | | | — | | | ☐ PASS ☐ FAIL |
| | W1/D1 | 2 | | | | | — | | | ☐ PASS ☐ FAIL |
| | W1/D1 | 3 | | | | | — | | | ☐ PASS ☐ FAIL |
| | W1/D1 | 4 | | | | | ☐ | | | ☐ PASS ☐ FAIL |
| | W1/D1 | 5 | | | | | — | | | ☐ PASS ☐ FAIL |

**Overall Phase F smoke:** ☐ PASS (all executed cases) ☐ FAIL (see bugs below)

---

## 8. Bug boundary — what fixes are allowed after smoke

### 8.1 Allowed fixes (integration bugs only)

| Category | Examples |
|----------|----------|
| Env / deploy | Flag not loaded; backend not restarted; wrong module path on VPS |
| Payload wiring | `active_range_id` / RH / RL not sent from Electron; `seed_from_electron` missing |
| Seed lookup | Wrong layer/TF filter; `MULTIPLE_ACTIVE_RANGES` handling; DB path mismatch |
| Replay context | Stale suggestions in panel; wrong `detection_run_id` filter; supersede scope |
| Persistence | `meta_json` not stored; missing `engine_source`; writer merge dropping seed fields |
| API | `run-detector` dropping optional fields; `range_mode` not honored |

### 8.2 Not allowed (defer to separate task / doctrine review)

| Category | Examples |
|----------|----------|
| Detector accuracy | “Wrong” RH/RL on valid doctrine path — tuning opposite swing pick |
| Threshold tuning | Swing displacement, BOS wick vs body, reclaim sensitivity |
| Doctrine changes | New reclaim definition; swing-pair fallback; S&R profile in RANGE_V2 |
| Promotion | Auto-approve; `NO_VALID_RANGE` promotion behavior changes |
| Guided workflow | Autopilot range birth; auto-select active range in UI |
| RANGE_V1 | Any change to smoke_v1 path for convenience |

If a failure is **doctrinal disagreement** rather than integration defect, log it in the execution log and **do not** patch detector logic under Phase F.

---

## 9. Exit criteria (Phase F complete)

| Criterion | Met? |
|-----------|------|
| `DETECTOR_RANGE_MODE=doctrine_v2` verified on target environment | ☐ |
| Cases 1–5 executed on real XAUUSD W1 or D1 data (minimum: 1, 2, 3, and one of 4/5) | ☐ |
| Review panel shows RANGE_V2 + replay context + seed trace | ☐ |
| SQL confirms `detector_version=RANGE_V2`, `engine_source=python_detector`, required `meta_json` keys | ☐ |
| `map_ranges` / `map_events` unchanged by detector-only run | ☐ |
| No integration bugs open OR bugs logged with allowed-fix classification | ☐ |

**Phase G / later:** promotion hardening for `NO_VALID_RANGE`, CLI `--range-mode` extension, production cutover decision.

---

## 10. References

- `docs/architecture/RANGE_V2_DOCTRINE_CONTRACT.md` — locked rules
- `docs/architecture/RANGE_V2_IMPLEMENTATION_PLAN.md` — phases A–E
- `docs/architecture/PRODUCTION_SMOKE_TEST_PLAN_PHASE_0_3_5.md` — base detection brain loop
- `backend/smoke_test_detection_brain_loop.py` — API/DB helper
- `backend/tests/test_range_v2_seed_context.py` — automated seed tests (66 total with suite)
