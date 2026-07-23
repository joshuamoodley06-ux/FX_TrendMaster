# Daily Doctrine Suite v1 (Draft Only)

This directory is intentionally **not registered** with the doctrine runtime.

It contains design-stage Python modules and focused tests for the Daily layer. The code must not be added to the application, candidate installer, runtime registry, bootstrap chain, Electron UI, or analytical database until Josh reviews the doctrine and explicitly approves implementation.

## Structural source of truth

- Backend / canonical Master Map owns Weekly and Daily ranges, parent links, anchors, lifecycle and BOS events.
- These scripts read saved structure and candle data.
- They never create, repair, infer or rewrite `parent_range_id`.
- Orphan and invalid Daily ranges remain visible as review evidence.
- Historical calculations use only information available at the candidate freeze time.

## Draft suite

### 1. Daily first-range Weekly transition

Classifies the first historically available Daily child associated with a new Weekly chapter.

Outputs:

- `WEEKLY_EXTERNAL_TO_INTERNAL`
- `WEEKLY_EXTERNAL_CONTINUATION`
- `WEEKLY_INTERNAL_FIRST_RANGE`
- `UNRESOLVED`

The classification is factual. It records where the first Daily range begins and completes relative to the Weekly external boundary. It does not call the setup tradable.

### 2. Daily first range at Weekly extreme rejection

Finds the first Daily child created after a confirmed Weekly discount or premium extreme rejection.

Weekly zones:

```text
Discount extreme = 0% to 25%
Fair Price        = 50%
Premium extreme  = 75% to 100%
```

The script records origin, first Daily range, Daily direction, relationship to the rejection, and whether the Daily range delivered away from the rejected extreme.

### 3. Daily pro-trend / counter-trend

Classifies Daily movement relative to the active Weekly BOS chapter:

```text
Weekly BOS_UP:
  Daily UP   = PRO_TREND
  Daily DOWN = COUNTER_TREND

Weekly BOS_DOWN:
  Daily DOWN = PRO_TREND
  Daily UP   = COUNTER_TREND
```

`SAME_D1`, unresolved anchor chronology, missing parent memory and invalid links remain review-only.

### 4. Daily BOS, reclaim, retracement and profile

Daily equivalents of the approved Weekly scripts:

```text
Daily BOS
Daily Reclaim
Daily Reclaim Depth
Daily Movement Classification
Daily Profile Classification
Daily Extreme Rejection Destination
```

Approved Weekly doctrine is preserved at D1 resolution:

- wick beyond RH/RL counts as BOS
- exact touch is not BOS
- same-candle event-order ambiguity remains `NEEDS_REVIEW`
- reclaim may occur on the BOS candle
- abandonment occurs when a later Daily BOS forms before reclaim
- profile thresholds remain:

```text
depth < 38.2%          -> S&R
38.2% <= depth <= 50%  -> S&R>FP
Depth > 50%            -> S&D
```

- abandoned continuation override remains `S&R` when source and next BOS directions match
- Daily extreme rejection uses the Daily range's own 0/25/50/75/100 geometry

### 5. Consecutive Daily profile streak

Counts consecutive **Daily ranges**, not candles, that complete with the same approved profile.

Outputs include:

- streak profile
- start and end Daily range IDs
- number of Daily ranges
- start and end time
- termination profile / reason
- whether the streak remains open at freeze

A missing or pending profile breaks certainty and creates an unresolved boundary. It is not silently skipped.

### 6. PDL / PDH extreme reversal sweep

Uses prior closed Daily candle levels:

```text
PDL sweep:
  current D1 low < previous D1 low
  and current D1 closes back above previous D1 low

PDH sweep:
  current D1 high > previous D1 high
  and current D1 closes back below previous D1 high
```

Location gate:

```text
PDL sweep valid only at Weekly discount / external low
PDH sweep valid only at Weekly premium / external high
```

Exact level touches are not sweeps because price must trade beyond the prior level. The sweep candle is a factual reversal candidate, not an automatic trade signal. Follow-through and later structural confirmation are reported separately.

## Deliberate non-implementation

The following are intentionally absent:

- runtime registration
- execution order assignment in the active chain
- package bootstrap changes
- candidate review UI
- database schema changes
- Electron wiring
- automatic publication
- automatic parent assignment

## Review sequence proposed later

```text
Daily BOS
-> Daily Reclaim
-> Daily Reclaim Depth
-> Daily Movement
-> Daily Profile
-> Daily Extreme Rejection
-> Weekly-to-Daily first-range transition
-> Weekly extreme rejection first Daily
-> Pro-trend / Counter-trend
-> Profile streak
-> PDL / PDH sweep
```

The sequence is only a design recommendation. Nothing in this directory is active doctrine yet.
