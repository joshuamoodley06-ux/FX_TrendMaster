# Current Status - 2026-06-10

## Backend

Validated routes:

```text
POST /api/v1/raw-mapping/cases
POST /api/v1/raw-mapping/events
POST /api/v1/raw-mapping/events/delete
GET  /api/v1/raw-mapping/events/export
```

Validated case:

```text
case_id = 4a029f89-d810-4bc5-90b4-0efb4c4346f3
```

Validated first event:

```text
event_id = 40fe12e6-9366-489d-8767-a69402e99c92
```

Validated delete modifier:

```text
event_id = 0bae740f-d2d1-4977-91b2-b828c1838814
```

## DB split

Backend must be started with:

```text
DATABASE_PATH=C:\Users\Administrator\Desktop\FXTM App\trading_gate\app\market_memory.db
RAW_MAPPING_DB_PATH=C:\Users\Administrator\Desktop\FXTM App\trading_gate\data\raw_mapping_v159.db
```

Do not point `DATABASE_PATH` at the raw mapping DB, or candle loading breaks.

## Electron

Latest patch in this repo:

```text
v087.29c raw case window ledger fix
```

Purpose:

```text
- prevent stale YTD/chart window from mutating Case Manager window
- ignore legacy map event bundles in raw-ledger mode
- keep Case Save aligned to raw mapping routes
```
