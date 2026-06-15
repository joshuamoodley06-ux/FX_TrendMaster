# Python Analyst V1.1 — Rule Engine + Data Collection Statistics UI Plan

Status: PLAN APPROVED (decisions locked, see section 7) — no implementation yet.

---

## 0. What this is

A local, rule-based structural analyzer ("Python Analyst V1.1") plus a rebuilt
**Data Collection Statistics** page in Electron that drives it.

- Not AI. Not ML. Not prediction. Rule-based structural statistics only.
- Python answers: retracement depth inside parent, BOS+reclaim, BOS+abandon,
  bounce between extremes, child-range counts before parent break, post-reclaim outcome.

### Fit with the locked architecture

| Layer | Role in this feature | Allowed? |
|---|---|---|
| Electron | Select cases, fetch raw data from VPS, write input JSON, spawn local Python, display reports | Yes — no interpretation, no durable truth |
| VPS Backend | Serves existing endpoints read-only. **Zero backend changes.** | Yes |
| Python Analyst | The only layer that thinks: zones, retracement, reclaim/abandon, rotations, sequences | Yes — Python is the sanctioned brain |

The analyst never writes to any DB, never repairs mappings, never POSTs to the VPS.
All output is local files under its own workspace.

---

## 1. Where things live

```
FX_TrendMaster/
  electron/
    python_analyst/                  <- NEW: analyst code lives inside electron per request
      analyst_v1.py                  <- CLI entry (matches spec command lines)
      analyst/                       <- package
        io/        input_loader.py, candle_frame.py
        models/    derived_fields.py, zones.py, retracement.py,
                   bos_reclaim.py, bos_abandon.py, rotation.py,
                   sequence.py, outcome.py
        audit/     audit_warnings.py, hierarchy_check.py
        storage/   workspace.py (yearly parquet/json), combined.py
        reports/   csv_writer.py, json_writer.py, markdown_writer.py
      requirements.txt               <- pandas, pyarrow
    src/
      analystPage.tsx                <- NEW: Data Collection Statistics page (own file,
                                        keeps main.tsx from growing)
      analystClient.ts               <- NEW: VPS fetchers + input-package builder
    electron/
      main.cjs                       <- MODIFIED: IPC handlers + python spawn
      preload.cjs                    <- NEW: contextBridge for the renderer

%USERPROFILE%\Documents\FXTM_Analyst\   <- workspace OUTSIDE the repo (decided)
  input/                                <- Electron-written input packages
    XAUUSD_2020.json
  workspace/
    XAUUSD/
      2019/  input_snapshot.json
             normalized_ranges.parquet
             normalized_events.parquet
             yearly_stats.json
             reports/                   <- all per-year CSV/MD/JSON outputs
      2020/  ...
      combined/
        XAUUSD_combined_stats.json
        XAUUSD_year_comparison.csv
        XAUUSD_combined_report.md
```

Notes:

- `electron/python_analyst/` is separate from the root `processor/` package.
  The processor (raw-ledger compiler) is untouched. The analyst is a read-only
  consumer of already-saved ranges/events; if the processor later becomes the
  range compiler of record, the analyst input builder swaps sources without
  changing the rule engine.
- The workspace lives outside the repo at `Documents\FXTM_Analyst\` so data
  never pollutes git. The path is shown in the UI and overridable there.

---

## 2. Data flow (end to end)

```
1. User opens Data Collection Statistics page
2. UI lists saved cases from VPS        GET /api/v1/raw-mapping/cases  (raw:{uuid})
                                        GET /api/v1/mos/seed-ideas     (case:{id}, legacy)
3. User picks symbol + year + cases (explicit multi-select; never "all by default")
4. Electron fetches, per selected case_ref:
     ranges   GET /api/v1/map/ranges?case_ref=...&limit=...
     events   GET /api/v1/map/events?case_ref=...&limit=...
     raw ledger (raw cases only, for audit cross-check)
              GET /api/v1/raw-mapping/events/export?case_id=...
5. Electron derives the candle requirements from the fetched data:
     timeframes = distinct chart_timeframe/source_timeframe/timeframe seen
     window     = min(anchor/event time) - padding .. max(...) + padding
     candles  GET /api/v1/candles?symbol&timeframe&start&end (chunked)
