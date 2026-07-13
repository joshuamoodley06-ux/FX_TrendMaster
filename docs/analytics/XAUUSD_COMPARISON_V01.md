# XAUUSD Structural Comparison v0.1

## Scope

Read-only Python Truth Engine logic. It compares trusted structural states and returns every linked historical example. It does not write raw mapping storage, Master Map ingestion tables, Electron state, or VPS data.

## Smallest input contract

A live state uses `xauusd_structural_state_v0.1`:

```json
{
  "schema_version": "xauusd_structural_state_v0.1",
  "state_id": "live-id",
  "symbol": "XAUUSD",
  "as_of_time": "2026-07-10T12:00:00Z",
  "trust_status": "TRUSTED",
  "parent_direction": "UP",
  "parent_origin": "DEMAND",
  "parent_range": {"low": 3200.0, "high": 3400.0},
  "current_price": 3270.0,
  "child_relationship": "PROTREND",
  "bos_state": "UP",
  "reclaim_state": "WICK",
  "retest_state": "HELD",
  "ltf_confirmation_state": "CONFIRMED_UP",
  "event_sequence": ["BOS_UP", "RECLAIM_WICK", "RETEST_HELD", "LTF_CONFIRMED_UP"]
}
```

Historical fixture cases add:

- `example_id`, `case_ref`, `source_refs`, and a stable `example_ref.link`
- `base_state`
- timestamped `event_timeline`
- `freeze_at`, which creates the same-stage historical snapshot
- a separate `outcome` object

Outcome data is never passed into matching or scoring.

## Structural normalisation

Location is calculated as:

```text
(current_price - parent_low) / (parent_high - parent_low)
```

Absolute XAUUSD price is not compared. Location is also labelled as below-parent, lower extreme, lower, equilibrium, upper, upper extreme, or above-parent.

Event similarity uses longest-common-subsequence order. Candle spacing and identical candle count are not comparison inputs.

## Match tiers

### Strong structural match

- exact parent direction, parent origin, child relationship, BOS, reclaim, retest, and lower-timeframe state
- exact structural event sequence
- normalised location difference no greater than `0.08`

### Close match

- exact parent direction, parent origin, child relationship, and model family
- normalised location difference no greater than `0.20`
- event-order similarity at least `0.75`
- same terminal structural event
- no more than two BOS/reclaim/retest/lower-timeframe state differences
- weighted structural score at least `0.78`

### Broader model-family match

- same parent direction and model family
- normalised location difference no greater than `0.40`
- event-order similarity at least `0.50`
- same terminal structural event

Tiers remain separate. Requested tiers are explicit. An empty strong sample is not widened automatically.

## Trust filtering

A historical snapshot must be explicitly `TRUSTED`. Any `NEEDS_REVIEW` or `EXCLUDED` value in trust, review, resolution, or parent-link status removes that example before matching. The report discloses filtered counts.

## Outcome definitions

- `CONTINUATION`: the declared continuation destination is reached first.
- `FAILURE`: the declared structural invalidation/failure destination is reached first.
- `ALTERNATIVE`: another declared structural destination is reached before either primary continuation or failure destination.

Each outcome stores the reached destination and bars to destination by timeframe. These labels are fixture truth in v0.1; the Master Map adapter will later populate them from the settled Task 1 output.

## Output contract

`xauusd_comparison_report_v0.1` returns:

- normalised query state and requested tiers
- records seen, trusted records used, and exclusion counts
- separate strong, close, and model-family sections
- sample size per section
- continuation, failure, and alternative frequencies
- next structural destination frequencies
- time-to-destination summary by timeframe
- every linked historical example, its score/evidence, frozen state summary, and outcome

## Controlled fixture run

```bash
PYTHONPATH=python python -m range_library_memory.structural_comparison \
  --fixture python/range_library_memory/tests/fixtures/xauusd_comparison_v01.json
```

## Josh doctrine still required

The engine deliberately leaves these as explicit contract values instead of inventing trading doctrine:

1. Final parent-origin vocabulary and whether origin means zone, creation mechanism, or both.
2. Exact live definitions for retest `HELD`, `FAILED`, and lower-timeframe confirmation.
3. Canonical destination names and which destination wins when multiple are touched in one candle.
4. Whether time-to-destination should use D1 bars, source-timeframe bars, elapsed sessions, or all three.
5. Whether location bands should use fixed quartiles, the current mitigation M1/M2/M3 zones, or another structural partition.
