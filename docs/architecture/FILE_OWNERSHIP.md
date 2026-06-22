# FX TrendMaster — File Ownership Matrix

**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../project%20rules.md) · [`PROJECT.RULES.md`](../../PROJECT.RULES.md)  
**Control plane:** [`SYSTEM_MAP.md`](SYSTEM_MAP.md) · [`DATA_FLOW_CONTRACTS.md`](DATA_FLOW_CONTRACTS.md) · [`PILOT_BACKSTOP_CHECKLIST.md`](PILOT_BACKSTOP_CHECKLIST.md)  
**Rule:** Any task touching `main.tsx` must declare subsystem section per **Main TSX Risk Rule** (§39) in [`TASK_TEMPLATE.md`](../agents/TASK_TEMPLATE.md).

**Task types:**

| Code | Meaning |
|------|---------|
| **P** | Pilot feature/fix (scoped subsystem) |
| **L** | Librarian audit/docs only |
| **S** | Sync Architect boundary work |
| **B** | Backend/VPS only |
| **R** | Recovery restore (one feature) |
| **—** | Do not edit without explicit approval |

---

## High-risk orchestration

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/main.tsx` | **Orchestration (all)** | Map Studio wiring only — delegates to modules | P, R (declared section) | Everything | **~13k lines.** Sections: imports, MapStudio state, `loadCandles`, camera, save, explorer, campaign, D3CandleMap, keyboard, boot effects. One subsystem per task. |
| `electron/electron/main.cjs` | Startup shell | Electron window, IPC registration | P (shell only) | candle cache, preload | Not mapping logic |
| `electron/electron/preload.cjs` | IPC bridge | Expose safe APIs to renderer | P (IPC only) | localResearch, candleCache | |

---

## Candle loader / library / sync

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/localCandleLibrary.ts` | Local candle library | Local-first read path, missing-window sync trigger | P, R | `syncService`, `main.tsx` loadCandles | Primary chart read API |
| `electron/src/candleLoadPolicy.ts` | Candle loader | Window padding, stale-load guards, diagnostics | P, R | `main.tsx`, `hierarchyRangeNavigation` | |
| `electron/src/candleLoadDebug.ts` | Candle loader | Debug logging helpers | P | — | |
| `electron/src/candleFeedIdentity.ts` | Candle loader / Keyboard | Feed guard before H/L/BOS | P, R | keyboard, save | Must not block load |
| `electron/src/candleBootService.ts` | Candle sync | Thin wrappers → syncService | P | `localCandleLibrary` | Overlaps syncService |
| `electron/src/syncService.ts` | Candle sync | VPS fetch, upsert, background sync | P, S | local library, main boot | |
| `electron/src/localResearchClient.ts` | Local candle library | IPC client for SQLite candles | P, S | `.cjs` DB layer | |
| `electron/electron/candleCache.cjs` | Local candle library | SQLite candle storage | P, S | syncService | |
| `electron/electron/candleCacheIpc.cjs` | Local candle library | IPC handlers | P, S | preload | |
| `electron/electron/localResearchDatabase.cjs` | Local candle library | DB schema/init | S | candle cache | |
| `electron/src/syncArchitectLoad.ts` | Candle loader | Session load guard, rehydration | P, S, R | session, main | |
| `electron/src/hierarchyRangeNavigation.ts` | Candle loader / Hierarchy | TF/window resolution for jumps | P, R | main explorer | |
| `electron/src/replayCursorSeed.ts` | Candle loader / Replay | Replay start seeding | P, R | main replay | |

---

## Viewport / chart

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/chartViewportPolicy.ts` | Viewport | Camera owner stability rules | P, R | main camera | |
| `electron/src/viewportController.ts` | Viewport | Preserve viewport on save/panel | P, R | main (partially wired) | Module vs inline overlap |
| `electron/src/viewportClamping.ts` | Viewport | Pan clamp math | P | useViewportClamping | |
| `electron/src/hooks/useViewportClamping.ts` | Viewport | Container clamp hook | P | mappingViewContext | |
| `electron/src/chartFocusMode.ts` | Overlays / Viewport | Focus Y-scale, ghost tiers | P, R | main D3CandleMap | |
| `electron/src/chartRenderPipeline.ts` | Chart rendering | Alternate draw pipeline | — | main inline D3 | **Not primary path** — report-only unless migration task |
| `electron/src/chartRenderGate.ts` | Chart rendering | 5px resize gate | P | main scheduleDraw | |
| `electron/src/chartResizeDebounce.ts` | Chart rendering | Resize debounce | P | main | |
| `electron/src/chartLayoutResizeGuard.ts` | Chart rendering | Layout resize guard | P | main | |
| `electron/src/rangeLineStyle.ts` | Overlays | Range line styles | P | chartFocusMode | |

---

## Mapping save / commit

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/inspectorCommit.ts` | Mapping save | Single durable-write funnel | P, S, B | main save paths | All structural commits |
| `electron/src/autoBosNextRangePrompt.ts` | Mapping save | Post-BOS next-range confirm | P, R | saveStructuralBos | |
| `electron/src/fingerErrorStack.ts` | Mapping save | LIFO undo stack | P | main keyboard | |
| `electron/src/hooks/useMappingDraft.ts` | Mapping save | Draft container state | P | syncService drafts | |
| `electron/src/mappingEventsPersistence.ts` | Mapping save | Events localStorage mirror | P | reactive hook | |
| `electron/src/hooks/useReactiveMappingEventsPersistence.ts` | Mapping save | Reactive events persistence | P | main | |

