# ADR-001: Local Candle Library

**Status:** Accepted (target architecture — partially implemented)  
**Date:** 2026-06-19  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../../project%20rules.md)  
**Authority:** Local Candle Library Rule, Incremental Candle Sync Rule, Candle Loading Must Not Be Guarded Away (§10–§11)

**See also:** [`SYSTEM_MAP.md`](../SYSTEM_MAP.md) · [`DATA_FLOW_CONTRACTS.md`](../DATA_FLOW_CONTRACTS.md) flows A, E

---

## Context

FX TrendMaster chart performance depends on reading OHLC from a local SQLite library (`Documents/FXTM_Research/candle_cache.db` via `electron/electron/candleCache.cjs`) while VPS/backend remains the **master candle source** and **structural truth**.

This ADR is derived from `project rules.md` and current Electron modules (`localCandleLibrary.ts`, `syncService.ts`, `loadCandles` in `main.tsx`).

---

## Decision

### Roles

| Layer | Role |
|-------|------|
| **Backend / VPS** | Master OHLC store; MT5 sync target; authoritative `map_ranges` / `map_events` / audit |
| **Local candle library** | Primary **chart** read path; incremental upsert target |
| **Chart (MapStudio)** | Reads **local first**; never assumes VPS on every interaction |

### Supported chart timeframes

```text
M15, H1, H4, D1, W1
MN1 — later if needed (MACRO layer; not in CHART_LIBRARY_TIMEFRAMES yet)
M1  — explicitly out of scope unless Josh requests
```

Implementation constant: `CHART_LIBRARY_TIMEFRAMES` in `syncService.ts`.

### Sync modes

| Mode | Limit (current) | When |
|------|-----------------|------|
| **Initial bootstrap** | `INITIAL_BOOTSTRAP_LIMIT` (500 bars) | First empty local library for symbol/TF |
| **Missing window** | VPS fetch for `start`/`end` only | Local empty for requested structural/chart window |
| **Incremental delta** | `INCREMENTAL_DELTA_LIMIT` (24 bars) | Background timer + post-load refresh |
| **Interval** | Every `DEFAULT_RESYNC_INTERVAL_MS` (5 min) | Active symbol × all library TFs |

VPS must **not** receive full-history pulls on ordinary timeframe switch or 5-minute tick.

### Local library schema (allowed)

```text
candles (symbol, timeframe, time, OHLCV, source, updated_at)
candle_sync_state (last_time, bar_count, last_sync_at, last_mode, last_error)
```

### Local library must never own

```text
map_ranges / map_events
hierarchy / parent_range_id truth
campaign completion state
audit verdicts
mapping drafts as durable truth
```

**Known violation (document, do not expand):** `mapping_ranges` table in `candle_cache.db` used for stale UI rehydration checks. Structural truth must not be written there. See recovery architecture reports.

---

## Allowed flows

### 1. First bootstrap

```text
App boot / empty local TF
  → optional VPS bootstrap (limited bar count, not full history unless explicit)
  → upsert local candles + sync_state
  → loadChartCandlesLocalFirst → chart render
```

Entry: `syncMissingWindowFromVps` / warm boot paths in `syncService.ts`.

### 2. Timeframe switch

```text
User selects TF tab
  → discard stale async loads (requestId + activeTf guard)
  → clear stale candles if TF changed (shouldClearCandlesOnLoadStart)
  → loadChartCandlesLocalFirst (local read, window from TF-aware policy — NOT camera viewport)
  → optional missing-window VPS sync only if local window empty
  → set loadedCandleContext
  → at most ONE timeframe-switch camera fit (TIMEFRAME_SWITCH owner)
```

**Forbidden:** full VPS history fetch on every TF switch.

### 3. Missing window

```text
Structural/campaign context requires [start, end]
  → read local for window
  → if empty: syncMissingWindowFromVps(start, end) only
  → re-read local
  → if still empty: empty chart + diagnostic message
```

Entry: `loadChartCandlesLocalFirst` when `window` set and local empty.

### 4. Incremental delta

```text
Background 5m timer OR runBackgroundDeltaSync after chart load
  → syncIncrementalDeltaFromVps (small limit)
  → upsert local
  → if current TF affected: merge into chart state quietly
  → NO camera refit
```

### 5. Latest / forming candle update

```text
Every 5 minutes (active symbol, library TFs)
  → fetch tail delta from VPS
  → upsert same timestamp (update H/L/C/V)
  → chart merge if on affected TF
```

Forming-candle semantics (`is_closed`) are **target** per `project rules.md`; schema support may be incremental.

### 6. Local empty state

```text
Local read returns 0 bars
  → show: "No {TF} candles available for this window. Sync/import required."
  → block H/L/BOS (feed guard) — NOT block load attempts
  → do NOT show previous TF candles under new tab
```

### 7. VPS unavailable state

```text
Local has data
  → chart works offline from library
Local empty + VPS fail
  → empty diagnostic, user may retry Reload / Sync MT5
  → mapping blocked until feed valid
```

---

## Forbidden flows

| Flow | Why |
|------|-----|
| Chart pulls **full VPS history** on every TF switch | Violates Local Candle Library Rule |
| **Stale TF candles** remain visible after failed switch | Violates No Wrong-Candle Display Rule |
| Local cache **owns** ranges/events/hierarchy | Violates Source Of Truth Rule |
| **Feed guard** blocks `loadCandles()` | Violates Candle Loading Must Not Be Guarded Away |
| **5-minute timer** pulls full history | Violates Incremental Candle Sync Rule |
| Use **camera viewport** as default data window on TF switch | Violates Timeframe Switch Load Window Rule |
| Quiet full-history reload during active structural mapping | Blocked by `shouldBlockQuietFullHistoryReload` |

### Boundary note: rehydration vs feed guard

`validateRangeRehydration` may set `should_clear_ui` and return **zero candles** before local read. This is **UI stale-context protection**, not the mapping feed guard. **Target state:** rehydration must not block candle **fetch** permanently; it may clear structural UI overlays only. Pilot/Sync Architect should converge this with ADR-003.

---

## Implementation map

| Concern | Module |
|---------|--------|
| Local-first load | `electron/src/localCandleLibrary.ts` → `loadChartCandlesLocalFirst` |
| VPS delta / missing window | `electron/src/syncService.ts` |
| Chart orchestration | `electron/src/main.tsx` → `loadCandles` |
| SQLite IPC | `electron/electron/candleCache.cjs`, `candleCacheIpc.cjs` |
| Background 5m sync | `SyncService.startResyncTimer` |

---

## Consequences

- Pilot candle patches must touch **Cache** or **Chart** subsystem only — not save logic or detector.
- Candle bugs require **availability audit** (local count, VPS count, window) before UI changes.
- MN1/M1 require explicit ADR amendment before inclusion.
