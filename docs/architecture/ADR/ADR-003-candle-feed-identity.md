# ADR-003: Candle Feed Identity (Mapping Safety Contract)

**Status:** Accepted (implemented in `candleFeedIdentity.ts`)  
**Date:** 2026-06-19  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../../project%20rules.md)  
**Authority:** Candle Feed Identity Rule, No Wrong-Candle Display Rule, Candle Loading Must Not Be Guarded Away

**See also:** [`DATA_FLOW_CONTRACTS.md`](../DATA_FLOW_CONTRACTS.md) flows A, D · [`GOLDEN_SMOKE.md`](../../testing/GOLDEN_SMOKE.md)

---

## Context

Mapping against the wrong OHLC series produces **database poison** (RH/RL/BOS tied to incorrect bars). The app maintains an explicit **`LoadedCandleContext`** stamped when a candle load succeeds, and evaluates **`evaluateCandleFeedGuard`** before marking/saving.

---

## Required invariant (before H / L / BOS / structural save)

All must **agree**:

| Field | Source |
|-------|--------|
| `structure_layer` | MapStudio mapping layer (MACRO…MICRO) |
| `source_timeframe` | Layer source TF selector |
| `chart_timeframe` | Selected chart tab TF |
| `loaded candle timeframe` | `LoadedCandleContext.chartTimeframe` |
| `displayed candle data` | `candles[]` count + TF alignment |
| `symbol` | Active symbol |
| `case_id` | Active mapping case display id |

Implementation: `ActiveMappingFeedSnapshot` vs `LoadedCandleContext` in `evaluateCandleFeedGuard()`.

### Layer ↔ timeframe defaults

| Layer | Allowed chart TFs | Default source |
|-------|-------------------|----------------|
| MACRO | MN1, W1 | MN1 |
| WEEKLY | W1 | W1 |
| DAILY | D1 | D1 |
| INTRADAY | H4, H1 | H1 |
| MICRO | M15, M5 | M15 |

---

## Rules

### 1. Wrong timeframe display is a critical bug

If tab says M15 but chart renders D1 bars → **P0 bug**.

On TF switch failure:

```text
clear stale candles
set loadedCandleContext = null
show diagnostic (formatMissingCandleMessage)
feed guard blocks marking
```

Enforced by: `shouldClearCandlesOnLoadStart`, empty apply path in `loadCandles`.

### 2. H / L / BOS blocked if feed missing / mismatched / loading

Guard blocks when:

| `mismatch` | Condition |
|------------|-----------|
| `loading` | `candleLoadInFlight` or chart loading |
| `empty` | Zero candles or no loaded context |
| `loaded-tf` | Loaded TF ≠ chart tab TF |
| `layer` | Loaded layer ≠ active layer |
| `source-tf` | Source TF invalid or ≠ loaded source |
| `chart-tab` | Chart TF not allowed for active layer |

Entry: `assertCandleFeedReady()` before mark/save actions in `main.tsx`.

### 3. Chart may show empty diagnostic

Acceptable failure UX:

```text
No M15 candles available for this window. Sync/import required.
```

Unacceptable:

```text
M15 tab selected while H1 candles remain visible
```

### 4. Chart may not show stale candles

Async race protection:

- `candleLoadSeqRef` + `activeTimeframeRef` + `isCurrentCandleLoadRequest`
- Stale responses discarded with log `stale-local` / `stale-parse`

### 5. Guard must block marking/saving only — not candle loading

**Allowed guard scope:**

```text
block H, L, BOS_UP, BOS_DOWN
block auto range save, auto BOS save, auto chain save
```

**Forbidden guard scope:**

```text
blocking loadCandles()
blocking local candle reads
blocking VPS delta sync
blocking chart render after valid candles arrive
```

When guard detects mismatch with recoverable reload:

```text
assertCandleFeedReady → loadCandles(reloadTf, { reason: 'feed-mismatch-reload', deferCamera: true })
```

This **triggers load** to fix feed — guard does not replace load path.

---

## LoadedCandleContext lifecycle

```text
loadCandles start (non-quiet)
  → clear loadedCandleContext
load success + candles applied
  → buildLoadedCandleContext({ requestId, symbol, caseId, chartTf, sourceTf, layer, count })
mark/save
  → assertCandleFeedReady()
```

Status line: `buildCandleFeedStatusLine()` — shows `FEED MISMATCH` when guard fails.

---

## Known gaps / assumptions

| Item | Status |
|------|--------|
| `SYSTEM_MAP.md` | Available — see [`SYSTEM_MAP.md`](../SYSTEM_MAP.md) §2 Candle loader |
| Rehydration `should_clear_ui` | May zero candles before local read — overlaps empty state; not feed guard but affects display |
| MN1 in library TFs | Layer allows MN1 chart; library sync list may omit until MN1 added |

---

## Pilot restrictions

- Feed identity patches: **`candleFeedIdentity.ts`**, guard call sites, `loadedCandleContext` stamping — not VPS routes, not detector.
- Never block `loadChartCandlesLocalFirst` inside guard functions.
- Adding a new mapping shortcut **must** call `assertCandleFeedReady`.

---

## Related files

- `electron/src/candleFeedIdentity.ts`
- `electron/src/candleFeedIdentity.test.ts`
- `electron/src/main.tsx` — `buildActiveCandleFeedSnapshot`, `assertCandleFeedReady`, `loadCandles` context stamp
