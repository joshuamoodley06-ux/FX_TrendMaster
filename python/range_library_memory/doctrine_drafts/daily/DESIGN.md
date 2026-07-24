# Daily Doctrine Draft Laboratory

## Status

```text
DESIGNED
CODED AS PURE DRAFT FUNCTIONS
NOT RUNTIME REGISTERED
NOT INSERTED INTO THE DOCTRINE CHAIN
NOT PUBLISHED TO APPROVED MEMORY
NOT EXPOSED IN ELECTRON
```

This folder is intentionally isolated from `doctrine_package_runtime_registry.py`.
It is a review laboratory for Daily doctrine. Integration happens only after the
rules and validation samples are approved.

## Inputs kept as structural truth

- Canonical Master Map parent/child hierarchy
- `parent_range_id` evidence represented by trusted Weekly children
- approved Weekly doctrine memory
- approved Daily Mapping Coverage Audit memory
- approved Weekly/Daily Relationship Builder memory
- D1 candles supplied by the existing doctrine context

Draft code reports missing or invalid links. It never creates or repairs parents.

## Planned candidate order

```text
100  Daily BOS
110  Daily Reclaim
120  Daily Reclaim Depth
130  Daily Movement Classification
140  Daily Profile Classification
150  Daily Extreme Rejection Destination
160  Daily Child Trend Classification
170  First Daily External-to-Internal
180  First Daily at Weekly Extreme Rejection
190  Daily Profile Streaks
200  PDL / PDH Reversal Sweep
```

The numbers are planning references only. No runtime execution order is changed.

# 1. Approved Weekly doctrine ported to Daily

The first six candidates preserve the approved Weekly rules and replace:

```text
W1 candle  -> D1 candle
Weekly range -> Daily range
weeks -> Daily candles / days
```

## Daily BOS

- Daily range completion is the later RH/RL anchor.
- Same-D1 RH/RL anchors are supported.
- First later D1 wick strictly beyond RH or RL is BOS.
- Exact touch is not BOS.
- A D1 candle breaking both boundaries remains `NEEDS_REVIEW` because OHLC cannot
  prove which boundary broke first.

## Daily Reclaim

- `BOS_UP` reclaims the old RH.
- `BOS_DOWN` reclaims the old RL.
- Same BOS candle reclaim is day zero.
- First later D1 wick touching/crossing the broken boundary confirms reclaim.
- A later new Daily BOS before reclaim marks the source Daily range abandoned.
- A later reclaim after abandonment becomes `ABANDONED_THEN_RECLAIMED`.
- Reclaim and a new BOS on the same D1 remain review-only.

## Daily Reclaim Depth

- Reads mapped Daily Range 1 and mapped next Daily Range 2.
- Does not invent a lifecycle or rebuild ranges from candles.
- Candidate Range 2 must share the same trusted Weekly parent as Range 1.
- `BOS_UP`: Fib 0 = D1 RH, Fib 1 = D1 RL, measure Range 2 RL.
- `BOS_DOWN`: Fib 0 = D1 RL, Fib 1 = D1 RH, measure Range 2 RH.
- Anchor sequences remain:
  - `OPPOSITE_THEN_CONTINUATION`
  - `CONTINUATION_THEN_OPPOSITE`
  - `SAME_D1`
- Negative raw depth becomes trader-facing `NO_RETRACEMENT` at 0%; raw values stay
  stored for audit.

## Daily Movement Classification

- Movement starts immediately after the source Daily BOS.
- The source BOS candle and first later approved Daily BOS candle are excluded.
- For source `BOS_UP`: bearish D1 = countertrend, bullish D1 = protrend.
- For source `BOS_DOWN`: bullish D1 = countertrend, bearish D1 = protrend.
- Consecutive same-role candles merge into one movement leg.
- Doji/invalid OHLC remains `NEEDS_REVIEW`.
- Daily reclaim depth is optional enrichment and cannot delay factual movement.

## Daily Profile Classification

```text
depth < 38.2%          -> S&R
38.2% <= depth <= 50%  -> S&R>FP
depth > 50%            -> S&D
```

Exact 38.2% and exact 50% are `S&R>FP`.

Continuation override is retained:

```text
previous Daily reclaim = ABANDONED
and next Daily BOS direction = source Daily BOS direction
-> S&R
```

## Daily Extreme Rejection Destination

Daily range geometry uses the same approved zones:

