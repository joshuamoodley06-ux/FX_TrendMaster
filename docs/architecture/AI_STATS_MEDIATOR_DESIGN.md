# AI Stats Mediator — Design (Python Query Authority + AI Explanation)

Status: **M1–M4 IMPLEMENTED** (query engine + Ask Analyst UI + OpenAI-compatible mediator).

---

## 0. What this is

An **AI Stats Mediator** that lets Josh ask natural-language trading/statistics
questions and receive answers **calculated by the Python Analyst**, not by the
AI.

| Layer | Role |
|-------|------|
| **Josh** | Asks in English |
| **AI Mediator** | Parses question → structured query JSON; explains Python results in trader language |
| **Python Query Engine** | Filters saved workspace reports/parquet; computes counts, rates, aggregates |
| **Electron UI** (later) | “Ask Analyst” panel: question input, query preview, run, display result + explanation |

This is **not** a trading brain, **not** ML prediction, **not** a mapping editor.

### Fit with the locked architecture

| Rule | Mediator behavior |
|------|-------------------|
| Python is the only calculation authority | AI never invents percentages or counts |
| Electron stays dumb | UI displays query JSON, Python result, AI text — no stat math in renderer |
| No backend DB writes | Query engine reads local workspace only |
| No auto-repair | AI cannot fix mappings or ranges |
| No trade signals | Explanations describe historical structure stats, not entries/exits |

The existing **Python Analyst V1.1** rule engine (`analyst/pipeline.py`) **produces**
reports. The **Query Engine** (`analyst/query_engine.py`) **consumes** them.
Neither layer writes to the VPS.

---

## 1. End-to-end flow

```
Josh English question
    → AI Mediator (query translator — Phase M2+)
    → Query Plan JSON  (mediator_query_v1)
    → Python Query Engine  (Phase M1)
    → query_result.json
    → AI Mediator (explanation layer — Phase M3+)
    → Trader-language answer (with sample size, filters, warnings)
```

**Phase M1** skips AI entirely: Josh (or a test fixture) writes query JSON by hand.

---

## 2. Hard rules (non-negotiable)

### AI must never

- Write to any database
- Repair mappings or ranges
- Create or modify analyst reports
- Generate trade signals or position advice
- Answer statistics without a Python `query_result.json`
- Hide low sample size
- Pretend confidence when data is weak
- Silently guess ambiguous layer/timeframe meaning

### AI must always show (in every answer)

1. Plain numeric answer
2. **Sample size**
3. **Symbol / year labels / case_refs** used
4. **Filters** applied (as returned by Python)
5. Continuation / failure / abandon / unresolved counts (when applicable)
6. **Warning** if sample size is small or data is incomplete

### Python must never

- Re-run rule models during query (read saved outputs only)
- POST to VPS or open mapping DBs
- Return aggregates without `sample_size` and `filters_applied`

### Thresholds (locked for V1)

| Condition | AI behavior |
|-----------|-------------|
| `sample_size == 0` | “No matching examples found in saved analyst data.” |
| `sample_size < 20` | “Sample size is too small to trust.” (still show numbers) |
| Ambiguous layer scope | Ask **one** clarification question, do not guess |
| Missing workspace year | Say which symbol/labels have no saved data |

---

## 3. Where things live

```
electron/python_analyst/
  analyst/
    query_engine.py          <- NEW (Phase M1)
    query/
      schema.py              <- mediator_query_v1 validation
      loaders.py             <- parquet + CSV + yearly_stats loaders
      filters.py             <- row filters + cross-report joins
      metrics.py             <- continuation_rate, group_by aggregates
      templates.py           <- question-type → primary report table map
  analyst_v1.py              <- MODIFIED: add --query CLI
  tests/
    fixtures/
      query_deep_retracement.json
    test_query_engine.py

%USERPROFILE%\Documents\FXTM_Analyst\workspace\
  XAUUSD/
    2020/                    <- year folder = batch label (may be 2020 or 2019_Q3-2021_Q1)
      normalized_ranges.parquet
      normalized_events.parquet
      yearly_stats.json
      reports/*.csv
    combined/
      XAUUSD_combined_stats.json
      XAUUSD_year_comparison.csv

Query output (default):
  workspace/<SYMBOL>/queries/<query_id>/query_result.json
  or stdout / path passed via --query-output
```

**Note:** Workspace batch folders are **user-chosen labels** (see Python Analyst
plan §7). Query JSON must support `year_labels: ["2020", "2019_Q3-2021_Q1"]`
in addition to calendar `years: [2020, 2021]` for folder resolution.

