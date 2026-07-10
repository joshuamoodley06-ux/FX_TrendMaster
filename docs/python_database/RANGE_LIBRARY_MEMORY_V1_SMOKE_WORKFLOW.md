# Range Library Memory v1 Smoke Workflow

## Purpose

SQLite Range Library Memory v1 is the first safe SQLite memory layer for raw range and event imports. It records import runs, raw payloads, validation issues, duplicate candidates, and manual review bookkeeping so operators can inspect import history without opening SQLite directly.

This workflow does not change Electron/backend mapping truth. The raw Electron/backend mapping truth remains the source of truth.

This workflow does not perform analytics or model logic.

This workflow does not auto-merge duplicates, delete rows, repair raw data, or rewrite raw payload JSON.

## Commands

Run commands from the repository root.

Initialize a local database:

```powershell
python -m range_library_memory.cli init --db-path data/local/range_library_memory_smoke.sqlite3
```

Import a raw JSON source:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/basic_import.json --source-kind fixture --db-path data/local/range_library_memory_smoke.sqlite3
```

Bulk import a folder of JSON exports:

```powershell
python -m range_library_memory.cli bulk-import --source-dir data/local/range_memory_exports --source-kind fxtm_export --db-path data/local/range_library_memory_smoke.sqlite3
```

List recent import runs:

```powershell
python -m range_library_memory.cli list-runs --db-path data/local/range_library_memory_smoke.sqlite3 --limit 10
```

Show one import run:

```powershell
python -m range_library_memory.cli show-run --db-path data/local/range_library_memory_smoke.sqlite3 --import-run-id 1
```

List validation issues:

```powershell
python -m range_library_memory.cli list-issues --db-path data/local/range_library_memory_smoke.sqlite3 --status open --limit 20
```

Resolve one validation issue:

```powershell
python -m range_library_memory.cli resolve-issue --db-path data/local/range_library_memory_smoke.sqlite3 --issue-id 1 --notes "Reviewed during smoke test."
```

List duplicate candidates:

```powershell
python -m range_library_memory.cli list-duplicates --db-path data/local/range_library_memory_smoke.sqlite3 --status open --limit 20
```

Review one duplicate candidate:

```powershell
python -m range_library_memory.cli review-duplicate --db-path data/local/range_library_memory_smoke.sqlite3 --candidate-id 1 --status ignored --notes "Smoke test review only."
```

Allowed duplicate review statuses:

- `open`
- `confirmed_duplicate`
- `not_duplicate`
- `ignored`

## Example Smoke Flow

Use a local throwaway DB path:

```powershell
$db = "data/local/range_library_memory_smoke.sqlite3"
```

Initialize the DB:

```powershell
python -m range_library_memory.cli init --db-path $db
```

Import the basic fixture:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/basic_import.json --source-kind fixture --db-path $db
```

Import the validation issue fixture:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/validation_issues_import.json --source-kind fixture --db-path $db
```

Import the duplicate changed payload fixture:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/duplicate_changed_payload.json --source-kind fixture --db-path $db
```

