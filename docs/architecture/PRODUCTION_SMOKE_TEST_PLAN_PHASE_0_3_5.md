# Production Smoke Test Plan — Phase 0–3.5

**Status:** Ready to execute  
**Goal:** Validate the full suggest → decide → save truth loop on real XAUUSD data before Phase 4 (Guided Workflow Engine).  
**Out of scope:** Detector tuning, threshold changes, guided workflow, autopilot, new detector logic.

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| Backend | Latest code deployed on VPS; **service restarted** after deploy |
| Database | `market_memory.db` has XAUUSD OHLC for **W1** and/or **D1** |
| Electron | Build includes Review Candidate panel (`electron` ≥ 0.0.27, `npm run build`) |
| API base | `https://api01.apexcoastalrentals.co.za` |
| VPS shell | SSH access to run `python detector_performance.py` against production DB |

### Current preflight result (2026-06-17)

Automated preflight against production VPS shows a **deploy blocker** (not a code defect):

| Check | Result |
|-------|--------|
| `/api/v1/candles/status` | HTTP 200 but **`detection_brain` block missing** |
| `/api/v1/detection-brain/*` | **HTTP 404** — routes not on VPS |

**Follow-up (same day):** routes returned 200 but `ModuleNotFoundError` — `vps_restart_backend.bat` only copied `main.py` + `candle_store.py`. Fixed: bat now copies all `backend/*.py` and `backend/detector/`. **Re-run restart bat after pulling this fix.**

**Action required before Electron smoke test:** deploy latest `backend/` to VPS and restart FastAPI. Re-run:

```bash
python smoke_test_detection_brain_loop.py --preflight --symbol XAUUSD --timeframe W1
```

All three Step 2/5/6 checks must PASS before opening Electron.

---

### Deploy checklist (before smoke test)

1. Push/pull latest `backend/` to VPS (includes `detection_brain_*`, `detector/`, `detector_performance.py`).
2. Restart FastAPI via `scripts/vps_restart_backend.bat` — copies **all** `backend/*.py` + `backend/detector/` into `trading_gate/app/`.
3. Confirm new routes exist (404 = not deployed):
   - `GET /api/v1/detection-brain/suggestions`
   - `POST /api/v1/detection-brain/run-detector`
   - `POST /api/v1/detection-brain/suggestions/review`
4. Rebuild Electron if UI panel is missing: `cd electron && npm run build`.

---

## Layer / timeframe alignment (critical)

Detector infers `structure_layer` from `source_timeframe`:

| Chart TF | Set structure layer | Set source TF |
|----------|---------------------|---------------|
| W1 | WEEKLY | W1 |
| D1 | DAILY | D1 |

Review Candidate panel filters by **both** fields. Mismatch = empty list even after detector runs.

---

## Test path (13 steps)

### Step 1 — Restart backend

Restart the VPS FastAPI process. Wait until health responds.

**Pass:** API responds within 30s.

---

### Step 2 — Confirm `/status` reports `detection_brain.ok = true`

```bash
curl -s "https://api01.apexcoastalrentals.co.za/api/v1/candles/status" | jq '.detection_brain'
```

**Pass criteria:**

```json
{
  "ok": true,
  "schema_version": "detection_brain_v0",
  "tables": {
    "detector_suggestions": { "exists": true },
    "detector_corrections": { "exists": true }
  },
  "analytics_views": {
    "v_detector_correction_facts": true
  },
  "map_ranges_phase1_ready": true,
  "map_events_phase1_ready": true
}
```

Top-level `ok` must also be `true`.

**Fail actions:** Check backend logs for migration errors; run `init_db()` path; verify `detection_brain_schema.py` deployed.

---

### Step 3 — Open Electron Structural Map

1. Launch Electron cockpit.
2. Select **Mark** tab → **Structural Map** (not Manual Case / Raw Ledger).
3. Symbol: **XAUUSD**.

**Pass:** Structural Map pane loads without console crash.

---

### Step 4 — Load XAUUSD W1 or D1

1. Set **structure layer** = `WEEKLY` (W1) or `DAILY` (D1).
2. Set **source timeframe** to match (`W1` or `D1`).
3. Load chart candles for that timeframe (sync/import if empty).

**Pass:** Chart renders OHLC; sidebar shows VPS online.

**Verify OHLC on VPS:**

```bash
curl -s "https://api01.apexcoastalrentals.co.za/api/v1/candles/status" | jq '.groups[] | select(.symbol=="XAUUSD")'
```

---

### Step 5 — Run Python Detector

In **Review Candidates** panel → click **Run Python Detector**.

**Pass:** Message like `Python detector wrote N suggestion(s)` where N ≥ 1.

**API equivalent:**

```bash
curl -s -X POST "https://api01.apexcoastalrentals.co.za/api/v1/detection-brain/run-detector" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","source_timeframe":"W1","limit":500}'
```

**Fail actions:**

| Error | Likely cause |
|-------|----------------|
| 404 | Routes not deployed |
| `DETECTION_BRAIN_RUN_FAILED` | Import error / missing `detector/` on VPS |
| `written_count: 0` | No OHLC, or no range context / no detectable structure |

---

### Step 6 — Confirm PENDING suggestions appear

Click **Refresh** in Review Candidates.

**Pass:** List shows ≥ 1 row with `candidate_kind`, `detector_version`, `engine_source: python_detector`.

**API check:**

```bash
curl -s "https://api01.apexcoastalrentals.co.za/api/v1/detection-brain/suggestions?symbol=XAUUSD&structure_layer=WEEKLY&source_timeframe=W1&status=PENDING"
```

---

### Step 7 — Approve one clean candidate

