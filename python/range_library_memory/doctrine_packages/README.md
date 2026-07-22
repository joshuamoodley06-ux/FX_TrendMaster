# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly analysis chain

The repository currently keeps three distinct analytical scripts:

```text
weekly_bos.py             -> weekly_structure
weekly_reclaim.py         -> weekly_reclaim
weekly_reclaim_depth.py   -> weekly_reclaim_depth
```

They execute in order:

```text
Weekly BOS memory
-> Weekly reclaim / abandonment memory
-> Weekly Range 2 reclaim-depth memory
```

Each script reads approved output from the previous step instead of repeating its work.

## Weekly BOS v3

`weekly_bos.py` owns:

```text
first future W1 wick beyond RH or RL
BOS direction
BOS candle and price
weeks to BOS
```

If RH and RL come from the same W1 candle, chronology is stored as `SAME_W1`. The script starts scanning after that anchor candle and the first later one-sided wick break establishes BOS. A later candle breaching both boundaries still requires review.

Its permanent memory key is `weekly_structure`. Only one current Weekly BOS package file is maintained. Older approved source versions remain in database history for rollback and audit; they do not remain as parallel package files.

## Weekly reclaim v2

`weekly_reclaim.py` owns:

```text
BOS_UP   -> old RH is the reclaim boundary
BOS_DOWN -> old RL is the reclaim boundary
```

A BOS candle may reclaim immediately:

```text
BOS_UP   -> wick breaks RH and the same W1 closes at/below RH
BOS_DOWN -> wick breaks RL and the same W1 closes at/above RL
```

That same-candle reclaim stores `weeks_to_reclaim = 0`.

When the BOS candle closes beyond the broken boundary, the next W1 starts the count. The first later wick touching or crossing the broken boundary stops the count.

Reclaim lifecycle values are:

```text
RECLAIMED                   -> RECL
ABANDONED                   -> ABND
ABANDONED_THEN_RECLAIMED    -> ABND→RECL
PENDING                     -> PEND
```

A newer approved Weekly BOS before the first boundary touch marks the old range abandoned. If price returns to the old boundary later, the state becomes `ABANDONED_THEN_RECLAIMED`; the abandonment and later reclaim dates and week counts are both retained.

If a later reclaim and a newer BOS occur on the same W1 candle, OHLC cannot prove event order and the result remains `NEEDS_REVIEW`.

## Weekly Range 2 reclaim depth v3

`weekly_reclaim_depth.py` measures the mapped opposite anchor of Range 2 against the full size of Range 1. It does not keep scanning future candles for an arbitrary deepest wick.

For `BOS_UP`:

```text
Fib 0 = W1 RH
Fib 1 = W1 RL
Measured anchor = W2 RL
Depth = (W1 RH - W2 RL) / (W1 RH - W1 RL)
```

For `BOS_DOWN`:

```text
Fib 0 = W1 RL
Fib 1 = W1 RH
Measured anchor = W2 RH
Depth = (W2 RH - W1 RL) / (W1 RH - W1 RL)
```

The script stores:

```text
Range 1 ID, RH, RL and size
Fib 0 and Fib 1 prices
Range 2 ID and chronology
W2 opposite anchor type, price and candle
W2 continuation anchor type, price and candle
depth price, Fib ratio and percentage
weeks from BOS to Range 2 definition
Range 2 formation weeks
whether the old opposite external was touched or exceeded
source reclaim status and timing
```

Depth is not clamped. Ratios below 0 or above 1 remain visible for audit and statistics. No shallow, medium, or deep category is hardcoded.

## Version and dependency workflow

The cockpit registers the current bundled package sources automatically. Older approved versions remain active for rollback until the new candidate is approved, but they cannot unlock a newer child package.

The required order is:

```text
approve latest BOS package
-> approve latest Reclaim package
-> approve latest Range 2 Depth package
```

During candidate review, the previous approved run is reused as immutable evidence rather than rerun against a newer pending parent. This keeps the trusted memory active while individual candidate decisions are saved and the cockpit refreshes.

The corrected `SAME_W1` BOS case is prioritized in the BOS v3 five-sample review. Reclaim reviews prioritize distinct lifecycle states such as `RECL`, `ABND`, and `ABND→RECL` when those examples exist.

## Approval workflow

Each script follows the same lifecycle:

```text
register package source
-> validate the exact source
-> run five review cases in the analysis workspace
-> keep every audit fact visible before and after approval
-> approve 5/5
-> store that exact source as the current approved version
-> run only the approved versions in execution order
```

The Electron audit panel deliberately keeps each fact on a full-width row at every monitor size. Maximizing the window must not transform the fixed Hierarchy rail into a clipped multi-column table.
