# FX TrendMaster — Multi-Agent Development Plan

**Status:** Active  
**Owner:** Technical Lead  
**Last updated:** 2026-06-19

This document is the single source of truth for agent boundaries, IPC contracts, and cross-domain change control. All Composer agents working on FX TrendMaster must follow it.

---

## 1. System overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Electron Pilot (electron/src/)                                         │
│  React UI · mapping workflow · hierarchy · chart rendering              │
│  Emits raw mapping events · temporary visuals only                      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ window.electronAPI.*  (preload bridge)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Librarian (electron/electron/)                                         │
│  Main process · IPC handlers · local SQLite · candle cache · runners    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ spawns Python / reads local DB
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Sync Architect (backend/)                                              │
│  FastAPI · MT5 sync · candle_store · raw-mapping ledger API             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS (VPS)
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Python Processor (processor/) — separate agent, out of scope here      │
│  Authoritative derived state · ranges · features · ledger hash          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Golden rule (from `.cursorrules`):** Electron and Backend store/emit raw facts only. No derived range logic, phase detection, or training labels in Electron or Backend. See `docs/architecture/ARCHITECTURE_LOCK.md`.

---

## 2. Agent domains

### 2.1 Sync Architect

**Mission:** Keep the VPS evidence locker correct — candles in, raw events stored, MT5 sync reliable.

| Owns | Does not touch |
|------|----------------|
| `backend/` (all Python) | `electron/` |
| `backend/main.py` — FastAPI routes | `processor/` (unless explicitly tasked) |
| `backend/candle_store.py` | `electron/electron/` |
| `backend/candle_sync.py` | `electron/src/` |
| `backend/pull_vps_candles.py` | Preload / IPC |
| `backend/detection_brain_*.py` (API surface only) | UI components |
| `backend/tests/` | |
| `backend/detector/` (Python research brain) | |
| Deploy scripts: `backend/INSTALL_*.ps1`, `backend/QUICK_TEST_*.ps1` | |

**Primary responsibilities:**
- `/api/v1/candles/*` — fetch, bulk, status, sync-mt5, import
- `/api/v1/raw-mapping/*` — append-only raw event ledger
- MT5 → `market_memory.db` sync (raw OHLC only)
- Ledger hash contract (must match `processor/core/ledger_hash.py`)
- DB split: `DATABASE_PATH` (candles) vs `RAW_MAPPING_DB_PATH` (raw mapping)

**HTTP contract surface (Pilot may call directly):**

```text
GET  /api/v1/candles?symbol=&timeframe=&from=&to=&limit=&refresh=
GET  /api/v1/candles/status
GET  /api/v1/candles/sync-status
POST /api/v1/candles/sync-mt5
POST /api/v1/candles/import-common-files
GET  /price
GET  /api/v1/raw-mapping/events
POST /api/v1/raw-mapping/events
POST /api/v1/raw-mapping/events/batch
POST /api/v1/raw-mapping/events/delete
GET  /api/v1/raw-mapping/events/export
POST /api/v1/raw-mapping/cases
GET  /api/v1/raw-mapping/cases
```

---

### 2.2 Librarian

**Mission:** Own everything in the Electron main process — local SQLite, IPC bridges, Python subprocess orchestration, and candle cache on disk.

| Owns | Does not touch |
|------|----------------|
| `electron/electron/` (entire directory) | `electron/src/` (renderer / React) |
| `electron/electron/main.cjs` | `backend/` |
| `electron/electron/preload.cjs` | Mapping workflow logic |
| `electron/electron/localResearchIpc.cjs` | Chart rendering |
| `electron/electron/localResearchDatabase.cjs` | Hierarchy / campaign UI |
| `electron/electron/localResearchSettings.cjs` | |
| `electron/electron/localPythonRunner.cjs` | |
| `electron/electron/mediatorAi.cjs` | |
| `electron/electron/mediatorPrompts.cjs` | |
| Local `market_memory.db` path resolution & inspection | |