Select a range or BOS candidate that looks correct → **Approve**.

**Pass:**

- UI message confirms promotion (`range #id` or `event #id`).
- Candidate disappears from PENDING list (or list refreshes).

---

### Step 8 — Edit + Approve one candidate

Run detector again if needed for a fresh candidate. Edit RH/RL or event price → **Edit + Approve**.

**Pass:**

- Confirmed structure uses **edited** values (not original suggestion).
- `detector_corrections.error_category` ≠ `NO_ERROR` (e.g. `WRONG_RH`).

---

### Step 9 — Reject one bad candidate

Run detector if needed. Select weak candidate → choose reject category → **Reject**.

**Pass:**

- UI confirms rejection.
- No new `map_ranges` / `map_events` row for that suggestion.

---

### Step 10 — Database truth checks (VPS)

Run on VPS against production `market_memory.db`:

```bash
cd /path/to/backend
python smoke_test_detection_brain_loop.py --verify-only --symbol XAUUSD
```

Or manual SQL:

```sql
-- Suggestion statuses
SELECT suggestion_id, candidate_kind, status, user_action, promoted_range_id, promoted_event_id
FROM detector_suggestions
WHERE symbol = 'XAUUSD'
ORDER BY updated_at_utc_ms DESC
LIMIT 20;

-- Corrections for three actions
SELECT user_action, error_category, candidate_kind, detector_version
FROM detector_corrections
WHERE symbol = 'XAUUSD'
ORDER BY created_at_utc_ms DESC
LIMIT 10;

-- Promoted ranges only from approved/edited
SELECT id, range_high_price, range_low_price, confirmed_from_suggestion_id, user_action_at_confirm
FROM map_ranges
WHERE symbol = 'XAUUSD' AND confirmed_from_suggestion_id IS NOT NULL
ORDER BY updated_at DESC
LIMIT 10;
```

**Pass criteria:**

| Check | Expected |
|-------|----------|
| Approved suggestion | `status = APPROVED`, `user_action = APPROVE` |
| Edited suggestion | `status = EDITED`, `user_action = EDIT` |
| Rejected suggestion | `status = REJECTED`, `user_action = REJECT` |
| Approve correction | `error_category = NO_ERROR` |
| Edit/Reject correction | `error_category` ≠ `NO_ERROR` |
| Reject | No `promoted_range_id` / `promoted_event_id` on suggestion |
| Duplicate approve | Second click returns duplicate; **one** confirmed row per suggestion |

**Duplicate approve test:** Re-POST review for an already-approved `suggestion_id`. Expect `duplicate: true`, no extra `map_ranges` row.

---

### Step 11 — Run performance report

On VPS (same DB):

```bash
cd /path/to/backend
python detector_performance.py --symbol XAUUSD
```

**Pass:** Report shows `Reviewed ≥ 3` and non-zero approval/edit/rejection rates after steps 7–9.

JSON variant:

```bash
python detector_performance.py --symbol XAUUSD --json
```

---

### Step 12 — Confirm rates in report

**Pass criteria:**

- `SUMMARY.total_reviewed` ≥ 3
- `approval_rate`, `edit_rate`, `rejection_rate` all present (not `n/a`)
- `SCORECARD` lists candidate kinds you reviewed
- `ERROR CATEGORIES` includes `NO_ERROR` plus at least one non-`NO_ERROR` from edit/reject

---

### Step 13 — Manual mapping still works

Without using the detector:

1. Place RH/RL anchors on chart (Structural Map).
2. Save range via existing **Save** flow (`POST /api/v1/map/range`).
3. Optionally place manual BOS via structural event save.

**Pass:**

- Range saves without error.
- Explorer tree refreshes.
- Saved range visible on chart.
- No interference from detector suggestions (manual path independent).

---

## Automated helper script

Local or VPS:

```bash
# API preflight (steps 2, 5, 6) — no mutations
python smoke_test_detection_brain_loop.py --base-url https://api01.apexcoastalrentals.co.za --preflight --symbol XAUUSD --timeframe W1

# Full API loop (steps 2, 5–10, 11–12) — creates review actions on real suggestions
python smoke_test_detection_brain_loop.py --base-url https://api01.apexcoastalrentals.co.za --symbol XAUUSD --timeframe W1 --run-loop

# DB verify only (step 10) after manual Electron steps
python smoke_test_detection_brain_loop.py --verify-only --symbol XAUUSD
```

---

## Bug fix boundary (smoke test only)

Fix **only** if observed:

| Severity | Examples |
|----------|----------|
| Critical | API 404/500 on detection-brain routes; migration failure; promotion crash; duplicate confirmed rows; Electron panel crash; manual save broken |
| Not in scope | Detector accuracy; threshold tuning; UI polish; Phase 4 workflow |

---

## Sign-off template

| Step | Pass/Fail | Notes |
|------|-----------|-------|
| 1 Backend restart | | |
| 2 detection_brain.ok | | |
| 3 Electron Structural Map | | |
| 4 XAUUSD W1/D1 loaded | | |
| 5 Run detector | | |
| 6 PENDING visible | | |
| 7 Approve | | |
| 8 Edit + approve | | |
| 9 Reject | | |
| 10 DB truth | | |
| 11 Performance CLI | | |
| 12 Rates shown | | |
| 13 Manual mapping | | |

**Smoke test result:** PASS / FAIL  
**Date:**  
**Tester:**  
**Blockers for Phase 4:** (list any)

---

## References

- `backend/detection_brain_promotion.py` — promotion workflow
- `backend/detector_performance.py` — measurement CLI
- `electron/src/reviewCandidatePanel.tsx` — review UI
- `docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md` — contracts
