# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly analysis chain

The repository currently keeps four distinct analytical scripts:

```text
weekly_bos.py                        -> weekly_structure
weekly_reclaim.py                    -> weekly_reclaim
weekly_reclaim_depth.py              -> weekly_reclaim_depth
weekly_movement_classification.py    -> weekly_movement_classification
```

They execute in order:

```text
Weekly BOS memory
-> Weekly reclaim / abandonment memory
-> Weekly Range 2 reclaim-depth memory
-> Weekly movement classification memory
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

## Weekly Range 2 reclaim depth v6

This package reads mapped ranges. It does not infer or build the range lifecycle.

The structural sequence is stored using two separate endpoints:

```text
Range 1 BOS
-> reclaim starts the next range sequence
-> new opposite anchor sets retracement depth
-> the later of RH and RL completes the mapped new range
```

The depth endpoint and range-completion endpoint are not assumed to be the same candle.

For `BOS_UP`:

```text
Fib 0 = W1 RH
Fib 1 = W1 RL
Depth endpoint = W2 RL
Raw depth = (W1 RH - W2 RL) / (W1 RH - W1 RL)
```

For `BOS_DOWN`:

```text
Fib 0 = W1 RL
Fib 1 = W1 RH
Depth endpoint = W2 RH
Raw depth = (W2 RH - W1 RL) / (W1 RH - W1 RL)
```

Both mapped anchor sequences remain valid:

```text
OPPOSITE_THEN_CONTINUATION
The reclaim/pullback creates the opposite anchor first.
A later continuation-side anchor completes the range.

CONTINUATION_THEN_OPPOSITE
The BOS leg has already created the continuation-side anchor.
A later reclaim creates the opposite anchor and completes the range.

SAME_W1
Both anchors belong to the same Weekly candle.
```

Range completion is always calculated from the actual later RH/RL anchor date. `active_from_time` is not allowed to claim that a range was complete before its second anchor existed.

The script selects the first mapped Weekly range that:

```text
completes on or after the reclaim
and
has its direction-specific opposite anchor on or after the reclaim
```

It does not skip the first valid mapped range merely because a later range looks cleaner.

Trader-facing classification:

```text
raw ratio < 0   -> NO_RETRACEMENT, trading depth 0%
raw ratio = 0   -> BOUNDARY_TOUCH, trading depth 0%
0 < ratio < 1   -> RETRACED_INTO_RANGE
raw ratio = 1   -> TOUCHED_OLD_OPPOSITE, 100%
raw ratio > 1   -> EXCEEDED_OLD_OPPOSITE
```

Pure `ABND` without a later reclaim does not create a reclaim-depth measurement. It remains pending until a later reclaim exists. `ABND→RECL` uses the later reclaim candle as the depth-window start.

Raw ratios remain unclamped for audit and research. Trader-facing depth never displays a negative retracement. No shallow, medium, or deep category is hardcoded.

## Weekly movement classification v2

This package consumes approved `weekly_reclaim_depth` memory. It does not redetect BOS, reclaim, Range 2, or Fib depth.

For `BOS_UP`:

```text
Countertrend movement:
old W1 RH -> W2 RL
Direction: DOWN

Protrend movement:
W2 RL -> W2 RH
Direction: UP
```

For `BOS_DOWN`:

```text
Countertrend movement:
old W1 RL -> W2 RH
Direction: UP

Protrend movement:
W2 RH -> W2 RL
Direction: DOWN
```

Movement weeks are counted from actual W1 candles, not by subtracting mapped anchor dates.

Weekly OHLC path doctrine:

```text
Bullish W1 = Open -> Low -> Close -> High
Bearish W1 = Open -> High -> Close -> Low
```

Therefore:

```text
BOS_UP
bearish W1 = countertrend
bullish W1 = protrend

BOS_DOWN
bullish W1 = countertrend
bearish W1 = protrend
```

The BOS candle is excluded from the new movement chapter. The script loads subsequent W1 candles through Range 2 completion and counts only candles matching each movement direction.

For mapped anchors on different W1 candles, their chronology defines the two movement windows. For `SAME_W1`, the shared anchor candle resolves the likely order:

```text
BOS_UP + bullish anchor W1  -> COUNTERTREND_THEN_PROTREND
BOS_UP + bearish anchor W1  -> PROTREND_THEN_COUNTERTREND
BOS_DOWN + bullish anchor W1 -> PROTREND_THEN_COUNTERTREND
BOS_DOWN + bearish anchor W1 -> COUNTERTREND_THEN_PROTREND
```

A same-W1 doji remains `NEEDS_REVIEW` because the specified OHLC path cannot establish the order.

The package stores only the basics needed for review and later statistics:

```text
Range 1 ID
Range 2 ID
BOS direction
movement sequence
countertrend classification, direction, distance, depth %, W1 count
protrend direction, distance, W1 count
```

This is not the future range-lifecycle/storyline builder. It labels movements already supported by approved mapped-range memory.

## Version and dependency workflow

The cockpit registers the current bundled package sources automatically. Older approved versions remain active for rollback until the new candidate is approved, but they cannot unlock a newer child package.

The required order is:

```text
approve latest BOS package
-> approve latest Reclaim package
-> approve latest Range 2 Depth package
-> approve latest Movement Classification package
```

During candidate review, the previous approved run is reused as immutable evidence rather than rerun against a newer pending parent. This keeps the trusted memory active while individual candidate decisions are saved and the cockpit refreshes.

The corrected `SAME_W1` BOS case is prioritized in the BOS v3 five-sample review. Reclaim reviews prioritize distinct lifecycle states such as `RECL`, `ABND`, and `ABND→RECL` when those examples exist. Depth reviews prioritize both anchor-order stories and distinct trader outcomes. Movement reviews prioritize both resolved movement orders, no-retracement, boundary-touch and ordinary-retracement examples where available.

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