**Primary responsibilities:**
- Register all `ipcMain.handle(...)` channels
- Expose typed APIs via `preload.cjs` → `window.electronAPI`
- Read-only SQLite inspection (`localResearchDatabase.cjs`)
- Spawn backend Python scripts for local research (detector, range scan, pull VPS candles to local file)
- Enforce exclusive job lock (`localResearchBusy`) for long-running local tasks
- Never interpret market structure — delegate thinking to `backend/detector/` or `processor/`

**Does not:**
- Render UI or manage React state
- POST raw mapping events (Pilot calls VPS HTTP or IPC proxy if added later)
- Modify VPS databases directly without going through approved scripts

---

### 2.3 Electron Pilot

**Mission:** Everything the user sees and clicks — Map Studio, mapping campaigns, parent/child hierarchy, replay HUD, raw event emission.

| Owns | Does not touch |
|------|----------------|
| `electron/src/` (entire directory) | `electron/electron/` |
| `electron/src/main.tsx` — Map Studio shell | `preload.cjs`, `ipcMain` handlers |
| `electron/src/*Workflow*.ts` | `localResearchIpc.cjs` |
| `electron/src/*Panel*.tsx` | `backend/` |
| `electron/src/chartRenderPipeline.ts` | Direct SQLite access |
| `electron/src/viewportController.ts` | Python subprocess spawning |
| `electron/src/styles.css` | |
| `electron/src/*.test.ts` (renderer unit tests) | |
| `electron/index.html` | |

**Primary responsibilities:**
- Chart rendering, crosshair, replay cursor, overlays (temporary visuals)
- Raw mapping event capture (HIGH, LOW, REF, MANUAL_BOS, AUTO_BOS, NOTE, DELETE_RECORD)
- Case save → VPS raw-mapping routes (via `fetch`, not local derivation)
- Parent/child hierarchy UI (`hierarchyIntegrity.ts`, `parentChildCoverage.ts`, `childMappingWorkflow.ts`)
- Mapping campaigns & session persistence
- Typed IPC **client** wrappers in `localResearchClient.ts` (calls only — no handler implementation)
- AUTO_BOS threshold detection (simple break of user-set H/L — allowed per `.cursorrules`)

**Does not:**
- Open SQLite files or spawn Python directly
- Add `ipcMain.handle` or edit `preload.cjs`
- Compile ranges, assign `parent_range_id`, or write processed features

---

## 3. IPC contract (Pilot ↔ Librarian)

Pilot talks to Librarian **only** through the preload bridge. No `require('electron')` in renderer. No Node APIs in `electron/src/`.

### 3.1 Namespace

**Target (canonical):** `window.electronAPI`  
**Legacy (still present — migrate incrementally):** `window.localResearch`, `window.analyst`

New channels must be added under `window.electronAPI`. Legacy namespaces remain until explicitly retired in this document.

### 3.2 Type location

| Artifact | Owner | Path |
|----------|-------|------|
| IPC channel handlers | Librarian | `electron/electron/*Ipc.cjs`, `main.cjs` |
| Preload exposure | Librarian | `electron/electron/preload.cjs` |
| Renderer TypeScript types + call wrappers | Pilot | `electron/src/localResearchClient.ts`, `electron/src/analystClient.ts` |
| Contract tests | Pilot writes, Librarian must pass | `electron/src/localResearchIpc.test.ts` |

Pilot may add types and wrapper functions in `electron/src/`. Librarian must implement matching handlers. **Neither agent may change the contract unilaterally** — see §5.

### 3.3 `window.electronAPI.candles`

Local candle access (SQLite on disk). VPS live candles remain Sync Architect HTTP — Pilot calls `BASE_URL/api/v1/candles` directly.

