# Architecture Lock

## Locked doctrine

```text
Electron = visual interpreter + raw event emitter / keylogger
VPS FastAPI = master raw event ledger / evidence locker
Main PC / Python = processing brain / compiler
Amy = future reader/explainer of processed summaries
```

## Electron is not allowed to derive durable truth

Electron may display temporary UI visuals:

```text
active high/low lines
frozen boxes
W1 overlays on D1
markers
selected candle HUD
```

Electron must not permanently write:

```text
parent_range_id
zone_percent
profile_type
phase
objective
training labels
feature rows
processed ranges
```

## Raw mapping events allowed

```text
SET_INITIAL_ANCHOR
SET_ANCHOR
ADJUST_ANCHOR
MANUAL_BOS
AUTO_BOS
RECLAIM
ABANDON_RANGE
DELETE_RECORD
NOTE
```

## Ledger rules

- Append-only.
- No hard deletes.
- A delete is represented by `DELETE_RECORD`.
- `DELETE_RECORD.supersedes_event_id` points at the target record.
- Undo delete is another `DELETE_RECORD` targeting the previous delete.
- `candle_time_utc_ms` is the relational market-time key.
- `candle_index` is informational only.
- `price_int` + `price_scale` should be used for comparisons.
- `schema_version = raw_mapping_v1`.
- Export must contain `ledger_hash`.

## Processing order

```text
created_order = intent/order-of-recording
candle_time_utc_ms = market timeline order
```

Processor should first resolve intent order, then build market timeline.
