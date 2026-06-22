# FX TrendMaster Feature Restore Log

Restoration follows `docs/recovery/RECOVERY_AUDIT.md` one feature at a time. No new architecture.

---

## 1. Session Persistence

| Field | Detail |
|-------|--------|
| **Feature restored** | Session Persistence — auto-save mapping session to localStorage; resume modal on boot |
| **Files changed** | `electron/src/hooks/useMappingSessionPersistence.ts` (new), `electron/src/hooks/useMappingSessionPersistence.test.ts` (new), `electron/src/main.tsx`, `electron/src/styles.css` |
| **Tests run** | `npm test` (electron vitest): **223 passed** — includes `mappingSessionPersistence.test.ts` and `useMappingSessionPersistence.test.ts` |
| **Manual smoke result** | Re-test required after orchestration patch (see Session Persistence patch 2 below) |
| **Commit hash** | `b02809d` (initial restore); patch 2 `ed6188c` + Map Studio wiring in `f10d215` |
| **Remaining missing features** | Viewport Stabilization, Focus Mode, Guided Mapping Cursor, Campaign Manager, Auto BOS Save |

### Session Persistence patch 2 (smoke failure fix)

**Root cause:** Resume applied scope/timeframe before backend ranges refreshed; boot `useEffect`s on `[timeframe]` fired full candle bootstrap (refresh ranges + sync all TFs + multiple `loadCandles`) in parallel with resume. Auto-save while modal pending could overwrite stored session. Auto-resume warm boot raced modal. Explorer year applied too early then overwritten by boot effects.

**Fix:** Gated orchestration (`idle` → `pending_modal` → `resuming`), defer auto-resume when stored mapping session exists, block boot effects during modal/resume, ordered resume: scope (no TF) → refresh ranges → validate IDs → select range → set TF → single `loadCandles` → events → explorer year last.

**Files:** `electron/src/hooks/useMappingSessionPersistence.ts`, `electron/src/hooks/useMappingSessionPersistence.test.ts`, `electron/src/hooks/useAutoResume.ts`, `electron/src/main.tsx`

**Tests:** `npm test` → 226 passed

---

## 2. Viewport Stabilization (hierarchy range jump patch)

| Field | Detail |
|-------|--------|
| **Feature restored** | Coordinated hierarchy range navigation — layer/TF/window/overlays/camera on explorer click |
| **Root cause** | `applyExplorerRowSelection` only called `selectSavedStructuralRange` when `rangeLayer === structureLayer`; cross-layer clicks set anchors without switching structural layer, source TF, or windowed candle load. `jumpToStructuralRange` switched chart TF via boot bootstrap (`cacheFullHistory: true`) without explicit window. `resolveCandleLoadWindow` used parent daily range for intraday loads via `resolveMappingContextRange`. Active range bypassed hide toggle in `chartSavedRangeOverlays`. `rangeSpanX` allowed RH/RL lines to collapse below readable width when zoomed out. |
| **Files changed** | `electron/src/main.tsx`, `electron/src/hierarchyRangeNavigation.ts` (new), `electron/src/hierarchyRangeNavigation.test.ts` (new) |
| **Tests run** | `npm test` (electron vitest): **232 passed** |
| **Manual smoke result** | Passed (Josh) |
| **Commit hash** | `f10d215` |
| **Remaining missing features** | Focus Mode, Guided Mapping Cursor, Campaign Manager, Auto BOS Save |

---

## 3. Focus Mode

| Field | Detail |
|-------|--------|
| **Feature restored** | Chart Focus Mode — candle-first Y-scale, tiered overlay ghosts, parent RH/RL on chart |
| **Root cause** | `chartFocusMode.ts` existed but was never wired; `chartFocusMode` body class was fullscreen layout only; `parentOverlays={[]}` dropped parent lines |
| **Files changed** | `electron/src/chartFocusMode.ts`, `electron/src/chartFocusMode.test.ts`, `electron/src/main.tsx` |
| **Tests run** | `npm test` (electron vitest): **234 passed** |
| **Manual smoke result** | Re-test required — INTRADAY/MICRO auto-focus, ghost ancestors, parent lines, Focus toggle |
| **Commit hash** | `355d17f` |
| **Remaining missing features** | Guided Mapping Cursor, Campaign Manager, Auto BOS Save |

### Viewport patch 2 (candle-load stability)

**Root cause:** Boot effect always used `cacheFullHistory: true` and re-ran on every case change; `resolveCandleLoadWindow` skipped W1/D1 windows; TF switch relied on boot without explicit windowed load; stale-load guard only checked request id + TF (not symbol/case); suspicious 1-bar window loads replaced full series; `contextMiss` forced `LATEST` camera jump.

**Fix:** `candleLoadPolicy.ts` guards; windowed loads for all structural contexts; unified TF switch + explicit `loadCandles`; boot seq coalescing without case-id retrigger; preserve candles until valid replacement; fit range on context miss when active range exists.

**Tests:** `npm test` → **239 passed**

### Viewport patch 2 round 4 (smoke passed)

**Root cause:** Stale React state — TF chip read empty `activeStructuralRangeId` right after range select and fell back to legacy path with `cacheFullHistory: true`. Local cache/VPS returned unfiltered bars even when `loadWindow` was set. `liveTail` still extended structural loads when context was missed. VPS sync ran on every structural navigation (H4 lag). Play Forward blocked because replay defaulted to last bar and stale localStorage cursor rehydrated to ~2026 end.

**Fix:** `activeStructuralRangeIdRef` / `selectedParentRangeIdRef`; `resolveStructuralDataLoadWindow()` separate from camera fit; `filterCandlesToLoadWindow()` + `maxBarsForStructuralWindow()`; `skipVpsSync` for windowed structural loads; unified TF switch with `structuralNavigation: true`; replay seeded at range start with `skipSavedReplayHydrateRef`; expanded `CandleLoadDiagnostics`.

**Files:** `electron/src/candleLoadPolicy.ts` (new), `electron/src/candleLoadPolicy.test.ts` (new), `electron/src/main.tsx`, `electron/src/hierarchyRangeNavigation.ts`, `electron/src/hierarchyRangeNavigation.test.ts`, `electron/src/syncArchitectLoad.ts`

**Tests:** `npm test` (electron vitest): **247 passed**

**Manual smoke result:** Passed (Josh) — H1 structural TF switch, Micro/M15 no incorrect jump, windowed loading, full-history reload resolved, Play Forward after saved range, replay cursor near range start, chart focus usable

**Commit hash:** `d076413`

**Remaining missing features:** Campaign Manager, Auto BOS Save

---

## 4. Guided Mapping Cursor

| Field | Detail |
|-------|--------|
| **Feature restored** | Guided hierarchy mapping cursor — gap queue boots sequential child walk with cursor line, ChildMappingPanel, session persistence |
| **Root cause** | Full cursor model existed in `guidedMappingCursor.ts` and `childMappingPanel.tsx` but was never wired in `main.tsx`; gap queue only drilled layer/TF without cursor bootstrap |
| **Files changed** | `electron/src/main.tsx`, `electron/src/hooks/useMappingSessionPersistence.ts`, `electron/src/styles.css`, `docs/recovery/RESTORE_LOG.md` |
| **Tests run** | `npm test` (electron vitest): **247 passed** |
| **Manual smoke result** | Re-test required — gap queue click, cursor vlines, ChildMappingPanel scan/save/advance, session resume |
| **Commit hash** | *(pending commit)* |
| **Remaining missing features** | Campaign Manager, Auto BOS Save |

