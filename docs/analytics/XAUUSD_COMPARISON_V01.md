# XAUUSD Structural Comparison v0.1

## Scope

Read-only Python Truth Engine logic. It compares trusted structural states and returns every linked historical example. It does not write raw mapping storage, Master Map ingestion tables, Electron state, or VPS data.

Task B adds a conservative adapter from the merged `xauusd_master_map_v0.1` output to `xauusd_structural_state_v0.1`. The adapter reads canonical output only and does not change Master Map identity, lifecycle, relationship, or review rules.

## State input contract

A comparison state uses `xauusd_structural_state_v0.1`:

```json
{
  "schema_version": "xauusd_structural_state_v0.1",
  "state_id": "canonical-event-id@frozen-time",
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

Historical examples also carry a stable example link, source provenance, a frozen snapshot time, and a separate factual outcome. Outcome data is never passed into matching or scoring.

## Master Map adapter contract

Adapter schema: `xauusd_master_map_comparison_adapter_v0.1`.

Source requirements:

- Master Map schema must be `xauusd_master_map_v0.1` for `XAUUSD`.
- `structural_content_hash`, `root`, and `trusted_root` are mandatory.
- Candidate states are built only from canonical ranges and events present in `trusted_root`.
- The child range must have `navigation_status=TRUSTED`, `statistics_status=ELIGIBLE`, and `direct_parent_link_status=VALID`.
- Weekly/root ranges are not converted because the v0.1 comparison state requires a factual parent range.
- One frozen candidate is created per trusted `BOS_UP` or `BOS_DOWN` event.
- Only direct canonical events whose chart time is at or before the freeze event are included.

Every candidate preserves:

- Master Map `structural_content_hash`
- canonical child range ID and canonical parent range ID
- canonical event IDs and freeze-event ID
- child and parent source-record provenance
- structure layer and source timeframe
- range, event, active, inactive, and frozen chart times
- direct parent relationship status
- ordered factual event sequence

Review, excluded, unresolved-parent, hidden/unmaterialized, unsupported freeze-event, and root-without-parent records are disclosed with reasons. Missing comparison doctrine is never inferred.

## Missing doctrine handling

Fields unavailable from factual Master Map v0.1 output remain `UNKNOWN` or `NOT_AVAILABLE`. A state with a required unavailable field is marked `EXCLUDED` from comparison rather than normalized into a guessed value.

A separate doctrine-annotation input may populate approved values. Each annotation requires an `annotation_ref`, and its fields are copied into provenance. An annotation does not mutate the Master Map.

Fields still requiring approved doctrine include:

1. Parent direction as intended by the comparison contract. It is not automatically taken from a parent range's later break direction or latest BOS.
2. Final parent-origin vocabulary and whether origin means zone, creation mechanism, or both.
3. ProTrend, CounterTrend, and Transition classification at the frozen child event.
4. Exact reclaim wick/close semantics when they are not explicit canonical events.
5. Retest `HELD` and `FAILED` definitions.
6. Lower-timeframe confirmation definitions.
7. Continuation, failure, and alternative outcome destinations and tie handling.
8. Whether time-to-destination uses D1 bars, source-timeframe bars, sessions, or multiple measures.
9. Whether location bands remain quartiles or later use mitigation M1/M2/M3 zones.

## Outcome separation and no hindsight

Outcomes are optional factual inputs keyed by canonical event or range ID. Missing outcomes are represented as `NOT_AVAILABLE`.

- Outcome fields never qualify a state, select a tier, or contribute to a score.
- A factual outcome cannot occur before the frozen state.
- Historical candidates at or after the target freeze are excluded from that report.
- Future canonical events are never copied into an earlier frozen state.

## Structural normalization

Location is calculated as:

```text
(current_price - parent_low) / (parent_high - parent_low)
```

Absolute XAUUSD price is not compared. Event similarity uses longest-common-subsequence order. Candle spacing and identical candle count are not comparison inputs.

## Match tiers

### Strong structural match

- exact parent direction, parent origin, child relationship, BOS, reclaim, retest, and lower-timeframe state
- exact structural event sequence
- normalized location difference no greater than `0.08`

### Close match

- exact parent direction, parent origin, child relationship, and model family
- normalized location difference no greater than `0.20`
- event-order similarity at least `0.75`
- same terminal structural event
- no more than two BOS/reclaim/retest/lower-timeframe state differences
- weighted structural score at least `0.78`

### Broader model-family match

- same parent direction and model family
- normalized location difference no greater than `0.40`
- event-order similarity at least `0.50`
- same terminal structural event

Tiers remain separate. Requested tiers are explicit. An empty strong sample is not widened automatically.

## Report contract

`xauusd_master_map_real_comparison_report_v0.1` returns:

- records reported, materialized, trusted, blocked, and excluded with reasons
- linked canonical IDs, source references, chart times, and timeframes
- separate strong, close, and broader-family sections
- continuation, failure, alternative, and `NOT_AVAILABLE` frequencies
- destination and time-to-destination summaries where factual outcome data exists
- all blocked states and doctrine fields still required

## Commands

Controlled fixture engine:

```bash
PYTHONPATH=python python -m range_library_memory.structural_comparison \
  --fixture python/range_library_memory/tests/fixtures/xauusd_comparison_v01.json
```

Real Master Map JSON:

```bash
PYTHONPATH=python python -m range_library_memory.master_map_comparison_adapter \
  --master-map /path/to/xauusd_master_map_v01.json \
  --output /tmp/xauusd_comparison_report.json
```

Range Library database containing `master_map_outputs`:

```bash
PYTHONPATH=python python -m range_library_memory.master_map_comparison_adapter \
  --range-library-db /path/to/range_library.db \
  --output /tmp/xauusd_comparison_report.json
```

Doctrine annotations and factual outcomes are optional separate files:

```bash
  --doctrine-annotations /path/to/approved_annotations.json \
  --outcomes /path/to/factual_outcomes.json
```