```typescript
// Request / response shapes — Pilot defines types, Librarian implements

type CandleRange = {
  from?: string;       // ISO UTC or YYYY-MM-DD
  to?: string;
  limit?: number;
};

type CandleRow = {
  time: string;        // ISO UTC
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type CandlesFetchResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  source: 'local_sqlite' | 'cache';
  databasePath: string;
  candles: CandleRow[];
  error?: string;
};

type CandlesStatusResult = {
  ok: boolean;
  databasePath: string;
  exists: boolean;
  readable: boolean;
  totalCandles?: number | null;
  symbolCandles?: number | null;
  error?: string;
};

window.electronAPI.candles.fetch(symbol: string, timeframe: string, range?: CandleRange): Promise<CandlesFetchResult>
window.electronAPI.candles.status(symbol?: string, timeframe?: string): Promise<CandlesStatusResult>
window.electronAPI.candles.pullFromVps(args: { symbol: string; timeframes: string; databasePath?: string }): Promise<LocalResearchRunResult>
```

**IPC channel map (Librarian implements):**

| Preload method | IPC channel | Notes |
|----------------|-------------|-------|
| `candles.fetch` | `electron:candles:fetch` | Read from active local DB |
| `candles.status` | `electron:candles:status` | Wraps `buildDatabaseStatus` |
| `candles.pullFromVps` | `electron:candles:pull-vps` | Spawns `pull_vps_candles.py` |

### 3.4 `window.electronAPI.database`

```typescript
window.electronAPI.database.getPaths(): Promise<LocalResearchPaths>
window.electronAPI.database.getStatus(args?: { symbol?: string; timeframe?: string; databasePath?: string }): Promise<LocalResearchDatabaseStatus>
window.electronAPI.database.pickFile(): Promise<{ ok: boolean; databasePath?: string; canceled?: boolean; error?: string }>
window.electronAPI.database.setPath(args: { databasePath: string }): Promise<{ ok: boolean; databasePath: string; error?: string }>
window.electronAPI.database.openResearchFolder(): Promise<{ ok: boolean; path?: string; error?: string }>
```

**Legacy mapping:** `window.localResearch.getPaths` → `database.getPaths`, etc.

### 3.5 `window.electronAPI.research`

Long-running local Python jobs. All return `LocalResearchRunResult`:

```typescript
type LocalResearchRunResult = {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  error?: string;
  command?: string;
  parsed?: unknown;
};
```

| Preload method | IPC channel | Backend script |
|----------------|-------------|----------------|
| `research.runSeed` | `electron:research:seed` | `local_research_seed.py` |
| `research.runHistoricalRangeScan` | `electron:research:historical-range-scan` | `historical_range_scan.py` |
| `research.runBatchRangePromote` | `electron:research:batch-range-promote` | `batch_range_promote.py` |
| `research.runDetector` | `electron:research:run-detector` | `run_detector_local.py` |
| `research.listSuggestions` | `electron:research:list-suggestions` | via runner |
| `research.listDetectorRun` | `electron:research:list-detector-run` | via runner |
| `research.latestDetectorRun` | `electron:research:latest-detector-run` | via runner |
| `research.reviewSuggestion` | `electron:research:review-suggestion` | via runner |
| `research.runDetectorPerformance` | `electron:research:detector-performance` | `detector_performance.py` |
| `research.exportDetectionAudit` | `electron:research:export-detection-audit` | via runner |
| `research.runRandomRangeAudit` | `electron:research:random-range-audit` | via runner |
| `research.recordAuditVerdict` | `electron:research:record-audit-verdict` | via runner |

**Legacy mapping:** existing `local-research:*` channels — Librarian maintains both until retirement.

**Safety rule:** `batchRangePromote` with `confirm: true` requires `userConfirmed: true` from renderer (enforced in `localResearchIpc.cjs`).

### 3.6 `window.electronAPI.analyst`

Python Analyst / Mediator workspace (legacy `window.analyst`):

| Preload method | IPC channel |
|----------------|-------------|
| `analyst.getPaths` | `analyst:getPaths` |
| `analyst.checkPython` | `analyst:checkPython` |
| `analyst.run` | `analyst:run` |
| `analyst.runQuery` | `analyst:runQuery` |
| `analyst.onLog` | `analyst:log` (event) |
| … | (see `preload.cjs` for full list) |

### 3.7 IPC rules (hard constraints)

