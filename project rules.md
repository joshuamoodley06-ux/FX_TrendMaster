# PROJECT_RULES.md Addendum

## 21. Temporal Drift / Parent-Child Revalidation

Parent-child links must remain valid when a range is edited.

A child range may become invalid if:

* its `range_start_time` changes
* its `range_end_time` changes
* its `range_high_price` changes
* its `range_low_price` changes
* its `structure_layer` changes
* its `source_timeframe` changes
* its `parent_range_id` changes

Whenever a mapped range is edited, the backend must revalidate its hierarchy.

### Revalidation rules

For a DAILY range:

* Parent must be WEEKLY.
* Parent must exist.
* Parent must match the same symbol.
* Parent should match the same case where applicable.
* Child time window should overlap or sit inside the parent time window where parent times are known.

For an INTRADAY range:

* Parent must be DAILY.
* Parent must exist.
* Parent must match the same symbol.
* Parent should match the same case where applicable.
* Child time window should overlap or sit inside the parent time window where parent times are known.

For MICRO later:

* Parent must be INTRADAY.
* Parent must exist.
* Parent must match the same symbol.
* Child time window should overlap or sit inside the parent time window where parent times are known.

### Important

A failed revalidation must not silently delete the range.

Instead, the range must be flagged as:

```text
parent_link_status = VALID / ORPHAN / INVALID_PARENT / NEEDS_REVIEW
```

If the database does not yet have `parent_link_status`, this status may be returned in audit output or stored in `meta_json` until a dedicated column is added.

Do not silently auto-correct parent links without showing the user.

The app may suggest a better parent, but the final link must be visible and reviewable.

---

## 22. Orphan Resolution / Fix Orphan Flow

Orphan ranges are allowed during mapping, but they must not become permanent hidden debt.

An orphan is:

* a DAILY range without a WEEKLY parent
* an INTRADAY range without a DAILY parent
* a MICRO range without an INTRADAY parent later

Orphans are not fatal errors.

Orphans are incomplete hierarchy links.

### Audit requirement

The mapping audit must always report:

* orphan DAILY ranges
* orphan INTRADAY ranges
* orphan MICRO ranges later
* invalid parent links
* ranges needing parent review

Audit output must include enough data to fix the orphan:

* range_id
* symbol
* structure_layer
* source_timeframe
* range_start_time
* range_end_time
* RH/RL prices
* suggested parent candidates if available

### Fix Orphan flow

The app must eventually provide a Fix Orphan workflow.

Minimum required behaviour:

```text
1. Show orphan range.
2. Show possible parent ranges.
3. Let user select correct parent.
4. Backend validates the parent link.
5. Save parent_range_id.
6. Re-run audit.
```

Cursor must not implement a rushed Fix Orphan UI unless explicitly asked.

For now, backend should support safe re-parenting or leave a clear TODO.

### Re-parenting rules

A re-parent action must validate:

* child range exists
* parent range exists
* child and parent have same symbol
* child and parent belong to same case where applicable
* parent layer is exactly one level higher
* child is not its own parent
* circular parent chains are impossible

Do not hard-delete or remap a child range during re-parenting.

Only update the hierarchy link.

---

## 23. Display vs Storage Rule

The system must never confuse chart display timeframe with structural source timeframe.

### Definitions

`chart_timeframe`:

* The timeframe currently displayed in Electron.
* This is a UI/view property.
* It may change when the user zooms or switches chart view.

`source_timeframe`:

* The timeframe the structural range was based on.
* This is structural metadata.
* It must remain stable unless the user intentionally edits the range.

`structure_layer`:

* The logical layer in the market hierarchy.
* Allowed values:

  * WEEKLY
  * DAILY
  * INTRADAY
  * MICRO

### Rule

Queries and audits must use hierarchy and structure metadata, not only current chart display.

A range must remain discoverable if:

* it belongs to the active case
* it belongs to the selected parent hierarchy
* it matches the selected structure layer
* it is linked through `parent_range_id`

A range must not disappear merely because:

