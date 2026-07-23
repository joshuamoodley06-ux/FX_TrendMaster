# FXTM doctrine packages

These are reviewed analytical packages. Storing a source file does not approve it.

## Structure analysis chain

```text
10 weekly_bos.py                              -> weekly_structure
20 weekly_reclaim.py                          -> weekly_reclaim
30 weekly_reclaim_depth.py                    -> weekly_reclaim_depth
40 weekly_movement_classification.py          -> weekly_movement_classification
50 weekly_profile_classification.py           -> weekly_profile_classification
60 weekly_extreme_rejection_destination.py    -> weekly_extreme_rejection_destination
70 daily_mapping_coverage_audit.py             -> daily_mapping_coverage_audit
80 weekly_daily_relationship_builder.py        -> weekly_daily_relationship_builder
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
depth < 38.2%          -> S&R
38.2% <= depth <= 50%  -> S&R>FP
depth > 50%            -> S&D
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

## Weekly extreme rejection destination v1

Range geometry:

```text
Discount extreme = 0% to 25%
Fair Price       = 50%
Premium extreme = 75% to 100%
```

Confirmed rejection:

```text
Discount: trades at/below 25% and closes back above 25%
Premium:  trades at/above 75% and closes back below 75%
```

A candle merely remaining inside an extreme is not a rejection.

Destination ladder:

```text
NO_FOLLOW_THROUGH
FAIR_PRICE
OPPOSITE_EXTREME
OPPOSITE_EXTERNAL
```

The rejection candle may prove a destination only through its close. From the following W1 onward, wick touches count.

Each rejection journey stops when the opposite external is reached, the origin external later breaks, or available W1 data ends.

## Daily mapping coverage audit v1

The first Daily bridge script asks whether mapped Daily evidence was available at the Weekly candidate freeze. It does not interpret missing clicks as missing market structure.

Freeze rule:

```text
approved Weekly BOS time
fallback: persisted Weekly inactive time
```

Coverage states:

```text
COMPLETE
PARTIAL
NOT_MAPPED
MAPPING_GAP
INVALID_PARENT_LINK
```

Critical distinction:

```text
Weekly freeze before first mapped Daily history -> NOT_MAPPED
Daily mapping era exists but no linked Daily child -> MAPPING_GAP
```

The package reads direct Daily children from the canonical Master Map hierarchy. It never searches for substitute parents or repairs a bad link. Review-root evidence may expose an invalid link for audit, but it never becomes statistics-eligible hierarchy truth.

Stored facts include:

```text
weekly candidate/range ID
candidate freeze time and basis
first available mapped Daily time
Daily ranges found at freeze
all linked Daily ranges
future Daily ranges excluded
earliest/latest Daily range at freeze
front/middle/tail gaps
overlap count
invalid parent links
```

Future Daily children remain in the audit payload but are excluded from `daily_ranges_found` at the freeze.

## Weekly Daily relationship builder v1

This package consumes approved Daily Mapping Coverage Audit memory and builds one ordered relationship row per linked Daily range.

Each row stores:

```text
weekly candidate ID
weekly range ID
Daily range ID
Daily sequence number
Daily start/created/end time
Daily direction
Daily status at freeze
persisted parent relationship identity
parent-link validity
historical availability
relationship validity
```

Historical leakage guard:

```text
Daily created after Weekly freeze -> NOT_YET_CREATED
```

A future row stays visible for auditing but is not counted as a valid historical relationship.

Daily direction is factual anchor chronology only:

```text
RL before RH -> UP
RH before RL -> DOWN
same/missing anchor time -> UNRESOLVED
```

The builder preserves missing or invalid parent evidence as stored. It does not silently fill, repair, or substitute a parent ID.

The relationship builder does not calculate Daily profile, setup quality, mitigation, phase, or trade direction.

## Version and dependency workflow

```text
approve BOS v3
-> approve Reclaim v2
-> approve Depth v6
-> approve Movement v4
-> approve Profile v1
-> approve Extreme Rejection Destination v1
-> approve Daily Mapping Coverage Audit v1
-> approve Weekly Daily Relationship Builder v1
```

Scripts 3–5 of the planned Daily bridge remain intentionally unbuilt until the first two scripts pass five-candidate manual review.

## Approval workflow

```text
register package source
-> validate exact source
-> run five review cases
-> approve 5/5
-> exact source becomes current approved memory
-> approved packages run in execution order
```
