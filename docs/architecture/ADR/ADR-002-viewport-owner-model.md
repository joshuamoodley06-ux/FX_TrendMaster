# ADR-002: Viewport Owner Model

**Status:** Accepted (implemented in `chartViewportPolicy.ts`; stabilization restore in progress)  
**Date:** 2026-06-19  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../../project%20rules.md)  
**Authority:** Viewport Ownership Rule, Timeframe Switching Rule, Candle Data vs Camera Rule (§11)

**See also:** [`SYSTEM_MAP.md`](../SYSTEM_MAP.md) · [`DATA_FLOW_CONTRACTS.md`](../DATA_FLOW_CONTRACTS.md) flows A, C

---

## Context

Late async candle loads, overlay refreshes, and background sync must not undo explicit user camera choices. MapStudio tracks a **viewport owner** and blocks automatic refits when a **stable owner** is active.

---

## Owners

| Owner | Meaning | Typical trigger |
|-------|---------|-----------------|
| `USER_PAN_ZOOM` | User dragged/zoomed chart | D3 pan/zoom handlers |
| `FIT_ALL` | User Fit All | `fitAllView` |
| `FIT_RANGE` | User Fit Range | `fitRangeView` |
| `FIT_REPLAY` | User Fit Replay | `fitReplayView` |
| `FIT_CASE` | User Fit Case | `fitCaseView` |
| `USER_LOCKED` | Locked camera domain | `lockCurrentView` / `RESTORE_LOCKED` |
| `TIMEFRAME_SWITCH` | One-shot fit after TF change | `switchTimeframePreserveCase`, `navigateStructuralChartContext` |
| `CAMPAIGN_CONTINUE` | One-shot fit after Continue | `continue-campaign` / `campaign-continue` reasons |
| `HIERARCHY_JUMP` | One-shot fit after explorer/audit jump | `explorer-jump-fit`, `audit-jump-fit`, `explorer-parent-context` |
| `SESSION_RESTORE` | Resume / open case fit | `session-restore`, `auto-resume`, `open-saved-case` |
| `AUTO` | System default; may be overridden | Initial load, jump-latest |

**Implementation note:** Code enum today includes `SESSION_RESTORE` but not `HIERARCHY_JUMP`. Hierarchy jumps currently set owners via `TIMEFRAME_SWITCH` or `inferViewOwnerFromCameraReason` → treat `explorer-jump*` as **`HIERARCHY_JUMP`** in debug logs; Pilot may add enum alias without changing fit behavior.

### Stable owners (block automatic refit)

```text
USER_PAN_ZOOM, FIT_ALL, FIT_RANGE, FIT_REPLAY, FIT_CASE,
USER_LOCKED, TIMEFRAME_SWITCH
```

Set: `STABLE_CAMERA_OWNERS` in `chartViewportPolicy.ts`.

`CAMPAIGN_CONTINUE`, `HIERARCHY_JUMP`, and `SESSION_RESTORE` are **one-shot navigation fits** — they claim camera once, then user actions should upgrade to a stable owner.

---

## Rules

### 1. Candle data changes must not move camera by themselves

- Applying parsed candles, merging background delta, or updating `candles[]` **must not** call `applyCameraCommand` unless `candleLoadMayMoveCamera` is true for explicit navigation reasons.
- Quiet reloads use `PRESERVE_OR_NEAREST_TIME` and respect stable owner via `shouldBlockAutomaticCameraRefit`.

### 2. Background sync must not refit camera

- `syncIncrementalDeltaFromVps` / 5m interval: upsert only.
- Chart candle merge on delta: **no** fit unless user explicitly navigates.

### 3. Overlay / audit refresh must not refit camera

- `refreshHierarchyAudit`, overlay projection updates, saved range list refresh: **read-only** for camera.
- Forbidden per PROJECT.RULES: audit refresh refits camera.

### 4. Timeframe switch may fit once

- Owner → `TIMEFRAME_SWITCH`.
- One fit via pending camera intent or deferred camera payload.
- Subsequent quiet loads must not refit.

### 5. Manual fit must survive late async loads

- After Fit All / Fit Range / Lock, stable owner blocks automatic refit from:
  - late candle responses
  - readable zoom recalc
  - overlay key changes
- Use `shouldBlockAutomaticCameraRefit(cameraViewOwner)` before applying camera from async paths.

### 6. Replay must not auto-pan unless explicitly enabled

- Arrow replay steps adjust **replay index** only by default.
- Auto-pan on replay requires explicit product flag (not default).
- `fitReplayView` is user-initiated → `FIT_REPLAY` owner.

### 7. Camera mutation must log reason/source in debug mode

- `setCameraViewOwnerWithLog(owner, source, reason)`
- `logCameraUpdate(reason, source, DEBUG_CAMERA)`
- Every `applyCameraCommand(intent, targetTime, reason, …)` must pass a **non-empty reason** string.

---

## Explicit navigation reasons

`isExplicitCameraNavigationReason()` whitelists reasons that may move camera during stable ownership transitions, including:

```text
fit-all, fit-range, fit-replay, fit-case, lock-view,
timeframe-switch, continue-campaign, explorer-jump, audit-jump,
drill-down, open-saved-case, manual-w/h, jump, fullscreen-layout-ready
```

---

## Forbidden behaviors

| Behavior | Status |
|----------|--------|
| Fit All then reset seconds later from async load | Forbidden |
| Audit refresh refits camera | Forbidden |
| Overlay refresh refits camera | Forbidden |
| Saved range list refresh refits camera | Forbidden |
| Replay step auto-pans without permission | Forbidden |
| Background delta sync refits camera | Forbidden |

---

## Pilot constraints

- Viewport patches: **`chartViewportPolicy.ts`**, camera paths in `main.tsx`, D3 chart props — not Campaign logic, not save logic.
- Viewport is a **dedicated subsystem** per task — do not mix with Session Persistence or Campaign Manager patches (see [`SYSTEM_MAP.md`](../SYSTEM_MAP.md) §5).
- Any new camera move must declare owner + reason.

---

## Related files

- `electron/src/chartViewportPolicy.ts`
- `electron/src/chartViewportPolicy.test.ts`
- `electron/src/main.tsx` — `applyCameraCommand`, `loadCandles` camera gating, `cameraViewOwner` state
