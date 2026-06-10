# FX TrendMaster Processor

Python brain for consuming raw mapping exports and compiling audited market structure.

## Pass 1

```bash
python -m processor.main --case-id <case_id>
```

Read-only against the VPS. Pass 1 will:

1. `GET /api/v1/raw-mapping/events/export?case_id=<case_id>`
2. Reject exports where `schema_version != raw_mapping_v1`
3. Recompute `ledger_hash` locally and compare to backend export
4. Resolve `DELETE_RECORD` / `supersedes_event_id` visibility chains
5. Write a local audit JSON under `exports/`

## Setup

From the repo root:

```bash
pip install -r processor/requirements.txt
```

Optional environment variables (see `.env.example`):

```text
FXTM_API_BASE=https://api01.apexcoastalrentals.co.za
FXTM_PROCESSOR_EXPORT_DIR=exports
```

Default API base is `https://api01.apexcoastalrentals.co.za`.

## Live case testing

Sample `case_id` values in older docs and smoke-test notes are illustrative. They may no longer exist on the live API.

For live testing, use a **current** `case_id` that exists in the backend's active `RAW_MAPPING_DB_PATH` (`raw_mapping_v159.db` on the VPS).

### Get a case_id

**From Electron**

1. Open the cockpit and create or select a case in raw-ledger mode.
2. Save mapping events to the VPS.
3. Copy the active `case_id` from the Case Manager / case payload shown in the UI.

**From the API**

Create a case:

```bash
curl -X POST "https://api01.apexcoastalrentals.co.za/api/v1/raw-mapping/cases" \
  -H "Content-Type: application/json" \
  -d "{\"symbol\":\"XAUUSD\",\"case_name\":\"processor_smoke\",\"base_timeframe\":\"W1\",\"price_scale_default\":100}"
```

The response includes `case_id`. Add events from Electron or `POST /api/v1/raw-mapping/events` before expecting a rich audit.

### Verify the case exists before running the processor

```bash
curl "https://api01.apexcoastalrentals.co.za/api/v1/raw-mapping/events/export?case_id=<case_id>"
```

Expected: HTTP `200` with `"ok": true`, `meta.schema_version`, `meta.ledger_hash`, and `sequence_by_intent`.

### Run Pass 1

From the repo root:

```bash
python -m processor.main --case-id <case_id>
```

Expected success output:

```text
Fetched case: <case_id>
Schema version: raw_mapping_v1
Backend ledger hash: <hex>
Local ledger hash: <hex>
Raw record count: N
Visible/surviving record count: V
Delete record count: D
Audit JSON path: exports/<case_id>_<timestamp>.audit.json
```

Inspect the audit JSON for:

- `ledger_hash_match: true`
- `visible_events` — surviving non-delete rows after delete resolution
- `delete_trail` — all `DELETE_RECORD` rows kept for audit
- `hidden_event_ids`, `orphaned_delete_ids`, `warnings`

### Troubleshooting

| Symptom | Likely meaning |
|---|---|
| HTTP `404` on `/events/export` | `case_id` is not in the active `RAW_MAPPING_DB_PATH`. Not necessarily a processor bug. |
| `Unsupported schema_version` | Backend export schema changed; processor needs an update. |
| `Ledger hash mismatch` | Local hash logic or ordering no longer matches backend export. Do not trust the audit output. |
| `Raw record count: 0` | Case exists but has no events yet. Processor may still succeed; audit will be empty. |

### Unit tests (offline)

No VPS required:

```bash
python -m pytest processor/tests/ -v
```
