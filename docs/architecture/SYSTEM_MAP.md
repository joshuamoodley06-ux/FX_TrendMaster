# FX TrendMaster — System Map

**Canonical doctrine:** `PROJECT.RULES.md`  
**Filesystem path:** [`project rules.md`](../../project%20rules.md) · pointer: [`PROJECT.RULES.md`](../../PROJECT.RULES.md)  
**Also:** [`.cursorrules`](../../.cursorrules) (raw ledger / mapping layer)  
**Purpose:** Subsystem layout for Pilot/Cursor containment — one task, one subsystem.  
**Baseline reference (audit):** `59db083` — *Stabilize chart viewport so Fit All and manual zoom survive async reloads.*

> **Filename note:** Doctrine canonical name is `PROJECT.RULES.md`; content lives in `project rules.md`. Do not rename without Josh approval.

---

## How to use this map

Before editing code, identify **one subsystem** from the list below. Read its **allowed/forbidden** boundaries and **fragile areas**. Cross-subsystem work requires Josh approval.

Use with: [`FILE_OWNERSHIP.md`](FILE_OWNERSHIP.md) · [`DATA_FLOW_CONTRACTS.md`](DATA_FLOW_CONTRACTS.md) · [`PILOT_BACKSTOP_CHECKLIST.md`](PILOT_BACKSTOP_CHECKLIST.md) · [`../agents/TASK_TEMPLATE.md`](../agents/TASK_TEMPLATE.md) · [`../testing/GOLDEN_SMOKE.md`](../testing/GOLDEN_SMOKE.md)

---

## PROJECT.RULES crosswalk (control plane)

| Rule (§ in `project rules.md`) | Where enforced in docs/code |
|--------------------------------|----------------------------|
| **Agent Chain Rule** (§36) | Librarian → Sync Architect → Pilot → QA → Josh; see [`TASK_TEMPLATE.md`](../agents/TASK_TEMPLATE.md) |
| **QA Gate Rule** (§50) | [`GOLDEN_SMOKE.md`](../testing/GOLDEN_SMOKE.md); QA verdict required before production commit |
| **Docs Control Plane Rule** (§38) | This file + listed control-plane docs |
| **Main TSX Risk Rule** (§39) | [`FILE_OWNERSHIP.md`](FILE_OWNERSHIP.md) · `main.tsx` section map |
| **Commit Scope Rule** (§45) | [`PILOT_BACKSTOP_CHECKLIST.md`](PILOT_BACKSTOP_CHECKLIST.md) · docs-only vs production separation |
| **Golden Smoke Rule** (§48) | [`GOLDEN_SMOKE.md`](../testing/GOLDEN_SMOKE.md) |
| **Candle Data vs Camera Rule** (§11) | [`ADR-002`](ADR/ADR-002-viewport-owner-model.md) · background sync in §4 Candle sync below |
| **Background sync discipline** (§10 Incremental + §11) | §4 Candle sync — delta only; no viewport refit; no structural writes |
| **Python Truth Engine Rule** (§31) | §14 Python / statistics — analytical truth only; no silent `map_*` mutation |
| **Canonical filename rule** (header) | [`PROJECT.RULES.md`](../../PROJECT.RULES.md) pointer |

---

## 1. Chart rendering

| Field | Detail |
|-------|--------|
| **Purpose** | Draw candles, overlays, guided lines, crosshair, trade ideas, drawings. Support mapping — not replace it. |
| **Owning files** | `electron/src/main.tsx` (`D3CandleMap`, `scheduleDraw`, inline D3) · `electron/src/chartRenderPipeline.ts` (module; **not** primary render path) · `electron/src/chartFocusMode.ts` · `electron/src/rangeLineStyle.ts` · `electron/src/chartDrawings.ts` · `electron/src/chartTradeIdeas.ts` · `electron/src/chartRenderGate.ts` · `electron/src/chartResizeDebounce.ts` · `electron/src/chartLayoutResizeGuard.ts` |
| **Main symbols** | `D3CandleMap`, `scheduleDraw`, `draw()`, `focusVisualStyle`, `savedRangeLineStyle`, `createChartRenderGate` |
| **Allowed** | SVG/canvas draw, overlay opacity tiers, resize debounce, render gate (>5px), empty-state display |
| **Forbidden** | Derive structural truth; save ranges/events; call VPS structural APIs; auto-detect BOS without user action |
| **Fragile areas** | Inline D3 in `main.tsx` (~10k+ lines); duplicate overlay logic vs `chartRenderPipeline.ts`; autoscale vs `cameraViewOwner` interaction |
| **Tests** | `chartRenderPipeline.test.ts`, `chartFocusMode.test.ts`, `chartRenderGate.test.ts`, `chartLayoutResizeGuard.test.ts`, `chartResizeDebounce.test.ts`, `rangeLineStyle.test.ts` |
| **Smoke** | **Electron required** — Fit All/Range stability, overlay anchoring, focus mode ghosts, guided cursor lines |

