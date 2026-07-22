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

## Weekly Range 2 reclaim depth v5

The depth window is tied to the actual structural sequence:

```text
Range 1 BOS
-> reclaim begins the pullback
-> first new Weekly range formed after that reclaim is Range 2
-> Range 2 formation stops the depth window
```

The script does not skip the first new range merely because a later range has a more convenient chronology. Chronology remains visible for audit, but it is not allowed to push the measurement months forward.

For `BOS_UP`:

```text
Fib 0 = W1 RH
Fib 1 = W1 RL
Measured anchor = W2 RL
Raw depth = (W1 RH - W2 RL) / (W1 RH - W1 RL)
```

For `BOS_DOWN`:

```text
Fib 0 = W1 RL
Fib 1 = W1 RH
Measured anchor = W2 RH
Raw depth = (W2 RH - W1 RL) / (W1 RH - W1 RL)
```

The trader-facing result is classified as:

```text
raw ratio < 0   -> NO_RETRACEMENT, trading depth 0%
raw ratio = 0   -> BOUNDARY_TOUCH, trading depth 0%
0 < ratio < 1   -> RETRACED_INTO_RANGE
raw ratio = 1   -> TOUCHED_OLD_OPPOSITE, 100%
raw ratio > 1   -> EXCEEDED_OLD_OPPOSITE
```

A Range 2 opposite anchor that remains above the broken RH after `BOS_UP`, or below the broken RL after `BOS_DOWN`, is therefore shown as `NO_RETRACEMENT` rather than a negative percentage. The distance beyond the broken boundary is stored and included in the review reason text.

The script stores both trader-facing and raw audit values:

```text
Range 1 ID, RH, RL and size
Fib 0 and Fib 1 prices
Range 2 ID and chronology
Range 2 selection rule
reclaim-to-Range-2 depth-window start and stop dates
W2 opposite anchor type, price and candle
W2 continuation anchor type, price and candle
trader-facing depth price, ratio, percentage and classification
raw depth price, ratio and percentage
boundary distance and relative position
weeks from BOS to Range 2 definition
weeks from reclaim to Range 2 definition
Range 2 formation weeks
whether the old opposite external was touched or exceeded
source reclaim status and timing
```

Pure `ABND` without a later reclaim does not create a reclaim-depth measurement. It remains pending until a later reclaim exists. `ABND→RECL` uses the later reclaim candle as the depth-window start.

Raw ratios remain unclamped for audit and research. Trader-facing depth never displays a negative retracement. No shallow, medium, or deep category is hardcoded.

## Version and dependency workflow

The cockpit registers the current bundled package sources automatically. Older approved versions remain active for rollback until the new candidate is approved, but they cannot unlock a newer child package.

The required order is:

```text
approve latest BOS package
-> approve latest Reclaim package
-> approve latest Range 2 Depth package
```

During candidate review, the previous approved run is reused as immutable evidence rather than rerun against a newer pending parent. This keeps the trusted memory active while individual candidate decisions are saved and the cockpit refreshes.

The corrected `SAME_W1` BOS case is prioritized in the BOS v3 five-sample review. Reclaim reviews prioritize distinct lifecycle states such as `RECL`, `ABND`, and `ABND→RECL` when those examples exist. Depth reviews prioritize distinct trader outcomes such as `NO_RETRACEMENT`, `BOUNDARY_TOUCH`, ordinary in-range retracement and old-opposite exceedance.

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
