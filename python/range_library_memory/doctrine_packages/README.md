# FXTM doctrine packages

These are reviewed analytical packages. Storing a source file does not approve it.

## Weekly analysis chain

```text
10 weekly_bos.py                     -> weekly_structure
20 weekly_reclaim.py                 -> weekly_reclaim
30 weekly_reclaim_depth.py           -> weekly_reclaim_depth
40 weekly_movement_classification.py -> weekly_movement_classification
50 weekly_profile_classification.py  -> weekly_profile_classification
```

Each package owns one job. Later packages consume approved memory instead of redetecting earlier facts.

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

For BOS Up, depth uses W2 RL against W1 RH/RL. For BOS Down, depth uses W2 RH against W1 RL/RH.

Supported mapped anchor sequences:

```text
OPPOSITE_THEN_CONTINUATION
CONTINUATION_THEN_OPPOSITE
SAME_W1
```

Trader-facing depth:

```text
raw ratio < 0 -> NO_RETRACEMENT · 0%
raw ratio = 0 -> BOUNDARY_TOUCH · 0%
0 < ratio < 1 -> RETRACED_INTO_RANGE
raw ratio = 1 -> TOUCHED_OLD_OPPOSITE · 100%
raw ratio > 1 -> EXCEEDED_OLD_OPPOSITE
```

## Weekly movement classification v4

Movement counting starts immediately after the range BOS. It does not wait for reclaim or depth confirmation.

```text
Range 1 BOS candle excluded
-> classify each later W1
-> group consecutive CT/PT candles into legs
-> stop before the next approved BOS candle
```

Weekly OHLC doctrine:

```text
Bullish W1 = Open -> Low -> Close -> High
Bearish W1 = Open -> High -> Close -> Low
```

```text
BOS_UP:   bearish = CT, bullish = PT
BOS_DOWN: bullish = CT, bearish = PT
```

Example:

```text
CT 1W -> PT 1W -> CT 1W -> BOS_UP
```

Depth is optional enrichment. A movement path may complete while depth remains pending.

## Weekly profile classification v1

This package consumes approved Weekly reclaim and reclaim-depth memory.

Depth rules:

```text
depth < 38.2%       -> S&R
38.2% <= depth <= 50% -> S&R>FP
depth > 50%         -> S&D
```

Exact 38.2% and exact 50% belong to `S&R>FP`.

Continuation override:

```text
previous range = ABANDONED
and
next BOS direction = source BOS direction
-> S&R
```

The override may classify S&R without a completed depth result. An abandoned range followed by an opposite-direction BOS stays pending rather than being forced into a profile.

Approved hierarchy badges:

```text
◆ S&R
◆ S&R>FP
◆ S&D
```

The review card deliberately shows only:

```text
profile
depth
reclaim status
previous BOS direction
next BOS direction
classification basis
```

Review sampling prioritises all three profiles, the abandonment continuation override, and one unresolved case where available.

## Version and dependency workflow

```text
approve BOS v3
-> approve Reclaim v2
-> approve Depth v6
-> approve Movement v4
-> approve Profile v1
```

A pending per-range Depth result does not block Movement v4, but profile classification waits for depth unless the explicit `ABND + same-direction BOS` override applies.

## Approval workflow

```text
register package source
-> validate exact source
-> run five review cases
-> approve 5/5
-> exact source becomes current approved memory
-> approved packages run in execution order
```
