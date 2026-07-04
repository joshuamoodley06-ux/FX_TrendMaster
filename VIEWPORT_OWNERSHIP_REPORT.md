# Viewport Ownership Report - FXTM Architecture Investigation

## 1. Current Ownership

Viewport movement in the TradingView implementation is currently owned by the `TradingViewChart.tsx` component, specifically within a `useEffect` that monitors the `fitRequest` prop.

The component arbitrates viewport changes based on the `chartMode`:
- **`hierarchy` mode**: Uses `setVisibleRange({ from, to })`. This is the "Fitting" path.
- **`replay` mode**: Uses `applyReplayAnchorFit(fitRequest)`. This is the "Panning" path.
- **Other modes**: Handle routine memory switches or center on a `target` target time.

The production of these requests follows these call chains:

### Hierarchy Navigation / Structural Selection
`jumpToStructuralRangeInner` (main.tsx)
  → `navigateStructuralChartContext`
    → `applyCameraCommand`
      → `cameraCommand` (State)
        → `tradingViewFitRequest` (Memo)
          → `TradingViewChart` (Prop: `fitRequest`)

### Replay Cursor Tracking
`stepReplayForward` / `stepReplayBack` (main.tsx)
  → `requestTradingViewReplayStepFit`
    → `tradingViewReplayStepFitRequest` (State)
      → `tradingViewFitRequest` (Memo)
        → `TradingViewChart` (Prop: `fitRequest`)

---

## 2. Intended Ownership

Viewport movement responsibility should be divided between **Fitting** (defining both zoom level and position) and **Panning** (moving the window without changing zoom).

| Action | Intended Subsystem / Logic | Requirement |
| :--- | :--- | :--- |
| **Replay Cursor Tracking** | `applyReplayAnchorFit` (Panning) | Keep cursor visible; maintain zoom. |
| **Hierarchy Navigation** | Window Fit (`from`/`to`) | Show entire range; set zoom. |
| **Structural Navigation** | Window Fit (`from`/`to`) | Show entire range; set zoom. |
| **Parent Mapping** | Window Fit (`from`/`to`) | Align with parent boundaries. |
| **Child Mapping** | Window Fit (`from`/`to`) | Align with parent boundaries. |
| **Timeframe Switching** | Routine Memory / Anchoring | Restore last known zoom/position. |

---

## 3. Root Cause

The investigation confirmed that **structural navigation entering replay cursor logic** is the root cause of the failure.

In `TradingViewChart.tsx` (approx. line 650), the routing logic is implemented as follows:

```typescript
// Current Logic in TradingViewChart.tsx
if (chartMode === 'hierarchy') {
    // ... Fitting Logic (Uses from/to)
}

if (chartMode === 'replay') {
    const status = applyReplayAnchorFit(fitRequest); // ... Panning Logic (Ignores from/to)
}
```

When a range is selected from the hierarchy while Replay is active:
1. `chartMode` is correctly identified as `replay`.
2. `fitRequest` is produced with correct `from` and `to` boundaries for the selected range.
3. Because `chartMode === 'replay'`, the request is routed to `applyReplayAnchorFit`.
4. `applyReplayAnchorFit` only inspects `request.target` (the cursor).
5. If the cursor is already visible in the *stale* viewport, the function returns `skipped` and **ignores the fitting boundaries**.

---

## 4. Minimal Architectural Correction

The routing decision inside `TradingViewChart.tsx` must be made aware of the **Intent** of the request, not just the current **Mode** of the chart.

### Recommended Correction
1. **Component awareness**: `TradingViewChart` should use the existing helper `isStructuralNavigationReason(pendingFitReason)`.
2. **Routing Update**: The Fitting path (currently used only for `hierarchy` mode) should also be taken if the reason for the fit is structural navigation, even if the chart is in `replay` mode.
3. **Subsystem Isolation**: `applyReplayAnchorFit` should remain a specialized Panning subsystem and should **never** be responsible for processing Fitting requests (those containing `from`/`to`).

### Files Requiring Modification
- `electron/src/tradingView/TradingViewChart.tsx`: Update the `useEffect` that handles `fitRequest` to check for navigation intent when routing.
