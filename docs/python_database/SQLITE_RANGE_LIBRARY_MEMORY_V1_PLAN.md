# SQLite Range Library Memory v1 Plan

## 1. Overview

SQLite Range Library Memory v1 adds a Python-owned persistence layer for range-library import memory. Its purpose is to record raw imported range and event data, import outcomes, validation issues, and duplicate candidates so imports are traceable and repeatable without changing the existing mapping truth.

The raw Electron/backend mapping truth remains the source of truth. Python may store raw imports and import metadata, but it must not silently rewrite mapped truth, normalize doctrine fields into a new truth, rebuild the library from scratch, delete historical records, auto-merge duplicates, or introduce analytics/model logic in this phase.

Core guarantees:

- Every import gets logged.
- Suspicious data gets flagged.
- Re-imports are incremental and auditable.
- Duplicates are surfaced as candidates only.
- No analytics, scoring, model training, prediction, or automatic range doctrine interpretation is added in v1.

## 2. Proposed Python Modules

Proposed package namespace:

- `python/range_library_memory/__init__.py`
- `python/range_library_memory/config.py`
- `python/range_library_memory/db.py`
- `python/range_library_memory/schema.py`
- `python/range_library_memory/importer.py`
- `python/range_library_memory/validation.py`
- `python/range_library_memory/duplicates.py`
- `python/range_library_memory/cli.py`
- `python/range_library_memory/models.py`

Responsibilities:

- `config.py`: Resolves the SQLite database path from CLI arguments, environment variables, or repo defaults.
- `db.py`: Opens SQLite connections, applies pragmas, manages transactions, and exposes migration helpers.
- `schema.py`: Owns idempotent table creation and future schema version checks.
- `importer.py`: Coordinates raw import parsing, import run creation, row insertion, result summaries, and issue recording.
- `validation.py`: Performs non-mutating validation and emits validation issues.
- `duplicates.py`: Detects possible duplicate raw ranges/events and records candidate links without merging.
- `cli.py`: Provides the operator-facing commands for initialization, import, validation, duplicate scanning, and inspection.
- `models.py`: Defines typed Python data structures for raw import payloads and database rows.

These modules are planning targets only. They should be introduced in a later implementation PR with tests before use in production workflows.

## 3. SQLite Database Location

Default location:

```text
data/python_database/range_library_memory.sqlite3
```

Configuration precedence:

1. Explicit CLI flag: `--db-path`
2. Environment variable: `FXTM_RANGE_LIBRARY_MEMORY_DB`
3. Repo-local default: `data/python_database/range_library_memory.sqlite3`

Operational rules:

- The database file is append-oriented for import history.
- Parent directories may be created by initialization commands.
- Existing database files must be migrated forward only.
- Commands must never rebuild the database from scratch as an implicit recovery strategy.
- Destructive maintenance, if ever added, must require a separate explicit command and a backup path.

## 4. Tables

### `import_runs`

Records one row for every attempted import.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `run_uuid TEXT NOT NULL UNIQUE`
- `source_path TEXT NOT NULL`
- `source_sha256 TEXT`
- `source_kind TEXT NOT NULL`
- `started_at_utc TEXT NOT NULL`
- `finished_at_utc TEXT`
- `status TEXT NOT NULL`
- `requested_by TEXT`
- `tool_version TEXT`
- `notes TEXT`

Rules:

- A row is created before parsing begins.
- Failed imports still keep their `import_runs` row.
- `status` values should include `started`, `completed`, `completed_with_issues`, and `failed`.

### `raw_ranges`

Stores raw imported range records without silently rewriting mapped truth.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `import_run_id INTEGER NOT NULL REFERENCES import_runs(id)`
- `source_record_id TEXT`
- `symbol TEXT`
- `timeframe TEXT`
- `range_type TEXT`
- `start_time_utc TEXT`
- `end_time_utc TEXT`
- `high REAL`
- `low REAL`
- `raw_payload_json TEXT NOT NULL`
- `payload_sha256 TEXT NOT NULL`
- `created_at_utc TEXT NOT NULL`

Rules:

- `raw_payload_json` preserves the original imported record as received.
- Derived columns are indexing helpers only, not rewritten doctrine truth.
- If derived columns cannot be extracted confidently, they may be null and must be flagged through `validation_issues`.

### `raw_events`

Stores raw imported event records associated with ranges or standalone source events.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `import_run_id INTEGER NOT NULL REFERENCES import_runs(id)`
- `raw_range_id INTEGER REFERENCES raw_ranges(id)`
- `source_record_id TEXT`
- `event_type TEXT`
- `event_time_utc TEXT`
- `price REAL`
- `raw_payload_json TEXT NOT NULL`
- `payload_sha256 TEXT NOT NULL`
- `created_at_utc TEXT NOT NULL`

Rules:

