# Data Flow Contracts

**Status:** Active reference  
**Date:** 2026-06-19 (reconciled with control plane)  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../project%20rules.md)  
**Authority:** ADR-001 … ADR-004, [`SYSTEM_MAP.md`](SYSTEM_MAP.md), [`FILE_OWNERSHIP.md`](FILE_OWNERSHIP.md)

**Related rules:** Candle Data vs Camera Rule (§11) · Background sync discipline (§10) · Agent Chain (§36) · QA Gate (§50) · Commit Scope (§45) · Docs Control Plane (§38) · Python Truth Engine (§31)

---

## Subsystem map (read-only)

```text
┌─────────────┐     delta/missing      ┌──────────────┐
│  VPS/Backend│ ◄────────────────────── │ Local Candle │
│  (master)   │ ──── OHLC read API ──► │   Library    │
└──────┬──────┘                        └──────┬───────┘
       │ structural CRUD                       │ local read
       ▼                                       ▼
┌─────────────┐     derive only        ┌──────────────┐
│ map_ranges  │ ◄── refreshSavedRanges │   MapStudio  │
│ map_events  │                        │   (Chart UI) │
│ audit API   │                        └──────┬───────┘
└─────────────┘                               │
       ▲                                      │ inspectorCommit
       └──────────────────────────────────────┘
```

---

## A. Chart timeframe switch

```text
User clicks TF tab
  │
  ├─► setTimeframe(tf) + activeTimeframeRef
  ├─► cameraViewOwner ← TIMEFRAME_SWITCH (one-shot)
  ├─► loadCandles(tf, { timeframeSwitch: true, reason: 'timeframe-switch:…' })
  │     │
  │     ├─► shouldClearCandlesOnLoadStart → clear stale bars if TF changed
  │     ├─► resolveTimeframeSwitchDataLoadWindow (NOT camera viewport)
  │     ├─► loadChartCandlesLocalFirst (local read)
  │     │     └─► optional syncMissingWindowFromVps if window empty
  │     ├─► parse + race guard (requestId, activeTf)
  │     ├─► buildLoadedCandleContext → loadedCandleContext state
  │     └─► apply camera ONCE if candleLoadMayMoveCamera
  │
  ├─► NO refreshHierarchyAudit (ordinary switch)
  ├─► NO full VPS history pull
  └─► assertCandleFeedReady gates H/L/BOS until loadedCtx matches tab
```

**Must not:** refit on background delta; show previous TF candles; use viewport as load window.

---

## B. Campaign Continue

```text
User clicks Campaign Continue
  │
  ├─► computeCampaignStatus(savedStructuralRanges, year)  [derived]
  ├─► getNextMappingTask → MappingGap
  ├─► activateMappingGap(gap)
  │     └─► startGuidedChildMapping(parentRange, { coverage })
  │           ├─► buildGuidedCursorFromParent
  │           ├─► setStructureLayer / sourceTf / parent id
  │           ├─► jumpToStructuralRange(parent) → navigateStructuralChartContext
  │           └─► loadCandles(childChartTf, { structuralNavigation: true })
  │
  ├─► cameraViewOwner ← CAMPAIGN_CONTINUE or HIERARCHY_JUMP (one fit)
  ├─► wait loadedCandleContext valid for child layer TF
  └─► enable H/L/BOS shortcuts only after assertCandleFeedReady === true
```

**Must not:** write campaign state to backend; save ranges without user H/L/BOS.

**Input requirement:** `savedStructuralRanges` refreshed from VPS before computing next task.

---

## C. Hierarchy jump

```text
User selects range in Explorer (Jump / row click)
  │
  ├─► jumpToStructuralRange(range) OR selectSavedStructuralRange
  ├─► applyExplorerRowSelection / navigateStructuralChartContext
  ├─► loadCandles(chartTf, { structuralNavigation: true, reason: 'explorer-jump-fit' })
  │     ├─► local library + optional missing window
  │     ├─► applyStructuralReplayRestore (replay seed at range start)
  │     └─► loadedCandleContext stamp
  ├─► FIT_STRUCTURAL_RANGE camera (one-shot, HIERARCHY_JUMP)
  └─► NO inspectorCommit / NO backend mutation
```

Context overlays use backend range prices projected on chart (Overlay Projection Rule).

---

## D. Mapping save (H / L / BOS)

```text
User presses H, L, ↑, or ↓
  │
  ├─► assertCandleFeedReady(actionLabel)
  │     ├─► if fail: message + optional loadCandles(reloadTf) — does NOT skip load path globally
  │     └─► if pass: continue
  │
  ├─► mapping context guard (case selected, anchors valid, RH > RL, etc.)
  │
  ├─► RH+RL complete → saveStructuralRange()
  │     └─► inspectorCommit({ kind: 'structural_range' }) → POST /api/v1/map/range
  │
  ├─► BOS → saveStructuralBos(direction)
  │     └─► inspectorCommit({ kind: 'structural_event' }) → POST /api/v1/map/structural-event
  │           + backend lifecycle patch on broken range
  │
  ├─► refreshSavedRangesForCurrentCase() — VPS GET map/ranges
  ├─► refreshStructuralMapEventsForChart(tf) — VPS GET map/events
  ├─► refreshHierarchyAudit() — quiet, no camera refit
  ├─► campaign status recomputes from refreshed ranges (derived)
  │
  └─► NO loadCandles unless feed mismatch reload or explicit navigation
```

---

## E. Background sync (5-minute incremental)

**Rule:** Candle Data vs Camera Rule (§11) — sync updates **data only**; camera must not refit.

```text
SyncService timer (DEFAULT_RESYNC_INTERVAL_MS = 5 min)
  │
  ├─► for each tf in CHART_LIBRARY_TIMEFRAMES:
  │     syncIncrementalDeltaFromVps(symbol, tf, { mode: 'incremental_delta', quiet: true })
  │       ├─► VPS fetch tail (INCREMENTAL_DELTA_LIMIT bars)
  │       └─► upsertLocalCandles → candle_cache.db
  │
  ├─► if active chart TF matches synced TF:
  │     runBackgroundDeltaSync OR quiet merge in loadCandles path
  │       └─► mergeParsedCandleRows if candlesChanged
  │
  ├─► update localLibraryDebug status line
  │
  └─► NO applyCameraCommand
      NO refreshHierarchyAudit
      NO campaign panel side effects
```

Optional: `initBackgroundCandleSync()` on app boot via `syncService.ts`.

---

## Cross-cutting contracts

| Contract | Rule |
|----------|------|
| Candle vs camera | §11 — background sync never calls `applyCameraCommand` |
| Async races | Later requestId / TF wins; stale responses dropped |
| Session resume | Refresh VPS ranges before applying session range ids |
| Stale UI rehydration | May clear structural UI; target: must not permanently block candle fetch (see ADR-001 note) |
| One subsystem | See [`PILOT_BACKSTOP_CHECKLIST.md`](PILOT_BACKSTOP_CHECKLIST.md) |
| QA before commit | Golden Smoke (§48) + QA VERDICT (§50) when flows A–E touched |

---

## File index

| Flow | Primary modules |
|------|-----------------|
| A | `main.tsx` loadCandles, switchTimeframePreserveCase |
| B | `mappingCampaignManager.ts`, startGuidedChildMapping |
| C | jumpToStructuralRange, hierarchyRangeNavigation.ts |
| D | inspectorCommit.ts, assertCandleFeedReady |
| E | syncService.ts, localCandleLibrary.ts |