1. **Channel naming:** new channels use `electron:<domain>:<action>`; legacy `local-research:*` and `analyst:*` frozen until migrated.
2. **Args:** always a single serializable object; no functions, no class instances.
3. **Errors:** handlers return `{ ok: false, error: string }` — never throw across the bridge.
4. **Exclusive jobs:** research runners respect `localResearchBusy`; Pilot must disable UI while busy.
5. **No new global namespaces** without a row in §3 and Technical Lead sign-off in §6 changelog.
6. **Pilot never imports** from `electron/electron/`.
7. **Librarian never imports** from `electron/src/`.

---

## 4. Shared / restricted zones

These paths are **no-man's-land** — no agent edits without §6 approval:

| Path | Default owner | Rule |
|------|---------------|------|
| `DEVELOPMENT_PLAN.md` | Technical Lead | Contract changelog lives here |
| `.cursorrules` | Technical Lead | Architecture lock |
| `docs/architecture/` | Technical Lead | Update when contracts change |
| `electron/package.json` | Librarian (deps), Pilot (scripts) | Coordinate version bumps |
| `electron/vite.config.ts` | Pilot | Build config for renderer |
| `electron/vitest.config.ts` | Either | Test config — announce changes |
| `electron/tsconfig.json` | Either | Shared TS config |
| `processor/` | Processor agent (future) | All three agents read-only unless tasked |
| `scripts/` | Sync Architect | Repo-wide helper scripts |

---

## 5. Conflict rules

### 5.1 Directory lock

| Agent | MAY edit | MUST NOT edit |
|-------|----------|---------------|
| Sync Architect | `backend/**` | `electron/**`, `processor/**` (unless tasked) |
| Librarian | `electron/electron/**` | `electron/src/**`, `backend/**` |
| Electron Pilot | `electron/src/**`, `electron/index.html` | `electron/electron/**`, `backend/**` |

### 5.2 Contract changes

To add, rename, or remove an IPC method or HTTP route used cross-domain:

1. Technical Lead (or human) adds a **Contract Change** entry to §6 changelog.
2. Librarian implements handler + preload (if IPC).
3. Sync Architect implements route (if HTTP).
4. Pilot implements/adjusts client wrapper + UI.
5. Pilot updates `localResearchIpc.test.ts` (preload surface snapshot).
6. All three verify before merge.

**Forbidden without §6 entry:**
- New `ipcMain.handle` channels
- New `contextBridge.exposeInMainWorld` keys
- Changing request/response shapes
- Pilot adding direct SQLite or `child_process` usage
- Librarian adding React components
- Sync Architect adding UI or Electron code

### 5.3 Architecture violations (auto-reject)

Any agent proposing these changes must stop and escalate:

- Derived range / phase / profile logic in `electron/src/` or `backend/main.py` mapping routes
- Hard deletes in raw mapping ledger
- Using `candle_index` for durable joins
- Hash ordering that diverges from backend fingerprint
- New raw event types without user approval

### 5.4 Merge discipline

- One agent per PR when possible.
- PR title prefix: `[Sync]`, `[Librarian]`, or `[Pilot]`.
- Cross-domain PRs require §6 changelog link in description.

---

## 6. Contract changelog

| Date | Change | Approved by |
|------|--------|-------------|
| 2026-06-19 | Initial multi-agent plan; `window.electronAPI.*` target namespace defined; legacy `localResearch` / `analyst` documented | Technical Lead |

<!-- Add new rows here before implementing contract changes -->

---

## 7. Out of scope for these three agents

| Area | Owner | Notes |
|------|-------|-------|
| `processor/` | Processor agent | Only layer allowed to compile derived truth |
| `docs/` | Technical Lead | Architecture docs updated on contract changes |
| VPS deployment | Human + Sync Architect | No automated deploy from Pilot/Librarian |
| DB binary files | Never commit | `market_memory.db`, `raw_mapping_v*.db` |

---

## 8. Reference docs

- `.cursorrules` — raw ledger golden rule
- `docs/architecture/ARCHITECTURE_LOCK.md` — Electron / VPS / Processor doctrine
- `docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md` — detection brain phases
- `README.md` — repo layout and live backend domain