6. Electron writes ONE input package JSON to Documents\FXTM_Analyst\input\<label>.json
7. Electron spawns:  python analyst_v1.py --input <pkg> --output <workspace/SYMBOL/YEAR>
8. Python runs offline against the package only (no network), writes reports
9. Electron reads output files via IPC and renders the report tabs
```

### Input package JSON (written by Electron, read by Python)

Spec manifest plus embedded data so Python needs no network access:

```json
{
  "schema_version": "analyst_input_v1",
  "symbol": "XAUUSD",
  "year": 2020,
  "label": "XAUUSD_2020",
  "case_refs": ["raw:...", "case:12"],
  "generated_at_utc_ms": 0,
  "source": { "base_url": "https://api01....", "fetched_at": "..." },
  "data": {
    "ranges":  [ /* map_ranges rows verbatim, all columns */ ],
    "events":  [ /* map_events rows verbatim, incl. candle OHLC cols */ ],
    "candles": { "D1": [ /* {time,open,high,low,close,volume} */ ], "H4": [], ... },
    "raw_ledgers": { "raw:{uuid}": { /* export payload incl. ledger_hash */ } }
  }
}
```

- Rows are passed verbatim — Electron does not rename, filter, or interpret fields.
- Python ignores unknown fields and preserves originals (same parser rule as processor).
- Python only analyzes the case_refs listed. Never all cases by default.

### Field mapping (spec -> actual backend columns)

All spec-required range fields exist on `map_ranges` /
`/api/v1/map/ranges` responses: `range_id (id)`, `case_ref`, `symbol`,
`structure_layer`, `source_timeframe`, `chart_timeframe`, `parent_range_id`,
`old_range_id`, `new_range_id`, `status`, `range_high_price`, `range_low_price`,
`range_high_time`, `range_low_time`, `range_start_time`, `range_end_time`,
`active_from_time`, `inactive_from_time`, `direction_of_break`,
`broken_by_event_id`, `created_by_event_id`.

Event fields come from `map_events`: `event_type`, `structure_layer`,
`source_timeframe`, `active_range_id`, `parent_range_id`, `event_time`,
`event_price`, `direction`, `candle_open/high/low/close`.

Candles come from the `candles` table via `/api/v1/candles`.

---

## 3. Python rule engine (V1.1 scope)

### 3.1 Derived range fields (computed per range, never stored back)

```
anchor_start    = range_start_time  || min(range_high_time, range_low_time)
anchor_end      = range_end_time    || max(range_high_time, range_low_time)
lifecycle_start = active_from_time  || anchor_start
lifecycle_end   = inactive_from_time || null
price_span      = abs(range_high_price - range_low_price)
```

### 3.2 Premium / Discount / Fair Price zones

```
price_position_percent = (price - range_low) / (range_high - range_low)

Discount   0.00–0.33   (M1 0.00–0.11, M2 0.11–0.22, M3 0.22–0.33)
Fair Price 0.33–0.66   (M1 0.33–0.44, M2 0.44–0.55, M3 0.55–0.66)
Premium    0.66–1.00   (M1 0.66–0.77, M2 0.77–0.88, M3 0.88–1.00)
```

Per child range vs its parent: RH position, RL position, midpoint position,
BOS price position (if event available), start zone, break zone.
Output: `range_zone_position.csv`.

### 3.3 Retracement model

Per BOS-created range sequence (old range breaks -> new range forms):

```
bullish: retracement_percent = (impulse_high - lowest low after BOS before
         next BOS/abandon) / (impulse_high - impulse_low)
bearish: mirrored with highest high
classes: shallow 0–0.33, mid 0.33–0.66, deep 0.66–1.00, extreme >1.00
```

Output: `retracement_stats.csv` with columns: case_ref, symbol,
parent_range_id, range_id, structure_layer, direction_of_break,
retracement_percent, retracement_class, retracement_price, retracement_time,
next_bos_direction, outcome.

### 3.4 BOS + Reclaim model

BOS = range marked BROKEN with direction_of_break + broken_by_event_id +
inactive_from_time. Reclaim = candle close back across the broken boundary
(above prior range high after BOS_UP pullback; below prior range low after
BOS_DOWN pullback), detected from candles.

Detects: bos direction, reclaim true/false, reclaim_time,
reclaim_candle_count_after_bos, reclaim_depth_percent, reclaim_class
(shallow/mid/deep), continuation_after_reclaim, candles_to_continuation_bos,
abandon_after_reclaim. Output: `bos_reclaim_report.csv`.

### 3.5 BOS + Abandon model (Rule V1)

```
After BOS_UP:   no continuation BOS_UP before breaking below new range low
                -> BOS_UP_ABANDONED
