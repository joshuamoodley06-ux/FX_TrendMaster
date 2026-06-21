# Electron Research Workstation Architecture

**Status:** Adopted 2026-06-17 — migration in progress (foundation phase)  
**Related:** `RANGE_V2_IMPLEMENTATION_PLAN.md` · `RANGE_PROFILE_ANALYTICS_PLAN.md` · `.cursorrules`

---

## 1. Problem statement

Heavy detection and research workflows were routed through the live FastAPI backend. That caused:

- SQLite lock contention (API + bulk promote + long scans)
- nginx / API gateway timeouts on multi-minute jobs
- Deployment-copy confusion (stale `backend/` files on VPS)
- Risk to the live execution path (candles, mapping save, trading gate)

**Decision:** Backend stays **light and stable**. Electron + **local Python** becomes the **heavy research workstation**.

---

## 2. Responsibility split

### 2.1 Backend / FastAPI (light)

| Allowed | Not allowed (migrate off API) |
|---------|-------------------------------|
| Serve candles | Historical range scans (multi-candle replay walk) |
| Store confirmed ranges / events | Bulk batch promote (79+ rows) |
| Simple status / list APIs | Profile analytics batch jobs |
| Small save / review (single suggestion) | Long-running SQL research |
| Live app / execution stability | Detector period scans over API |

Existing heavy API routes **remain** for rollback but must **not** be used for production research workflows.

### 2.2 Electron / local Python (heavy)

| Responsibility |
|----------------|
| Run detector (single-candle / replay context) |
| Historical `historical_range_scan.py` |
| `batch_range_promote.py` (dry-run + confirm) |
| Random visual audit (chart loader + local DB read) |
| Profile analytics (future) |
| `detector_performance.py` / SQL research |
| Heavy SQL analysis against a **local DB copy** |

---

## 3. Scripts that move to local execution (first wave)

| Script | Purpose | API equivalent (deprecated for bulk) |
|--------|---------|--------------------------------------|
| `backend/historical_range_scan.py` | Walk replay steps; write suggestions only | `POST /api/v1/detection-brain/run-detector` (period_scan) |
| `backend/batch_range_promote.py` | Dry-run / confirm promote to `map_ranges` | `POST /api/v1/detection-brain/ranges/batch-promote` |
| `backend/detector_performance.py` | Correction metrics / scorecard | (no stable public API yet) |

**Future local scripts:** random audit sampler, profile analytics classifier, ad-hoc SQL inspectors.

---

## 4. DATABASE_PATH resolution

Local Python uses the same `candle_store._resolve_db_path()` rules as backend:

**Priority:**

1. `DATABASE_PATH` env var (absolute or relative to `backend/`)
2. `RAW_MAPPING_DB_PATH` env var
3. `MARKET_MEMORY_DB_PATH` env var
4. Default: `backend/data/raw_mapping_v159.db`

**Electron local runner sets:**

```text
DATABASE_PATH=<user-chosen local copy>
RAW_MAPPING_DB_PATH=<same path unless split explicitly>
DETECTOR_RANGE_MODE=doctrine_v2
DETECTOR_RANGE_SCALE_MODE=generic
PYTHONPATH=<backend folder>   # so `import candle_store` works
```

**Recommended local layout:**

```text
Documents/FXTM_Research/
  raw_mapping_v159.db      # working copy (sync from VPS or export)
  logs/                    # optional stdout captures
```

**Override without code changes:**

```text
FXTM_BACKEND_DIR=C:\path\to\FX_TrendMaster\backend
DATABASE_PATH=C:\Users\...\Documents\FXTM_Research\raw_mapping_v159.db
```

Never point local bulk jobs at the **live VPS DB file** over network mounts while FastAPI is writing.

---

## 5. How Electron launches local Python

**Pattern:** Node `child_process.spawn` from the **Electron main process** (not renderer).

Foundation module:

- `electron/src/localPythonRunner.ts` — command builder, env, spawn, output parsers
- Future: `electron/electron/localPythonRunner.cjs` IPC bridge (same as analyst spawn)

**Flow:**

```text
Renderer (optional UI)
  → preload IPC `localResearch:run`
    → main.cjs spawn(python, [script.py, ...args], { cwd: backendDir, env })
      → stdout/stderr streamed to UI log panel
        → parsed summary returned to renderer
```

**Python executable:** `python` or user override (`FXTM_PYTHON` / settings).

**Working directory:** `backend/` (scripts use `import candle_store`).

**Packaged builds:** `backend/` must be shipped beside `python_analyst/` (asarUnpack) — follow-up packaging task.

---

## 6. How outputs are read back into Electron

| Script | Output channel | Parser |
|--------|----------------|--------|
| `historical_range_scan.py` | stdout text summary | `parseHistoricalScanOutput()` |
| `batch_range_promote.py --json` | stdout JSON | `parseBatchPromoteOutput()` |
| `detector_performance.py --json` | stdout JSON | `parseDetectorPerformanceOutput()` |

Electron stores last run result in memory (and optionally `Documents/FXTM_Research/logs/<run_id>.txt`).

Visual audit does **not** require script output — it reads DB via chart loader + optional local SQL.

---

## 7. Rollback strategy

1. **API routes stay** — flip workflow back to VPS API if local runner fails.
2. **No schema changes** in this migration phase.
3. **No detector logic deletion** — same Python modules, different invocation path.
4. **Feature flag** (future): Electron setting `researchMode: local | remote`.
5. **DB safety:** local copy is disposable; VPS remains source of truth until explicit sync.

---

## 8. Migration phases

| Phase | Scope | Status |
|-------|-------|--------|
| **A** | Architecture doc + `localPythonRunner.ts` foundation | This document |
| **B** | IPC wiring + dev Research panel (scan / promote / audit) | Next task |
| **C** | Deprecate heavy API usage in Review panel | After B proven |
| **D** | Profile analytics local-only | After batch audit gate |

---

## 9. Golden rules

1. **Never bulk-promote through live API** in production research.
2. **Never historical-scan through live API** for multi-month windows.
3. **Backend restart** must not be required for research jobs.
4. **Local DB copy** for heavy jobs; sync results up via normal save APIs or file deploy.
5. **Detector logic** changes only in `backend/detector/` — invocation path is separate concern.