**Gap to fix when implementing:** `combined.py` today only scans digit-only
folder names. Query engine and combined rebuild should both accept any folder
with `yearly_stats.json`.

---

## 4. Mediator Query JSON schema (`mediator_query_v1`)

### 4.1 Full example (continuation + reclaim + zone)

```json
{
  "schema_version": "mediator_query_v1",
  "query_id": "optional-uuid-or-slug",
  "symbol": "XAUUSD",
  "years": [2020, 2021],
  "year_labels": [],
  "case_refs": [],
  "parent_layer": "WEEKLY",
  "child_layer": "DAILY",
  "bos_direction": "DOWN",
  "parent_zone": "PREMIUM",
  "child_zone": null,
  "break_zone": null,
  "reclaim_class": "SHALLOW",
  "retracement_class": null,
  "outcome": "CONTINUED",
  "impulse_index": null,
  "question_type": "continuation_rate",
  "group_by": ["year_label"],
  "metrics": [
    "sample_size",
    "continued_count",
    "failed_count",
    "abandoned_count",
    "unresolved_count",
    "continuation_rate",
    "failure_rate"
  ],
  "include_source_rows": false,
  "source_row_limit": 50
}
```

### 4.2 Field reference

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | string | Must be `mediator_query_v1` |
| `symbol` | string | Required. e.g. `XAUUSD` |
| `years` | int[] | Optional. Match `yearly_stats.json` `year` field |
| `year_labels` | string[] | Optional. Match workspace folder names / `label` |
| `case_refs` | string[] | Optional. Filter `case_ref` column where present |
| `parent_layer` | string | `MACRO`, `WEEKLY`, `DAILY`, `INTRADAY`, `MICRO`, … |
| `child_layer` | string | Child `structure_layer` or `layer` |
| `bos_direction` | string | `UP` / `DOWN` |
| `parent_zone` | string | `DISCOUNT`, `FAIR`, `PREMIUM`, or third e.g. `PREMIUM_M2` |
| `child_zone` | string | Zone of child RH/RL/midpoint (`start_zone`) |
| `break_zone` | string | Child BOS zone (`break_zone` in zone report) |
| `reclaim_class` | string | `SHALLOW`, `MID`, `DEEP` |
| `retracement_class` | string | `SHALLOW`, `MID`, `DEEP`, `EXTREME` |
| `outcome` | string | `CONTINUED`, `FAILED`, `ABANDONED`, `UNRESOLVED`, `OPPOSITE_BOS`, `PARENT_BOS` |
| `impulse_index` | int | 1, 2, 3 from sequence report |
| `question_type` | string | Routes to primary report + join plan (see §5) |
| `group_by` | string[] | `year`, `year_label`, `quarter`, `reclaim_class`, `impulse_index`, … |
| `metrics` | string[] | See §4.3 |
| `include_source_rows` | bool | Default false. If true, attach matching CSV rows (capped) |
| `source_row_limit` | int | Max rows in `source_rows` (default 50) |

If both `years` and `year_labels` are empty, query **all** saved batch folders
for the symbol (with explicit warning in result).

### 4.3 Supported metrics (V1)

| Metric | Meaning |
|--------|---------|
| `sample_size` | Rows after all filters |
| `continued_count` | `outcome == CONTINUED` |
| `failed_count` | `outcome == FAILED` |
| `abandoned_count` | `outcome == ABANDONED` or abandon report |
| `unresolved_count` | `outcome == UNRESOLVED` |
| `continuation_rate` | `continued / (continued + failed + abandoned)` — excludes unresolved unless metric requests it |
| `failure_rate` | `failed / resolved` |
| `abandon_rate` | `abandoned / resolved` |
| `average_retracement` | Mean `retracement_percent` |
| `median_retracement` | Median `retracement_percent` |
| `average_rotations` | Mean `rotations_count` |
| `median_rotations` | Median `rotations_count` |
| `reclaim_rate` | From reclaim report |

Unknown metrics → validation error before execution.

---

## 5. Question types → data sources (V1)

Python routes `question_type` (or inferred from filters) to **saved reports**.
Cross-report questions use **join keys** documented below.

### 5.1 Continuation rate questions

**Example:** “How often did Daily BOS up continue after deep retracement?”

| Primary table | `reports/retracement_stats.csv` |
| Filters | `structure_layer` = child_layer, `direction_of_break`, `retracement_class`, `outcome` |
| Outcome column | `outcome` |

**Columns (existing contract):**