After BOS_DOWN: mirrored -> BOS_DOWN_ABANDONED
```

Saved ranges first: `new_range_id` breaking opposite -> failed continuation;
status ABANDONED -> abandon; no next range -> unresolved.
Output: `bos_abandon_report.csv` (old_range_id, new_range_id, bos_direction,
abandoned, abandon_reason, opposite_break_time, candles_before_abandon).

### 3.6 Bounce between extremes (rotation) model

Per parent range, over child ranges/candles inside parent lifecycle:
premium touches (high >= 0.66 threshold price), discount touches
(low <= 0.33 threshold price), full rotations each way, rotations before
parent BOS, final break direction.
Output: `extreme_rotation_report.csv` (parent_range_id, parent_layer,
child_layer, premium_touches, discount_touches, rotations_count,
final_break_direction, child_count_before_break).

### 3.7 Impulse / Retest sequence model

Neutral mechanical labels only (no P1/P2/P3 stored as truth):
first BOS in new direction = impulse_1, pullback/reclaim = retest_1,
next same-direction BOS = impulse_2, etc.
Output: `impulse_retest_sequence.csv` (case_ref, parent_range_id,
child_range_id, layer, sequence_direction, impulse_index, retest_index,
bos_event_id, reclaim_detected, retracement_class, next_outcome).

### 3.8 Outcome classification

`CONTINUED | FAILED | ABANDONED | UNRESOLVED | OPPOSITE_BOS | PARENT_BOS`
per spec definitions, applied to every detected setup/sequence.

### 3.9 Audits (warn, never crash)

- Wrong/missing parent links -> `audit_warnings.csv` + `hierarchy_completeness.csv`
- Weekly root accepted when Macro absent
- Anchor span oddities warn but do not fail analysis
- Raw ledger hash recomputed and compared against export `ledger_hash`
  (mismatch = warning row, analysis continues)
- Missing candles for a needed timeframe/window -> warning + affected rules
  emit UNRESOLVED instead of crashing

### 3.10 Reports produced per run

```
output/
  analyst_summary.json        analyst_report.md
  audit_warnings.csv          hierarchy_completeness.csv
  range_zone_position.csv     retracement_stats.csv
  bos_reclaim_report.csv      bos_abandon_report.csv
  extreme_rotation_report.csv impulse_retest_sequence.csv
  yearly_summary.csv          combined_summary.csv