- Events are stored as imported, not interpreted into analytics signals.
- Linking to `raw_ranges` is allowed only when the source import clearly provides that relationship.
- Unlinked events remain valid raw memory and may be flagged for review when context is missing.

### `range_import_results`

Stores per-run aggregate outcomes.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `import_run_id INTEGER NOT NULL UNIQUE REFERENCES import_runs(id)`
- `ranges_seen INTEGER NOT NULL DEFAULT 0`
- `ranges_inserted INTEGER NOT NULL DEFAULT 0`
- `ranges_reused INTEGER NOT NULL DEFAULT 0`
- `events_seen INTEGER NOT NULL DEFAULT 0`
- `events_inserted INTEGER NOT NULL DEFAULT 0`
- `events_reused INTEGER NOT NULL DEFAULT 0`
- `validation_issue_count INTEGER NOT NULL DEFAULT 0`
- `duplicate_candidate_count INTEGER NOT NULL DEFAULT 0`
- `summary_json TEXT`
- `created_at_utc TEXT NOT NULL`

Rules:

- Results summarize what happened; they do not authorize automatic repair.
- Reused counts refer to exact raw payload matches already stored, not semantic duplicate merges.

### `validation_issues`

Stores suspicious or invalid data discovered during import or explicit validation.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `import_run_id INTEGER REFERENCES import_runs(id)`
- `raw_range_id INTEGER REFERENCES raw_ranges(id)`
- `raw_event_id INTEGER REFERENCES raw_events(id)`
- `severity TEXT NOT NULL`
- `issue_code TEXT NOT NULL`
- `message TEXT NOT NULL`
- `field_name TEXT`
- `observed_value TEXT`
- `created_at_utc TEXT NOT NULL`
- `resolved_at_utc TEXT`
- `resolution_notes TEXT`

Rules:

- Validation flags suspicious data; it does not rewrite raw records.
- Resolution is manual bookkeeping only.
- Historical issues must not be silently deleted.

### `duplicate_candidates`

Stores possible duplicate relationships for human review.

Proposed columns:

- `id INTEGER PRIMARY KEY`
- `import_run_id INTEGER REFERENCES import_runs(id)`
- `candidate_type TEXT NOT NULL`
- `left_raw_range_id INTEGER REFERENCES raw_ranges(id)`
- `right_raw_range_id INTEGER REFERENCES raw_ranges(id)`
- `left_raw_event_id INTEGER REFERENCES raw_events(id)`
- `right_raw_event_id INTEGER REFERENCES raw_events(id)`
- `rule_code TEXT NOT NULL`
- `confidence TEXT NOT NULL`
- `reason TEXT NOT NULL`
- `created_at_utc TEXT NOT NULL`
- `review_status TEXT NOT NULL DEFAULT 'open'`
- `review_notes TEXT`

Rules:

- Duplicate candidates are advisory only.
- v1 must never auto-merge duplicate candidates.
- Candidate records should be retained for audit even after review.

## 5. Import Algorithm

1. Resolve the database path and initialize schema if needed.
2. Start a transaction.
3. Create an `import_runs` row with `status = 'started'`.
4. Read the source file and calculate `source_sha256`.
5. Parse the source into raw range and event records without changing doctrine semantics.
6. For each raw range:
   - Preserve the full original record in `raw_payload_json`.
   - Calculate `payload_sha256`.
   - Insert the row if the exact payload is new for the import memory.
   - Reuse the existing row if the exact payload already exists.
   - Record validation issues for missing, malformed, contradictory, or suspicious fields.
7. For each raw event:
   - Preserve the full original record in `raw_payload_json`.
   - Calculate `payload_sha256`.
   - Insert or reuse by exact payload identity.
   - Record validation issues without rewriting the event.
8. Run duplicate candidate detection against newly imported rows and relevant existing rows.
9. Insert a `range_import_results` summary.
10. Mark the import run as `completed` or `completed_with_issues`.
11. Commit the transaction.
12. If an unexpected error occurs, roll back row inserts from the transaction when possible and mark the import run as `failed` in a separate best-effort update.

## 6. Re-import Behavior

Re-imports are expected and must be safe.

Rules:

- Re-importing the same file creates a new `import_runs` row.
- Exact raw payload matches are reused instead of duplicated.
- Re-imports must not delete records from previous runs.
- Re-imports must not rebuild the database from scratch.
- Re-imports must not overwrite raw payload history.
- If the same source path has different content, it is treated as a new import run and flagged in the result summary.
- If the same raw payload appears in multiple files, the database records the import history without treating that as a merge.

## 7. Validation Rules

Validation is non-mutating and issue-based.

Initial range validation rules:

- Missing symbol.
- Missing timeframe.
- Unsupported or unknown timeframe string.
- Missing start or end timestamp.
- End timestamp earlier than start timestamp.
- Missing high or low when range price boundaries are expected.
- High lower than low.
- Non-numeric high, low, or price fields.
- Missing range type when the source format is expected to include it.
- Timestamp values that cannot be parsed into UTC.
- Raw payload too large for normal source expectations.
- Required source identifiers missing when the source format documents them.