---

## 2. Candle loader

| Field | Detail |
|-------|--------|
| **Purpose** | Load requested TF candles local-first; windowed structural loads; stale-load race guards; truthful empty states. |
| **Owning files** | `electron/src/main.tsx` (`loadCandles`) · `electron/src/localCandleLibrary.ts` · `electron/src/candleLoadPolicy.ts` · `electron/src/candleLoadDebug.ts` · `electron/src/candleFeedIdentity.ts` · `electron/src/hierarchyRangeNavigation.ts` · `electron/src/replayCursorSeed.ts` · `electron/src/syncArchitectLoad.ts` |
| **Main symbols** | `loadCandles`, `loadChartCandlesLocalFirst`, `shouldAcceptCandleLoadResult`, `resolveStructuralDataLoadWindow`, `evaluateCandleFeedGuard`, `candleLoadSeqRef` |
| **Allowed** | Local read → VPS missing-window/delta; request-id matching; clear stale candles on TF mismatch; diagnostic logging |
| **Forbidden** | Block `loadCandles()` because mapping guard failed; show wrong-TF candles; mask missing M15 with H1/D1 fallback; use viewport as default data window |
| **Fragile areas** | `loadCandles` orchestration in `main.tsx`; quiet vs structural vs TF-switch paths; `liveTail` flag; replay hydrate race |
| **Tests** | `localCandleLibrary.test.ts`, `candleLoadPolicy.test.ts`, `candleFeedIdentity.test.ts`, `hierarchyRangeNavigation.test.ts`, `replayCursorSeed.test.ts`, `syncArchitectLoad.test.ts` |
| **Smoke** | **Electron required** — W1/D1/H4/H1/M15 loads, H1↔H4↔H1, D1→M15, truthful missing-data message |

---

## 3. Local candle library

| Field | Detail |
|-------|--------|
| **Purpose** | Primary chart candle performance layer (SQLite via Electron IPC). |
| **Owning files** | `electron/src/localCandleLibrary.ts` · `electron/src/localResearchClient.ts` · `electron/electron/localResearchDatabase.cjs` · `electron/electron/candleCache.cjs` · `electron/electron/candleCacheIpc.cjs` |
| **Main symbols** | `loadChartCandlesLocalFirst`, `fetchLocalCandles`, `upsertLocalCandles`, `getLocalCandlesStatus`, `readLocalLibraryDebugStatus` |
| **Allowed** | OHLC upsert by `symbol+timeframe+time`; sync metadata; window-filtered reads |
| **Forbidden** | Store ranges, events, hierarchy, campaign truth, audit truth |
| **Fragile areas** | IPC bridge main/preload; schema migrations in `localResearchDatabase.cjs` |
| **Tests** | `localCandleLibrary.test.ts`, `localResearchIpc.test.ts` |
| **Smoke** | **Electron required** — local count visible in UI; library path/status line |

---

## 4. Candle sync

| Field | Detail |
|-------|--------|
| **Purpose** | Incremental VPS delta sync (~5 min); bootstrap missing windows; background symbol sync. |
| **Owning files** | `electron/src/syncService.ts` · `electron/src/candleBootService.ts` · `electron/src/hooks/useCockpitSync.ts` · `electron/electron/candleCache.cjs` |
| **Main symbols** | `syncIncrementalDeltaFromVps`, `syncMissingWindowFromVps`, `syncSymbolFromVps`, `syncTimeframeFromVps`, `initBackgroundCandleSync`, `CHART_LIBRARY_TIMEFRAMES` |
| **Allowed** | Fetch deltas (~5 min interval); upsert local library; update forming/latest bar; warm-boot reads from session |
| **Forbidden** | Full-history VPS pull on every TF switch; structural writes; **viewport refit**; mapping saves; wrong-TF display (see **Candle Data vs Camera Rule** §11) |
| **Fragile areas** | Overlap with `candleBootService` wrappers; background sync during structural navigation (`skipVpsSync`) |
| **Tests** | `syncService.test.ts`, `hooks/useCockpitSync.test.ts` |
| **Smoke** | **Electron required** — incremental sync after window gap; no lag on hierarchy jump |