* the current chart timeframe changed
* `chart_timeframe` differs from `source_timeframe`
* the user zoomed out or switched chart view

### Example

A DAILY range linked to a WEEKLY parent must remain visible in the Weekly hierarchy view.

An INTRADAY range based on H4 or H8 must remain linked to its DAILY parent even if Electron is currently showing H1 or D1.

The hierarchy is truth.

The chart timeframe is only the view.

---

## 24. Calculation Engine Versioning

Derived analytics must be reproducible.

Any calculated metric must record the calculation engine version that produced it.

Examples of calculated metrics:

* position_percent
* discount/fair/premium zone
* M1/M2/M3 bucket
* candle touched zone
* deepest mitigation
* sweep detection
* P1/P2/P3 detection
* time-to-target
* range outcome
* trade validation result
* management instruction

### Required version fields

Analytics outputs should include:

```text
calculation_engine_version
ruleset_version
analysis_type
created_at
```

If a dedicated column does not exist yet, store these values inside `meta_json` or `result_json`.

### Rule

Do not overwrite old analytics results without preserving the engine version.

If the calculation logic changes later, the system must be able to tell:

```text
This result was calculated using engine version v1.
This result was calculated using engine version v2.
```

This allows historical reproducibility.

The mapping database stores structural facts.

The analytics database stores derived results with versioned rules.

---

## 25. Implementation Order / Proof Path

The hierarchy must be proven in the simplest order.

Do not start with Intraday.

Do not start with Micro.

Do not start with ML.

Do not start with Amy.

### Required proof order

```text
Step 1: Weekly range save
Step 2: Daily range save
Step 3: Daily range linked to Weekly parent
Step 4: Audit proves Weekly → Daily hierarchy
Step 5: Range math derives discount/fair/premium from Weekly + Daily ranges
Step 6: Python HTF analytics v1
Step 7: Intraday range storage
Step 8: Intraday linked to Daily parent
Step 9: LTF analytics
Step 10: Trade validation / management
Step 11: Amy
Step 12: ML
```

### First validation target

The first production-ready mapping validation must prove:

```text
Case: XAUUSD_HTF_Mar2020_Mar2021

WEEKLY ranges: greater than 0
DAILY ranges: greater than 0
DAILY ranges linked to WEEKLY: greater than 0
Orphan DAILY ranges: 0 or intentionally confirmed
Ranges missing RH/RL: 0
BOS events missing BH/BL: 0
Hierarchy audit: PASS
```

Only after this works should Intraday mapping be expanded.

---

## 26. Cursor Phase Discipline

Cursor must not perform big-bang architecture changes.

All major mapping changes must be executed in phases:

```text
Phase 1: Database schema and safe migrations only
Phase 2: Backend endpoints and validation only
Phase 3: Electron UI only
Phase 4: Audit/export validation only if needed
```

Cursor must stop after each phase and report:

* files changed
* migration impact
* backend impact
* frontend impact
* risks
* TODOs
* test steps

Cursor must not begin the next phase until Josh explicitly approves.

If Cursor cannot complete a phase safely, it must stop and explain why.

No fake completion.

No silent rewrites.

No heroic refactors.

---

## 27. Mapping-Ready Definition of Done

The app is not mapping-ready until all of these pass:

```text
1. Backend starts cleanly.
2. DB migration logs show no destructive changes.
3. Electron opens cleanly.
4. Raw marker identity contract is preserved.
5. RH/RL can be assigned.
6. BH/BL can be assigned or saved through BOS events.
7. Weekly range saves with structure_layer = WEEKLY.
8. Daily range saves with structure_layer = DAILY.
9. Daily range can link to selected Weekly parent.
10. Audit shows Weekly → Daily hierarchy.
11. Audit reports orphan Daily ranges.
12. Old interpretation fields are hidden from active mapping.
13. Reset Mapping DB is protected behind Danger Zone.
14. Export/audit can be saved and reviewed.
```

Only after this definition is met should real historical Weekly/Daily mapping begin.