`case_ref`, `symbol`, `parent_range_id`, `range_id`, `structure_layer`,
`direction_of_break`, `retracement_percent`, `retracement_class`,
`retracement_price`, `retracement_time`, `next_bos_direction`, `outcome`

### 5.2 Reclaim questions

**Example:** “Does shallow reclaim perform better than deep reclaim?”

| Primary table | `reports/bos_reclaim_report.csv` |
| Join for outcome | `retracement_stats` or `impulse_retest_sequence` on `range_id` |
| group_by | `reclaim_class` |

**Columns:**

`case_ref`, `symbol`, `range_id`, `bos_direction`, `reclaim_occurred`,
`reclaim_time`, `reclaim_candle_count_after_bos`, `reclaim_depth_percent`,
`reclaim_class`, `continuation_after_reclaim`, `candles_to_continuation_bos`,
`abandon_after_reclaim`

### 5.3 Premium / discount questions

**Example:** “How often does Daily BOS up from Weekly discount continue?”

| Primary table | `reports/range_zone_position.csv` |
| Join | `normalized_ranges.parquet` for parent `structure_layer` |
| Filters | parent_layer via join, child `structure_layer`, `break_zone` or `start_zone` |

**Zone report columns:**

`case_ref`, `symbol`, `parent_range_id`, `child_range_id`, `structure_layer`,
`rh_position_percent`, `rl_position_percent`, `midpoint_position_percent`,
`bos_position_percent`, `start_zone`, `start_zone_third`, `break_zone`,
`break_zone_third`

**Join logic:**

1. Load zone rows where `child_range_id` = child range.
2. Join `normalized_ranges.parquet` on `parent_range_id` → parent `structure_layer`.
3. Join `retracement_stats` or sequence on `child_range_id` for outcome / BOS direction.

**Example mediator query for Josh’s headline question:**

“Daily BOS down from Weekly premium continue after shallow reclaim”

```json
{
  "schema_version": "mediator_query_v1",
  "symbol": "XAUUSD",
  "year_labels": ["2019_Q3-2021_Q1"],
  "question_type": "continuation_reclaim_zone",
  "parent_layer": "WEEKLY",
  "child_layer": "DAILY",
  "bos_direction": "DOWN",
  "parent_zone": "PREMIUM",
  "reclaim_class": "SHALLOW",
  "metrics": ["sample_size", "continued_count", "failed_count", "abandoned_count", "unresolved_count", "continuation_rate"]
}
```

Primary path: `bos_reclaim_report` filtered by `bos_direction` + `reclaim_class`,
joined to zone report (`break_zone` starts with `PREMIUM` or parent discount/premium
logic), parent layer from ranges parquet, outcome from `retracement_stats.outcome`
on matching `range_id`.

### 5.4 Rotation questions

**Example:** “How many discount-to-premium rotations before Weekly breaks?”

| Primary table | `reports/extreme_rotation_report.csv` |
| Filters | `parent_layer` = WEEKLY |

**Columns:**

`parent_range_id`, `parent_layer`, `child_layer`, `premium_touches`,
`discount_touches`, `rotations_count`, `final_break_direction`,
`child_count_before_break`

### 5.5 Sequence questions

**Example:** “Is impulse 2 better than impulse 1?”

| Primary table | `reports/impulse_retest_sequence.csv` |
| group_by | `impulse_index` |

**Columns:**

`case_ref`, `parent_range_id`, `child_range_id`, `layer`, `sequence_direction`,
`impulse_index`, `retest_index`, `bos_event_id`, `reclaim_detected`,
`retracement_class`, `next_outcome`

### 5.6 Year comparison questions

**Example:** “What changed from 2020 to 2021?”

| Sources | `yearly_stats.json` per label, `combined/XAUUSD_combined_stats.json`, `year_comparison.csv` |
| Returns | Deltas in `rule_stats` continuation/retracement/rotation aggregates |

No row-level join — aggregate diff only.

---

## 6. Join key reference (for implementers)

| Key | Used between |
|-----|----------------|
| `range_id` | reclaim ↔ retracement ↔ ranges |
| `child_range_id` | zone ↔ retracement ↔ sequence |
| `parent_range_id` | zone ↔ rotation ↔ ranges hierarchy |
| `old_range_id` / `new_range_id` | abandon report ↔ ranges |
| `case_ref` | all case-scoped reports |
| `structure_layer` / `layer` | layer filters (normalize to uppercase) |

Always attach `year_label` (workspace folder name) and `symbol` when merging
multi-year frames.

---