```

### 3.11 Yearly storage / incremental stats

One year at a time. Each run saves `input_snapshot.json`,
`normalized_ranges.parquet`, `normalized_events.parquet`, `yearly_stats.json`,
`reports/` under `workspace/<SYMBOL>/<YEAR>/`. Combined artifacts are rebuilt
from all saved `yearly_stats.json` files only — raw history is never reloaded.

### 3.12 CLI

```
python analyst_v1.py --input "%USERPROFILE%\Documents\FXTM_Analyst\input\XAUUSD_2020.json" --output "%USERPROFILE%\Documents\FXTM_Analyst\workspace\XAUUSD\2020"
python analyst_v1.py --rebuild-combined --symbol XAUUSD --workspace "%USERPROFILE%\Documents\FXTM_Analyst\workspace"
```

### 3.13 Hard limits (V1.1)

No ML. No DB writes. No auto-repair of mappings. No trade signals.
No R-multiple. No live alerts. Read-only against the VPS (and in practice
fully offline — Electron does the fetching).

---

## 4. Electron changes

### 4.1 Main process + preload (new plumbing)

Today `main.cjs` has no IPC, no preload, and never spawns processes. Add,
keeping `contextIsolation: true` / `nodeIntegration: false`:

| IPC channel | Does |
|---|---|
| `analyst:writeInput` | Write input package JSON to `Documents\FXTM_Analyst\input\` |
| `analyst:run` | Spawn `python analyst_v1.py ...`, stream stdout/stderr to renderer |
| `analyst:rebuildCombined` | Spawn rebuild-combined command |
| `analyst:cancel` | Kill a running analyst process |
| `analyst:listWorkspace` | List symbols/years/reports in the workspace |
| `analyst:readReport` | Read one output file (CSV/JSON/MD) for display |
| `analyst:checkPython` | Resolve/verify python executable + deps |

Preload (`preload.cjs`) exposes exactly these as `window.analyst.*`.
File access is restricted to the workspace root (`Documents\FXTM_Analyst\`,
overridable in the UI). Python executable path is configurable in the UI
(default `python` on PATH) and persisted in localStorage.

### 4.2 Data Collection Statistics page (replaces current Data Collection)

Cleanup: the current `DataCollectionPage` (Lifecycle Scenario Calculator
posting to `/api/v1/lifecycle/scenario/calculate`) is removed along with its
result panel. The backend endpoint stays untouched. Sidebar label becomes
**Data Collection Statistics** (same `page: 'data'` key). New page lives in
its own file `analystPage.tsx` — not added to the 8.8k-line `main.tsx` blob.

UI layout, top to bottom, matching the analyst workflow:

```
+----------------------------------------------------------------------+
| 1. CASE SELECTION                                                    |
|  symbol picker | year picker | refresh | search                      |
|  [ ] case rows: name, case_ref, symbol, base TF, updated, scope      |
|  multi-select checkboxes; "n selected" pill; explicit select only    |
+----------------------------------------------------------------------+
| 2. DATA PACKAGE BUILDER                                              |
|  label preview (XAUUSD_2020) | padding setting | timeframe override  |
|  [Fetch + Build Package] -> per-case fetch progress with counts:     |
|    ranges n / events n / candles per TF n / ledger ok + hash badge   |
|  validation strip: missing parents, empty candles -> shown as        |
|  warnings only (dumb display of fetch facts, no interpretation)      |
+----------------------------------------------------------------------+
| 3. RUN PANEL                                                         |
|  python path field + check badge | output dir (auto: SYMBOL/YEAR)    |
|  [Run Analyst] [Rebuild Combined] [Cancel] | live stdout log pane    |
+----------------------------------------------------------------------+
| 4. RESULTS                                                           |
|  summary KPI row from analyst_summary.json (cases, ranges, BOS up/   |
|  down, reclaim rate, abandon rate, rotation avg, unresolved count)   |
|  tabs: Report (markdown render) | Zones | Retracement | BOS+Reclaim  |
|        | BOS+Abandon | Rotations | Sequences | Audit Warnings        |
|  each CSV tab = sortable table + export-opens-file button            |
+----------------------------------------------------------------------+
| 5. WORKSPACE / YEARS                                                 |
|  per-symbol year list with status (analyzed date, counts)            |
|  combined view: year comparison table + combined report markdown    |
+----------------------------------------------------------------------+
```

Electron displays numbers Python produced; it computes nothing itself.

### 4.3 What Electron explicitly does NOT do

- No zone/retracement/reclaim math in the renderer.
- No writes to `/api/v1/map/*` or `/api/v1/raw-mapping/*` from this page (read-only fetches).
- No durable truth: input packages and reports are disposable local files.

---

## 5. Implementation phases (for later, after plan approval)

1. **Phase A — Python skeleton:** package layout, CLI, input loader, derived
   fields, workspace writer; runs against a hand-made fixture JSON.
2. **Phase B — Rule models:** zones -> retracement -> bos_reclaim ->
   bos_abandon -> rotation -> sequence -> outcomes, each with a small pytest
   fixture case (synthetic ranges/candles).
3. **Phase C — Reports + yearly/combined storage.**
4. **Phase D — Electron plumbing:** preload + IPC + spawn + workspace reader.
5. **Phase E — UI:** remove scenario calculator, build new page sections 1–5.
6. **Phase F — Acceptance test** (section 6) against a real selected case set.

Touched files only: `electron/electron/main.cjs`, new `preload.cjs`, new
`electron/src/analystPage.tsx` + `analystClient.ts`, minimal `main.tsx` edits
(nav label + page mount), new `electron/python_analyst/**`.
Backend and `processor/` are not touched.

## 6. Acceptance test (from spec)

Input: selected cases with Macro/Weekly/Daily/Intraday/Micro hierarchy, at
least one BOS_UP, one BOS_DOWN, one child sequence inside a parent, one wrong
parent warning.

Expected:

- Reports generate without crashing
- Weekly root accepted when Macro absent
- Parent lifecycle uses active_from_time / inactive_from_time
- Anchor span warnings do not fail analysis
- Wrong parent links appear in audit warnings
- Zone report classifies Premium/Fair/Discount (+ thirds)
- Retracement report classifies shallow/mid/deep/extreme
- BOS reclaim report detects reclaim or unresolved
- Extreme rotation report counts premium/discount touches + rotations
- Combined yearly report updates after a second year is analyzed

## 7. Decisions (locked with user, 2026-06-13)

1. **Old scenario calculator:** delete entirely. Backend
   `/api/v1/lifecycle/scenario/calculate` endpoint stays untouched.
2. **Year handling:** year is a user-chosen package label; the case list
   filters by symbol and shows updated/replay dates for manual selection.
3. **Candle fetching:** only fetch timeframes actually present in the selected
   cases' ranges/events, chunked by time window, with a manual override field.
4. **Python runtime:** system Python 3.11+ with pandas/pyarrow from
   `electron/python_analyst/requirements.txt`; executable path configurable in UI.
5. **Workspace location:** outside the repo at `%USERPROFILE%\Documents\FXTM_Analyst\`,
   path shown and overridable in the UI.
