# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly analysis chain

```text
weekly_bos.py                        -> weekly_structure
weekly_reclaim.py                    -> weekly_reclaim
weekly_reclaim_depth.py              -> weekly_reclaim_depth
weekly_movement_classification.py    -> weekly_movement_classification
```

Execution order:

```text
Weekly BOS
-> Weekly reclaim / abandonment
-> Weekly Range 2 reclaim depth
-> Weekly movement classification
```

Each package owns one job. A later package may enrich earlier facts, but it must not delay facts that are already knowable.

## Weekly BOS v3

- first future W1 wick beyond RH or RL counts as BOS;
- exact boundary touch is not BOS;
- `SAME_W1` anchors are supported;
- first later one-sided wick break establishes BOS;
- a later W1 breaking both boundaries remains `NEEDS_REVIEW`.

## Weekly reclaim v2

```text
BOS_UP   -> old RH is reclaim boundary
BOS_DOWN -> old RL is reclaim boundary
```

A same-BOS-candle reclaim stores `weeks_to_reclaim = 0`. Otherwise the next W1 starts at week 1 and the first later boundary touch stops the count.

Lifecycle values:

```text
RECLAIMED                -> RECL
ABANDONED                -> ABND
ABANDONED_THEN_RECLAIMED -> ABND→RECL
PENDING                  -> PEND
```

If reclaim and a newer BOS occur on the same W1, OHLC cannot prove order and the result remains `NEEDS_REVIEW`.

## Weekly Range 2 reclaim depth v6

The package reads mapped ranges. It does not build the range lifecycle.

```text
Range 1 BOS
-> reclaim starts the next sequence
-> new opposite anchor sets depth
-> later RH/RL anchor completes Range 2
```

For BOS Up:

```text
Fib 0 = W1 RH
Fib 1 = W1 RL
Depth endpoint = W2 RL
```

For BOS Down:

```text
Fib 0 = W1 RL
Fib 1 = W1 RH
Depth endpoint = W2 RH
```

Supported mapped anchor sequences:

```text
OPPOSITE_THEN_CONTINUATION
CONTINUATION_THEN_OPPOSITE
SAME_W1
```

Range completion uses the actual later RH/RL anchor date. `active_from_time` cannot claim completion before the second anchor exists.

Trader-facing depth:

```text
raw ratio < 0 -> NO_RETRACEMENT · 0%
raw ratio = 0 -> BOUNDARY_TOUCH · 0%
0 < ratio < 1 -> RETRACED_INTO_RANGE
raw ratio = 1 -> TOUCHED_OLD_OPPOSITE · 100%
raw ratio > 1 -> EXCEEDED_OLD_OPPOSITE
```

## Weekly movement classification v4

Movement counting starts when the range breaks. It does not wait for reclaim or reclaim-depth confirmation.

The package reads approved Weekly BOS memory for every mapped Weekly range and finds the first later approved BOS event.

```text
Range 1 BOS candle
-> excluded from count
-> classify every later W1 candle
-> stop immediately before the next approved BOS candle
-> next BOS is the terminal event
```

Weekly OHLC direction doctrine:

```text
Bullish W1 = Open -> Low -> Close -> High
Bearish W1 = Open -> High -> Close -> Low
```

Movement roles:

```text
BOS_UP
bearish W1 = countertrend (CT)
bullish W1 = protrend (PT)

BOS_DOWN
bullish W1 = countertrend (CT)
bearish W1 = protrend (PT)
```

Consecutive candles with the same role form one leg. A role change starts a new leg.

Example:

```text
CT 1W -> PT 1W -> CT 1W -> BOS_UP
```

The package stores:

```text
movement_path
movement_sequence
ordered movement_legs with candle dates
movement leg count
countertrend leg count and total W1 count
protrend leg count and total W1 count
source BOS direction/date
next BOS direction/date
Range 1 and Range 2 IDs
```

Reclaim Depth is optional enrichment:

```text
Depth complete
-> add countertrend depth classification, distance and percentage
-> add protrend distance

Depth pending
-> movement path still completes
-> depth fields remain pending
-> countertrend classification = COUNTERTREND_LEG_DEPTH_PENDING
```

A completed movement chapter can therefore be approved while reclaim remains unconfirmed. A missing next approved BOS keeps the chapter `PENDING`. A doji between BOS events remains `NEEDS_REVIEW` until its role is defined.

This is still not the future range lifecycle/storyline builder. It preserves the factual ordered movement path that the later lifecycle script will consume.

## Version and dependency workflow

```text
approve latest BOS package
-> approve latest Reclaim package
-> approve latest Range 2 Depth package
-> approve latest Movement Classification package
```

A pending per-range Depth result no longer blocks Movement v4. Package versions remain chained so updated parent memory invalidates child results safely.

Movement v4 review prioritises:

```text
an alternating three-leg storyline
one chapter beginning CT
one chapter beginning PT
a depth-pending chapter
ordinary depth variation
```

## Approval workflow

```text
register package source
-> validate exact source
-> run five review cases
-> approve 5/5
-> exact source becomes current approved memory
-> approved packages run in execution order
```