## 7. Python Query Engine (`analyst/query_engine.py`)

### 7.1 Responsibilities

1. **Resolve workspace paths** for symbol + year labels
2. **Load** parquet + CSV + JSON (pandas)
3. **Validate** query against `mediator_query_v1`
4. **Apply filters** per question type
5. **Join** reports when needed (§6)
6. **Compute metrics** (§4.3)
7. **Emit** `query_result.json`

### 7.2 CLI (extends `analyst_v1.py`)

```bash
python analyst_v1.py --query query.json --workspace "C:\Users\joshu\Documents\FXTM_Analyst\workspace"

# Optional:
python analyst_v1.py --query query.json --workspace ... --query-output path/to/query_result.json
```

Exit codes: `0` success, `2` validation/IO error.

### 7.3 `query_result.json` schema (`mediator_result_v1`)

```json
{
  "schema_version": "mediator_result_v1",
  "query_id": "...",
  "status": "OK",
  "symbol": "XAUUSD",
  "year_labels_used": ["2020", "2021"],
  "case_refs_used": [],
  "filters_applied": {
    "parent_layer": "WEEKLY",
    "child_layer": "DAILY",
    "bos_direction": "DOWN",
    "parent_zone": "PREMIUM",
    "reclaim_class": "SHALLOW"
  },
  "question_type": "continuation_reclaim_zone",
  "sample_size": 53,
  "metrics": {
    "continued_count": 34,
    "failed_count": 13,
    "abandoned_count": 4,
    "unresolved_count": 2,
    "continuation_rate": 0.642
  },
  "grouped": [],
  "warnings": [
    "SAMPLE_SIZE_MODERATE: 53 rows — interpret with caution"
  ],
  "data_sources": [
    "XAUUSD/2020/reports/bos_reclaim_report.csv",
    "XAUUSD/2020/reports/range_zone_position.csv",
    "XAUUSD/2020/normalized_ranges.parquet"
  ],
  "source_rows": [],
  "generated_at_utc_ms": 1710000000000
}
```

| `status` | Meaning |
|----------|---------|
| `OK` | Query ran; see `sample_size` |
| `NO_DATA` | No matching rows |
| `NO_WORKSPACE` | Symbol or year labels not found |
| `VALIDATION_ERROR` | Bad query JSON |
| `PARTIAL_DATA` | Some year folders missing reports |

Warnings (non-fatal, always listed):

- `NO_MATCHING_ROWS`
- `SAMPLE_SIZE_SMALL` (< 20)
- `SAMPLE_SIZE_MODERATE` (20–49)
- `MISSING_YEAR_FOLDER`
- `MISSING_REPORT_FILE`
- `JOIN_ROWS_DROPPED` (orphan keys after join)

---

## 8. AI response format (Phase M3+)

Every mediated answer uses **five blocks**:

1. **Plain answer** — one sentence with the key number
2. **Data sample** — counts table
3. **Filters used** — mirror `filters_applied` from Python
4. **Important warning** — sample size tier + data gaps
5. **Trader interpretation** — structural reading, not trade advice

### Example (target output)

**Question:** How often did Daily BOS down from Weekly premium continue after shallow reclaim?

**Answer:** Across XAUUSD 2020–2021, Daily BOS_DOWN from Weekly premium with shallow reclaim continued **64.2%** of the time.

**Data:**

- Sample size: 53
- Continued: 34
- Failed: 13
- Abandoned: 4
- Unresolved: 2

**Filters used:** Parent WEEKLY, child DAILY, parent zone PREMIUM, BOS DOWN, reclaim SHALLOW.

**Warning:** Sample size is moderate; more mapped years may shift the rate.

**Trader interpretation:** Shallow reclaim after bearish Daily BOS from Weekly premium leans continuation-favorable, but failure still occurs in roughly one in four resolved cases.

---

## 9. Electron UI (Phase M4 — “Ask Analyst” panel)

Add to **Data Collection Statistics** (`analystPage.tsx`), below Results or as a tab:

```
+----------------------------------------------------------------------+
| ASK ANALYST (Mediator)                                               |
| [ natural language question textarea ]                               |
| [ Build Query ]  [ Run Python ]  [ Explain Result ]                |
|                                                                      |
| Generated query JSON (editable)                                      |
| Python query_result.json (read-only JSON viewer)                     |
| AI explanation (markdown)                                            |
+----------------------------------------------------------------------+
```

### IPC additions (main.cjs + preload.cjs)