---

## Campaign / hierarchy / guided

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/mappingCampaignManager.ts` | Campaign | Status, next task, tiers | P, R, L | main panel mount | |
| `electron/src/mappingCampaignPanel.tsx` | Campaign | Campaign UI | P, R | main | |
| `electron/src/mappingCampaignWorkflow.ts` | Campaign | Continue helpers | P, R | | |
| `electron/src/mappingWorkflow.ts` | Campaign / Hierarchy | Gap queue computation | P, R | campaign manager | |
| `electron/src/parentChildCoverage.ts` | Campaign | Coverage math | P, L | | |
| `electron/src/guidedMappingCursor.ts` | Campaign | Guided cursor model | P, R | main, session | |
| `electron/src/childMappingPanel.tsx` | Campaign | Guided UI panel | P, R | main | |
| `electron/src/childMappingWorkflow.ts` | Campaign | Child session phases | P, R | | |
| `electron/src/hierarchyIntegrity.ts` | Hierarchy | Parent window validation | P, L | campaignFlexibility | |
| `electron/src/campaignFlexibility.ts` | Hierarchy | Boundary crossing soft validation | P | save flow | |

---

## Session / resume

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/mappingSessionPersistence.ts` | Session | Session schema R/W | P, R, S | main boot | |
| `electron/src/hooks/useMappingSessionPersistence.ts` | Session | Orchestration hook | P, R | main, autoResume | |
| `electron/src/MappingSessionResumeModal.tsx` | Session | Resume modal UI | P, R | main | |
| `electron/src/autoResumeStorage.ts` | Session | Minimal symbol/TF resume | P | useAutoResume | |
| `electron/src/hooks/useAutoResume.ts` | Session | Boot welcome/resume | P, R | session hook | |
| `electron/src/mapStudioStaleRehydration.ts` | Session / Cache | Ghost state clear | P, R | syncArchitect | |

---

## Keyboard / context / inspector

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/mapStudioKeyboard.ts` | Keyboard | Key → action map | P, R | main handlers | |
| `electron/src/mapStudioMappingContext.test.ts` | Keyboard | Context tests | L | | |
| `electron/src/inspectorPanel.tsx` | Startup shell | Inspector tabs | P | main portal | |
| `electron/src/inspectorCommit.ts` | Mapping save | (see above) | | | |
| `electron/src/inspectorContext.ts` | Hierarchy | Inspector routing hints | P | | |
| `electron/src/mappingViewContext.ts` | Campaign | Parent/child chart context | P | viewport clamp | |
| `electron/src/mappingViewContextSwitcher.tsx` | Campaign | Context switcher UI | P | main ribbon | |

---

## Shell / nav / styles

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `electron/src/appShell.tsx` | Startup shell | Nav rail, shell layout | P | main layout | |
| `electron/src/navOverlay.tsx` | Startup shell | O-N-G-M-C-T rail | P | inspector tabs | |
| `electron/src/styles.css` | Startup shell | Global CSS | P (scoped) | pilot grid, chart | Large file — subsystem-scoped edits only |
| `electron/src/appNavigation.ts` | Startup shell | Page routing | P | | |

---

## Backend (structural truth)

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `backend/main.py` | Backend API | HTTP routes | B, S | detector promotion | |
| `backend/candle_store.py` | Backend API | DB access | B, S | | |
| `backend/detector/**` | Detector (assistant) | Suggestions only | B (detector task) | Electron mapping | Not product workflow |
| `electron/src/rawMapping.ts` | Audit / raw ledger | Raw case export | P, S | backend raw routes | |

---

## Python / research (Python Truth Engine — §31)

| File | Subsystem | Owner responsibility | May edit | Dangerous with | Notes |
|------|-----------|---------------------|----------|----------------|-------|
| `python_analyst/**` | Python / statistics | Analytical truth from exports | P (research) | backend structural writes | **Must not** silently mutate `map_ranges` / `map_events` |
| `processor/**` | Python / statistics | Compile from raw ledger exports | P (research) | Electron mapping | Read-only vs VPS unless approved |
| `electron/src/localPythonRunner.ts` | Python / statistics | Bundled runner | P | electron build | |
| `electron/src/localResearchWorkflow.ts` | Python / statistics | Local research UI flow | P | | User-selected DB copy only |

---

## Tests (co-located)

| Pattern | Owner | May edit |
|---------|-------|----------|
| `electron/src/**/*.test.ts` | Matching subsystem | P, L, R |
| `backend/tests/**` | Backend | B, L |

---

## `main.tsx` section map (for task declarations)

| Approx region | Subsystem | Key symbols |
|---------------|-----------|-------------|
| Imports | — | keep minimal |
| MapStudio state | Mixed | hooks, localStorage |
| `loadCandles` | Candle loader | requestId, library load |
| Camera / `applyCameraCommand` | Viewport | cameraViewOwner |
| `saveStructuralRange/Bos` | Mapping save | inspectorCommit |
| Explorer / hierarchy | Hierarchy | applyExplorerRowSelection |
| Campaign / guided | Campaign | handleCampaignContinue, startGuidedChildMapping |
| Session hooks | Session | useMappingSessionPersistence |
| `D3CandleMap` | Chart + Viewport | draw, camera effects |
| Keyboard listeners | Keyboard | onSkeletonKeyDown |
| Boot `useEffect`s | Candle loader + Session | TF/case bootstrap |

---

*Expand this matrix when new owner files are added. Do not edit ownership rows without updating SYSTEM_MAP.md.*