Import the representative FXTM export-shape fixture:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/real_fxtm_export_shape.json --source-kind fxtm_export --db-path $db
```

List import runs:

```powershell
python -m range_library_memory.cli list-runs --db-path $db --limit 10
```

Show the latest run. Replace `3` with the latest run id from `list-runs`:

```powershell
python -m range_library_memory.cli show-run --db-path $db --import-run-id 3
```

List validation issues:

```powershell
python -m range_library_memory.cli list-issues --db-path $db --status open --limit 20
```

Resolve one issue. Replace `1` with an issue id from `list-issues`:

```powershell
python -m range_library_memory.cli resolve-issue --db-path $db --issue-id 1 --notes "Smoke test: reviewed issue."
```

List duplicate candidates:

```powershell
python -m range_library_memory.cli list-duplicates --db-path $db --status open --limit 20
```

Review one duplicate candidate. Replace `1` with a candidate id from `list-duplicates`:

```powershell
python -m range_library_memory.cli review-duplicate --db-path $db --candidate-id 1 --status confirmed_duplicate --notes "Smoke test: advisory duplicate confirmed."
```

JSON output is available for list/show commands where implemented:

```powershell
python -m range_library_memory.cli list-runs --db-path $db --limit 10 --json
python -m range_library_memory.cli show-run --db-path $db --import-run-id 3 --json
python -m range_library_memory.cli list-issues --db-path $db --status open --limit 20 --json
python -m range_library_memory.cli list-duplicates --db-path $db --status open --limit 20 --json
```

## Current FXTM Export Smoke Test

Use this focused smoke test when you want one clear local verification flow for the current FXTM analyst export package shape. The fixture is sanitized, small, and representative of the current app output wrapper, including `data.ranges`, `data.events`, metadata wrapper fields, and `data.raw_ledgers`.

Use a local throwaway DB path:

```powershell
$db = "data/local/range_library_memory_current_export_smoke.sqlite3"
```

Initialize the DB:

```powershell
python -m range_library_memory.cli init --db-path $db
```

Import the current FXTM export smoke fixture:

```powershell
python -m range_library_memory.cli import --source python/range_library_memory/tests/fixtures/current_fxtm_export_smoke.json --source-kind fxtm_export --db-path $db
```

List recent runs:

```powershell
python -m range_library_memory.cli list-runs --db-path $db --limit 5
```

Show the latest run. Replace `1` with the latest run id from `list-runs`:

```powershell
python -m range_library_memory.cli show-run --db-path $db --import-run-id 1
```

List duplicate candidates:

```powershell
python -m range_library_memory.cli list-duplicates --db-path $db --status open --limit 20
```

List validation issues:

```powershell
python -m range_library_memory.cli list-issues --db-path $db --status open --limit 20
```

Expected result:

- Import completes.
- `ranges_seen` is `2`.
- `events_seen` is `4`.
- `validation_issue_count` is `0`.
- Raw ledger events from `data.raw_ledgers` are included.
- `duplicate_candidate_count` may be `0` on the first import.
- No generated `.sqlite`, `.sqlite3`, or `.db` file should be committed.

## Export VPS Cases Safely

This workflow is intentionally offline. Do not point Range Library Memory directly at a production backend DB or VPS service. Export case JSON first, copy the JSON folder locally, and import from that local folder.

From a local copy of the source SQLite DB, export sanitized analyst package JSON files:

```powershell
python -m range_library_memory.export_cases --source-db data/local/source_case_copy.sqlite3 --output-dir data/local/range_memory_exports --symbol XAUUSD
```

Optional: limit the export while testing the workflow:

```powershell
python -m range_library_memory.export_cases --source-db data/local/source_case_copy.sqlite3 --output-dir data/local/range_memory_exports --symbol XAUUSD --limit 5
```

Bulk import the exported JSON folder into Range Library Memory:

```powershell
python -m range_library_memory.cli bulk-import --source-dir data/local/range_memory_exports --source-kind fxtm_export --db-path $db
```

Use JSON output for automation or logs:

```powershell
python -m range_library_memory.cli bulk-import --source-dir data/local/range_memory_exports --source-kind fxtm_export --db-path $db --json
```

Inspect the imported memory:

```powershell
python -m range_library_memory.cli list-runs --db-path $db --limit 20
python -m range_library_memory.cli show-run --db-path $db --import-run-id 1
python -m range_library_memory.cli list-issues --db-path $db --status open --limit 20
python -m range_library_memory.cli list-duplicates --db-path $db --status open --limit 20
```

Safety rules for VPS case export:

- Export to JSON first, then copy the JSON folder locally.
- Never connect this importer directly to VPS.
- Never point this importer directly at a production backend DB.
- Never commit exported real case JSON unless it has been deliberately sanitized.
- Never commit generated `.sqlite`, `.sqlite3`, or `.db` files.
- Treat duplicate candidates as advisory review items only.

## When This Fails

- Wrong working directory: run commands from the repository root so fixture paths resolve.
- Missing package import: set `PYTHONPATH=python` for the shell session if `range_library_memory` cannot be imported.
- Stale smoke DB: use a new `$db` path or remove the local throwaway DB before rerunning.
- Generated SQLite file in Git status: leave it untracked and remove or move it before committing.
- Real export shape changed: add a narrow importer compatibility patch only for the new raw export placement or key shape, while preserving raw payload JSON unchanged.
- Bulk import reports failed files: open the listed JSON file, fix or re-export it, then rerun bulk import. Successful files from the same run remain imported.

## Before Moving To Parent-Child Feature Engine

- Current FXTM export fixture imports successfully.
- Inspection commands show the expected range, event, validation, and duplicate counts.
- Raw payload preservation test passes.
- Validation review and duplicate review commands still pass tests.
- `python -m pytest python/range_library_memory/tests` passes.

## Safety Notes

- Never commit generated `.sqlite`, `.sqlite3`, or `.db` files.
- Use local paths such as `data/local/range_library_memory_smoke.sqlite3` for smoke testing.
- Inspection commands must not create databases.
- Review commands are manual bookkeeping only.
- Raw payload JSON remains untouched.
- Duplicate candidates are advisory only.
- Reviewing duplicate candidates never merges or deletes raw rows.
- Resolving validation issues never repairs or rewrites raw rows.

## Expected Verification

Human checks after the smoke flow:

- Tests pass.
- Imports create `import_runs` rows.
- The validation issue fixture import becomes `completed_with_issues`.
- Duplicate candidates do not change import status by themselves.
- Representative `fxtm_export` imports preserve saved range/event rows and raw ledger event objects as raw payload JSON.
- `range_import_results` shows validation issue and duplicate candidate counts.
- Resolved issues keep raw range and raw event rows unchanged.
- Reviewed duplicate candidates do not merge, delete, or rewrite anything.
- Generated SQLite files remain untracked and are not committed.