| Channel | Action |
|---------|--------|
| `analyst:writeQuery` | Save query JSON to `FXTM_Analyst/queries/` |
| `analyst:runQuery` | Spawn `analyst_v1.py --query ...` |
| `analyst:readQueryResult` | Read `query_result.json` |
| `analyst:explainResult` | Phase M3: call AI API with **only** result JSON + original question |

**Phase M1–M2:** No `explainResult` — explanation is manual or omitted.

### AI API boundary (M2/M3)

- **Input to AI:** user question + optional prior query + `mediator_query_v1` schema doc
- **Output from AI:** `mediator_query_v1` JSON only (M2)
- **Input to explainer:** user question + full `query_result.json` (M3)
- **Output from explainer:** markdown text following §8
- **Never send:** raw candle dumps, full parquet, VPS credentials

Configurable: API key in Electron settings / env, model choice, offline = disabled.

---

## 10. Implementation phases

### Phase M1 — Query engine without AI ✓

- [x] `analyst/query/schema.py` — validate `mediator_query_v1`
- [x] `analyst/query/loaders.py` — load workspace years + reports
- [x] `analyst/query/filters.py` — row filters + joins
- [x] `analyst/query/metrics.py` — aggregation
- [x] `analyst/query/templates.py` — question-type routing
- [x] `analyst/query_engine.py` — orchestrator
- [x] `analyst_v1.py --query` CLI
- [x] `analyst/storage/batches.py` + combined loader fix
- [x] Tests in `tests/test_query_engine.py`

### Phase M2 — AI query translator ✓

- [x] OpenAI-compatible API client (`mediatorAi.cjs`)
- [x] Prompt + schema-constrained JSON generation
- [x] User inspects/edits query before Run
- [x] Clarification flow for ambiguous layer scope

### Phase M3 — AI explanation layer ✓

- [x] Explainer prompt with hard rules (§2, §8)
- [x] Cites `sample_size` and `filters_applied` from Python only
- [x] Refuses to invent numbers (prompt-bound to result JSON)

### Phase M4 — Follow-up questions ✓

- [x] Session state: previous query + result in UI
- [x] AI emits modified query JSON on follow-up
- [x] Ask Analyst panel in `analystPage.tsx`

---

## 11. V1 acceptance test

**Josh asks:** “How often did deep Daily retracements continue?”

**AI produces query JSON:**

```json
{
  "schema_version": "mediator_query_v1",
  "symbol": "XAUUSD",
  "child_layer": "DAILY",
  "retracement_class": "DEEP",
  "question_type": "continuation_rate",
  "metrics": ["sample_size", "continued_count", "failed_count", "abandoned_count", "unresolved_count", "continuation_rate"]
}
```

**Python returns:** `sample_size`, continued/failed/abandoned/unresolved counts, `continuation_rate`.

**AI explains:** result %, sample size, filters used, warning if weak sample.

**Pass criteria:**

- Numbers in AI text **exactly match** `query_result.json` metrics
- No trade signal language
- Warning present when `sample_size < 20`

---

## 12. Files touched by phase

| Phase | Files |
|-------|-------|
| M1 | `electron/python_analyst/analyst/query/**`, `query_engine.py`, `analyst_v1.py`, `tests/test_query_engine.py` |
| M2–M3 | `electron/src/mediatorClient.ts`, `analystPage.tsx` (Ask panel), optional `mediatorPrompts.ts` |
| M4 | Same UI + session state in renderer |
| IPC | `electron/electron/main.cjs`, `preload.cjs` |

**Not touched:** `backend/`, `processor/`, VPS routes, mapping DB.

---

## 13. Decisions (locked with user, M1)

1. **Query output location:** `workspace/<SYMBOL>/queries/<query_id>/` (includes `query.json` + `query_result.json`)
2. **Unresolved in rate denominator:** excluded; `unresolved_count` shown separately
3. **AI provider:** deferred to M2/M3
4. **Combined folder scan:** non-digit batch labels supported via `analyst/storage/batches.py`
5. **`group_by quarter`:** deferred to M2

---

## 14. Relationship to Python Analyst V1.1

| Component | Produces | Consumes |
|-----------|----------|----------|
| Rule engine (`pipeline.py`) | Yearly CSV/parquet/stats | VPS input JSON |
| Query engine (`query_engine.py`) | `query_result.json` | Saved yearly outputs |
| AI Mediator | English ↔ query ↔ explanation | Query JSON + result JSON |

The Data Collection Statistics page **already** runs the rule engine (Phases A–E).
The Mediator **adds a read-only query layer** on top — no change to how reports
are generated.