---

## 5. Viewport ownership

| Field | Detail |
|-------|--------|
| **Purpose** | Camera/fit stability — manual fits survive async reloads, audit refresh, overlay updates. |
| **Owning files** | `electron/src/chartViewportPolicy.ts` · `electron/src/viewportController.ts` · `electron/src/viewportClamping.ts` · `electron/src/hooks/useViewportClamping.ts` · `electron/src/main.tsx` (`applyCameraCommand`, `cameraViewOwner`, `D3CandleMap` camera effects) |
| **Main symbols** | `CameraViewOwner`, `shouldBlockAutomaticCameraRefit`, `shouldPreserveViewport`, `EXPLICIT_VIEWPORT_MOVE_REASONS`, `clampChartTransformToTimeBounds` |
| **Allowed** | Explicit fit reasons; defer/suppress auto-refit when user owns view; container clamp for parent/child mapping |
| **Forbidden** | Silent refit after Fit All; audit refresh moving camera; replay auto-pan without permission |
| **Fragile areas** | **Three policy modules** + inline camera in `main.tsx`/`D3CandleMap`; `deferredCameraRef`; fullscreen layout effect |
| **Tests** | `chartViewportPolicy.test.ts`, `viewportController.test.ts`, `viewportClamping.test.ts` |
| **Smoke** | **Electron required** — Fit All + Fit Range stable 10s; manual zoom not reset by reload |

---

## 6. Keyboard mapping

| Field | Detail |
|-------|--------|
| **Purpose** | Candle-first mapping shortcuts: H/L, BOS arrows, replay, undo, escape. |
| **Owning files** | `electron/src/mapStudioKeyboard.ts` · `electron/src/main.tsx` (`onSkeletonKeyDown`, legacy `onKeyDown`) · `electron/src/candleFeedIdentity.ts` (guard before mark) |
| **Main symbols** | `resolveMapStudioKeyAction`, `isTypingInEditableField`, `evaluateCandleFeedGuard` |
| **Allowed** | Key → action dispatch; block when feed mismatch/loading; block in editable fields |
| **Forbidden** | Save on wrong TF; bypass `inspectorCommit` funnel |
| **Fragile areas** | Two keydown listeners in `main.tsx`; skeleton vs legacy mapping paths |
| **Tests** | `mapStudioKeyboard.test.ts`, `candleFeedIdentity.test.ts` |
| **Smoke** | **Electron required** — H/L/BOS only with valid feed; replay arrows |

---

## 7. Mapping save / checkpoint logic

| Field | Detail |
|-------|--------|
| **Purpose** | Persist structural ranges, BOS events, chain links to VPS/backend; auto-checkpoints when RH+RL/BOS complete. |
| **Owning files** | `electron/src/main.tsx` (`saveStructuralRange`, `saveStructuralBos`, `saveNextStructuralRange`) · `electron/src/inspectorCommit.ts` · `electron/src/structuralRangeLifecycle.ts` (if present) · `electron/src/autoBosNextRangePrompt.ts` · `electron/src/fingerErrorStack.ts` · `electron/src/hooks/useMappingDraft.ts` |
| **Main symbols** | `inspectorCommit`, `inspectorCommitOrThrow`, `saveStructuralRange`, `saveStructuralBos`, `resolveParentRangeIdForSave` |
| **Allowed** | Route all durable writes through `inspectorCommit`; local draft until checkpoint; LIFO undo for draft points |
| **Forbidden** | Direct fetch to structural API bypassing commit funnel; silent delete of backend truth |
| **Fragile areas** | Chain save / BOS lifecycle patch ordering; parent resolve auto-selection; duplicate range detection |
| **Tests** | `inspectorCommit.test.ts`, `structuralRangeLifecycle.test.ts`, `autoBosNextRangePrompt.test.ts`, `fingerErrorStack.test.ts`, `hooks/useMappingDraft.test.ts` |
| **Smoke** | **Electron required** — H/L checkpoint, BOS ↑/↓, Save Next / chain after BOS |

---

## 8. Campaign Manager

