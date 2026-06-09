# FX TrendMaster Cockpit

Electron, FastAPI and Python trading research cockpit for raw mapping, replay, immutable ledger storage and structural market analysis.

## Current architecture

```text
Electron = visual interpreter + raw event emitter / keylogger
FastAPI VPS backend = raw event ledger / evidence locker
Python processor = authoritative state/range/feature builder
Amy = future private assistant that reads processed summaries
```

## Current folders

```text
backend/    Latest FastAPI backend patch with raw mapping ledger routes

electron/   Latest Electron cockpit patch: v087.29c raw case window ledger fix

processor/  Scaffold for the Python brain, intentionally modular

docs/       Architecture notes, decision logs, legacy exports and Cursor notes

scripts/    Useful setup/start helper scripts
```

## Important rule

Do not commit DB files, `.env` files, `node_modules`, build folders, logs, or private credentials. This repo is source code and documentation only. The candle DB and raw mapping DB stay on the VPS/local machine.

## Live backend domain

```text
https://api01.apexcoastalrentals.co.za
```

## Backend DB split

```text
DATABASE_PATH       = market_memory.db        # candle/history DB
RAW_MAPPING_DB_PATH = raw_mapping_v159.db     # raw immutable mapping ledger
```

## Raw mapping routes

```text
POST /api/v1/raw-mapping/cases
POST /api/v1/raw-mapping/events
POST /api/v1/raw-mapping/events/batch
POST /api/v1/raw-mapping/events/delete
GET  /api/v1/raw-mapping/events
GET  /api/v1/raw-mapping/events/export
```

## First processor target

```text
1. Pull raw case export from VPS
2. Verify schema_version and ledger_hash
3. Resolve DELETE_RECORD / supersedes chains
4. Build clean timeline by candle_time_utc_ms
5. Write audit JSON locally
```