```text
Discount extreme = 0% to 25%
Fair Price       = 50%
Premium extreme = 75% to 100%
```

- Discount rejection: D1 trades at/below 25% and closes strictly above 25%.
- Premium rejection: D1 trades at/above 75% and closes strictly below 75%.
- Exact 25%/75% touch counts when the close finishes back outside the extreme.
- A candle remaining inside the extreme is not a rejection.
- Destination ladder remains:
  - `NO_FOLLOW_THROUGH`
  - `FAIR_PRICE`
  - `OPPOSITE_EXTREME`
  - `OPPOSITE_EXTERNAL`
- Rejection candle proves a destination only by close. Later D1 candles use wicks.
- Same later D1 touching the origin external and a new destination remains
  `NEEDS_REVIEW`.

# 2. Weekly-relative Daily candidates

## Daily Child Trend Classification

Each historically available, valid Daily child is compared with the active Weekly
story direction.

Direction priority:

1. approved Weekly BOS direction
2. Weekly anchor chronology when the Weekly range is still in progress
3. unresolved when neither is trustworthy

```text
Daily direction matches Weekly direction -> PROTREND
Daily direction opposes Weekly direction -> COUNTERTREND
Unresolved Daily or Weekly direction      -> UNRESOLVED
```

This is range-to-parent classification. It is separate from the D1 candle movement
legs inside one Daily range.

## First Daily External-to-Internal

The script retains the first valid Daily child whose structural movement begins at
or beyond a Weekly external boundary and finishes inside that Weekly range.

```text
UP Daily:
origin = Daily RL at/below Weekly RL
finish = Daily RH strictly inside Weekly range

DOWN Daily:
origin = Daily RH at/above Weekly RH
finish = Daily RL strictly inside Weekly range
```

The output distinguishes exact external touch from travel beyond the external.
A Daily range spanning both Weekly externals remains review-only.

## First Daily at Weekly Extreme Rejection

- Reads approved Weekly Extreme Rejection Destination events.
- Reads ordered Weekly/Daily relationships.
- Matches each rejection date to the Daily child lifecycle available on that date.
- Retains every matched rejection and exposes the first event as the primary review
  candidate.
- Multiple overlapping Daily children owning the same rejection date remain
  `NEEDS_REVIEW`.
- No Daily child is inferred from price geometry.

## Daily Profile Streaks

- Reads ordered valid Daily children.
- Reads approved Daily Profile memory for each child.
- Counts consecutive children with the same profile.
- A missing/review profile breaks the streak rather than being guessed.
- Stores all streaks, maximum streak, and current streak at the Weekly freeze.

# 3. PDL / PDH reversal sweep

This draft uses a strict close-back-through definition:

```text
PDL reversal sweep:
current D1 low < previous D1 low
and current D1 close > previous D1 low
and the PDL level is in Weekly discount (0-25%) or below Weekly RL

PDH reversal sweep:
current D1 high > previous D1 high
and current D1 close < previous D1 high
and the PDH level is in Weekly premium (75-100%) or above Weekly RH
```

- Exact equal high/low is not a sweep.
- Both PDL and PDH swept on one D1 remains `NEEDS_REVIEW` because OHLC cannot prove
  the intraday order.
- The draft stores the sweep and reversal direction only. It does not yet invent a
  CHoCH, entry trigger, stop, or destination.

# 4. Deliberately open doctrine decisions

These are exposed in output instead of silently resolved:

1. Whether Weekly anchor chronology should remain the fallback direction for an
   active Weekly range after live review.
2. Whether an exact Weekly RH/RL touch qualifies as an external-origin Daily range.
   The draft records `AT_EXTERNAL` separately so this can be changed without losing
   evidence.
3. Whether a PDL/PDH sweep requires a later D1 confirmation candle in addition to
   the same-candle close-back-through rule.
4. Whether profile streaks should reset when the Weekly parent changes. The draft
   resets by design because every output is parent-scoped.
5. Whether the first Daily at a Weekly extreme rejection should be the child active
   on the rejection date or the first new child completed after rejection. The
   draft stores the active-on-date match because it is factual; a later version can
   derive the first post-rejection child separately.

# 5. Integration gate

Before runtime implementation:

```text
review doctrine assumptions
run focused pytest locally
review representative historical candidates
split/adapter package only if required by runtime loader
register one script at a time
approve 5/5 before the next dependency activates
add Electron presentation only after output is trusted
```