| Field | Detail |
|-------|--------|
| **Purpose** | Orchestrate Weekly→Daily→Intraday→Micro campaign; tier progress; **Continue** to next coverage gap. |
| **Owning files** | `electron/src/mappingCampaignManager.ts` · `electron/src/mappingCampaignPanel.tsx` · `electron/src/mappingCampaignWorkflow.ts` · `electron/src/mappingWorkflow.ts` · `electron/src/parentChildCoverage.ts` · `electron/src/guidedMappingCursor.ts` · `electron/src/main.tsx` (`campaignStatus`, `handleCampaignContinue`, gap queue) |
| **Main symbols** | `computeCampaignStatus`, `getNextMappingTask`, `computeMappingGaps`, `startGuidedChildMapping`, `MappingCampaignPanel` |
| **Allowed** | Derive status from saved backend ranges; start guided mapping on Continue; year filter scope |
| **Forbidden** | Store campaign truth locally; auto-save structure without user marks; detector-driven layer switches |
| **Fragile areas** | HTF vs LTF explorer mode vs unified campaign priority; gap queue duplicate of Continue |
| **Tests** | `mappingCampaignManager.test.ts`, `mappingCampaignWorkflow.test.ts`, `parentChildCoverage.test.ts`, `guidedMappingCursor.test.ts` |
| **Smoke** | **Electron required** — Campaign Continue, tier badges, guided cursor boot |

---

## 9. Hierarchy navigation

| Field | Detail |
|-------|--------|
| **Purpose** | Market Memory Navigator tree, gap queue, drill-down, coordinated TF/window/camera on row click. |
| **Owning files** | `electron/src/main.tsx` (explorer panel, `applyExplorerRowSelection`, `jumpToStructuralRange`) · `electron/src/hierarchyRangeNavigation.ts` · `electron/src/mappingWorkflow.ts` · `electron/src/hierarchyIntegrity.ts` · `electron/src/campaignFlexibility.ts` |
| **Main symbols** | `buildCaseHierarchyForest`, `applyExplorerRowSelection`, `resolveRangeChartTimeframe`, `drillToChildMapping`, `activateMappingGap` |
| **Allowed** | Navigate layers/TFs; jump camera; select parent context; reparent via explicit commit |
| **Forbidden** | Infer hierarchy without backend ranges; hard-delete without audit |
| **Fragile areas** | Cross-layer selection vs `structureLayer` sync; path-only filters; navigation + candle load ordering |
| **Tests** | `hierarchyRangeNavigation.test.ts`, `hierarchyIntegrity.test.ts`, `campaignFlexibility.test.ts` |
| **Smoke** | **Electron required** — hierarchy row jump, cross-layer TF switch, parent lines |

---

## 10. Session persistence

| Field | Detail |
|-------|--------|
| **Purpose** | Resume mapping session (layer, range IDs, guided cursor, explorer year) across reloads. |
| **Owning files** | `electron/src/mappingSessionPersistence.ts` · `electron/src/hooks/useMappingSessionPersistence.ts` · `electron/src/MappingSessionResumeModal.tsx` · `electron/src/autoResumeStorage.ts` · `electron/src/hooks/useAutoResume.ts` · `electron/src/main.tsx` (orchestration gates) |
| **Main symbols** | `saveMappingSession`, `loadMappingSession`, `buildMappingSessionState`, `useMappingSessionPersistence`, `MappingSessionOrchestration` |
| **Allowed** | localStorage session snapshot; gated resume (idle→pending_modal→resuming); defer auto-resume when session exists |
| **Forbidden** | Session owning structural truth; resume overwriting backend ranges |
| **Fragile areas** | Boot effect race with `loadCandles`; modal vs auto-resume; explorer year apply order |
| **Tests** | `mappingSessionPersistence.test.ts`, `hooks/useMappingSessionPersistence.test.ts`, `autoResumeStorage.test.ts` |
| **Smoke** | **Electron required** — reload restore, non-blocking resume card |

---

## 11. Parent context overlays

| Field | Detail |
|-------|--------|
| **Purpose** | Project parent RH/RL onto lower-TF charts; mini-bar; focus-mode tier ghosts. |
| **Owning files** | `electron/src/main.tsx` (`activeParentRangeOverlay`, `chartSavedRangeOverlays`) · `electron/src/chartFocusMode.ts` · `electron/src/rangeLineStyle.ts` · `D3CandleMap` parent overlay draw path |
| **Main symbols** | `activeParentRangeOverlay`, `parentOverlays` prop, `focusOverlayRows`, `focusYExtentsWithParent` |
| **Allowed** | Price-aligned horizontal lines; tier opacity; union parent extents into Y domain |
| **Forbidden** | Separate overlay Y-scale; wrong-parent prices |
| **Fragile areas** | `parentOverlays={}` regression history; saved vs parent vs draft overlay precedence |
| **Tests** | `chartFocusMode.test.ts`, `rangeLineStyle.test.ts` |
| **Smoke** | **Electron required** — Weekly lines on Daily/H1/M15; focus mode ghosts |