Initial event validation rules:

- Missing event type.
- Missing event timestamp.
- Event timestamp cannot be parsed into UTC.
- Event price is non-numeric when present.
- Event references a source range id that is absent from the same import.
- Event has contradictory range linkage fields.

Validation severities:

- `info`: Useful review note.
- `warning`: Suspicious but import can continue.
- `error`: Bad record; raw payload may be stored but must be reported.
- `fatal`: Import cannot proceed reliably.

## 8. Duplicate Detection Rules

Duplicate detection records candidates only. It must never auto-merge or delete.

Initial range duplicate rules:

- `exact_payload_hash`: Same `payload_sha256`.
- `same_source_record_id`: Same source record id from different import runs.
- `same_range_window`: Same symbol, timeframe, start time, end time, high, and low.
- `overlapping_range_window`: Same symbol and timeframe with strongly overlapping time windows and matching or near-matching price boundaries.
- `same_window_different_payload`: Same symbol/timeframe/window but different raw payload hash.

Initial event duplicate rules:

- `exact_payload_hash`: Same `payload_sha256`.
- `same_source_record_id`: Same source event id from different import runs.
- `same_event_signature`: Same event type, timestamp, symbol context if available, and price.

Confidence values:

- `exact`: Payload hash or documented source id match.
- `high`: Same derived identity fields.
- `medium`: Strong overlap with small differences.
- `low`: Suspicious similarity that needs review.

## 9. CLI Commands

Proposed CLI module entry point:

```text
python -m range_library_memory.cli
```

Commands:

```text
init --db-path <path>
```

Creates parent directories if needed and applies schema migrations.

```text
import --source <path> --source-kind <kind> --db-path <path>
```

Imports a raw source file, logs the run, stores raw rows, records issues, and writes import results.

```text
validate --db-path <path> --import-run-id <id>
```

Runs validation for a specific import run and records issues without modifying raw records.

```text
scan-duplicates --db-path <path> --import-run-id <id>
```

Scans duplicate candidates for a specific import run.

```text
show-run --db-path <path> --import-run-id <id>
```

Shows import status, counts, validation issue counts, and duplicate candidate counts.

```text
list-runs --db-path <path> --limit <n>
```

Lists recent import runs.

Guardrails:

- No command silently deletes data.
- No command silently rebuilds the database.
- No command auto-merges duplicates.
- Any future destructive command must be explicit, isolated, documented, backed up, and tested.

## 10. Test Plan

Unit tests:

- Schema creation is idempotent.
- Database path resolution follows CLI, environment, default precedence.
- Every import creates an `import_runs` row.
- Failed imports retain a failed `import_runs` row where possible.
- Raw range payloads are stored without mutation.
- Raw event payloads are stored without mutation.
- Exact re-imports reuse existing raw payload rows and still create a new run.
- Validation emits expected issue codes for malformed records.
- Duplicate detection emits candidate rows without modifying source rows.

Integration tests:

- Import a representative fixture with ranges and events.
- Re-import the same fixture and assert no duplicate raw payload rows are created.
- Import a changed fixture with the same source path and assert a new run plus issue/result metadata.
- Import overlapping ranges and assert duplicate candidates are recorded.
- Verify no analytics/model tables or outputs are created.

Safety tests:

- Confirm no command removes prior import history.
- Confirm no command rewrites existing raw payload JSON.
- Confirm duplicate candidates remain candidates after scans.
- Confirm validation issue history remains available after subsequent imports.

## 11. Acceptance Criteria

- A docs-approved implementation plan exists for SQLite Range Library Memory v1.
- Planned behavior keeps raw Electron/backend mapping truth as source of truth.
- Python storage is limited to raw import memory, validation metadata, duplicate candidates, and import audit history.
- The plan explicitly forbids rebuilding from scratch, silent deletion, silent mapped-truth rewrites, and automatic duplicate merges.
- The plan defines all requested tables: `import_runs`, `raw_ranges`, `raw_events`, `range_import_results`, `validation_issues`, and `duplicate_candidates`.
- The plan defines import, re-import, validation, duplicate detection, CLI, and test behavior.
- No Electron files are modified.
- No backend files are modified.
- No Python production code is modified.
- No reports files are modified.
- No analytics or model logic is introduced.

## 12. Risks/Open Questions

- Exact source formats for the first importer need confirmation before implementation.
- The canonical repo-local database path may need adjustment if existing data directory conventions differ.
- Source id availability may vary by export format, which affects duplicate confidence.
- Payload size limits should be chosen after inspecting real source files.
- Future schema migrations need a versioning policy before v2.
- Manual review workflow for validation issues and duplicate candidates is not defined in v1.
- Backup and restore policy for the SQLite file should be specified before broad use.
- Whether import memory should be checked into source control or treated as local runtime state must be decided before implementation.