---

## 12. Audit / export

| Field | Detail |
|-------|--------|
| **Purpose** | Hierarchy audit, case audit JSON, mapping export, raw case export — read backend truth. |
| **Owning files** | `electron/src/main.tsx` (`refreshHierarchyAudit`, `exportAuditJson`, `exportCurrentMappingJson`) · `electron/src/rawMapping.ts` · `electron/src/reviewCandidateClient.ts` · Backend: `/api/v1/map/hierarchy-audit`, raw-mapping export routes |
| **Main symbols** | `refreshHierarchyAudit`, `exportRawCaseEvents`, `downloadJsonFile` |
| **Allowed** | Read-only audit display; JSON download; detector review panel |
| **Forbidden** | Audit-derived structural writes; camera refit on audit refresh |
| **Fragile areas** | Audit refresh triggering navigation side effects |
| **Tests** | `inspectorCommit.test.ts` (indirect); backend tests for audit API |
| **Smoke** | **Electron required** — audit refresh, export JSON |

---

## 13. Backend API / VPS truth

| Field | Detail |
|-------|--------|
| **Purpose** | Durable structural evidence locker + candle master source on VPS. |
| **Owning files** | `backend/main.py` · `backend/candle_store.py` · `backend/detection_brain_*` (assistant only) · `electron/src/vpsConfig.ts` · `electron/src/inspectorCommit.ts` |
| **Key routes** | `/api/v1/candles` · `/api/v1/map/range(s)` · `/api/v1/map/structural-event(s)` · `/api/v1/map/hierarchy-audit` · `/api/v1/raw-mapping/*` |
| **Allowed** | Validate, store, export, hash raw events; structural range CRUD with hierarchy fields |
| **Forbidden** | Frontend-derived range logic in backend; detector auto-promote without explicit path |
| **Fragile areas** | DB split (`market_memory.db` vs `raw_mapping_v159.db` per `.cursorrules`) |
| **Tests** | `backend/tests/*` |
| **Smoke** | VPS reachable; case load; range save round-trip |

---

## 14. Python / statistics future boundary

| Field | Detail |
|-------|--------|
| **Purpose** | **Python Truth Engine** — derive analytical truth from backend/raw exports; **only layer allowed to think** beyond UI orchestration. |
| **Owning files** | `python_analyst/` · `processor/` (if present) · `electron/src/localPythonRunner.ts` · `electron/electron/localPythonRunner.cjs` |
| **Allowed** | Read exports; build `clean_*` analytical tables, stats, Parquet/JSON exports; local research workflows |
| **Forbidden** | Silently rewrite `map_ranges` / `map_events` / hierarchy / raw ledger; ML/signals unless explicitly requested; corrections without explicit audit mode |
| **Fragile areas** | Bundled runner in Electron asar unpack |
| **Tests** | `localPythonRunner.test.ts`, `localResearchWorkflow.test.ts`, `python_analyst` pytest |
| **Smoke** | Optional — local research panel runs |

---

## 15. Startup shell / navigation

| Field | Detail |
|-------|--------|
| **Purpose** | App shell, nav rail, inspector tabs, page routing — not mapping brain. |
| **Owning files** | `electron/src/appShell.tsx` · `electron/src/navOverlay.tsx` · `electron/src/inspectorPanel.tsx` · `electron/src/appNavigation.ts` · `electron/src/main.tsx` (`App`) |
| **Allowed** | Layout, tab routing, persistent nav chrome |
| **Forbidden** | Structural inference in shell |
| **Tests** | `AppShell.test.ts`, `inspectorPanel.test.ts`, `appNavigation.test.ts` |
| **Smoke** | Electron — app starts, pilot case opens, Campaign tab reachable |

---

## Subsystem dependency graph (read-only)

```text
Backend VPS (truth)
    ↑ inspectorCommit
Mapping Save ← Keyboard ← Candle Feed Guard ← Candle Loader ← Local Library ← Candle Sync
    ↑
Campaign / Hierarchy / Session (orchestration in main.tsx)
    ↓
Chart Rendering + Viewport + Overlays
```

---

*Update this map when a subsystem gains a new owner file or a fragile area is resolved.*
