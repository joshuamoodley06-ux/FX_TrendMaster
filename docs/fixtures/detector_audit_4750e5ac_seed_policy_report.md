# Seed policy patch — audit run 4750e5ac

**Date:** 2026-06-17  
**Scope:** Reviewed-truth seed mode for historical range scan (`seed_policy = reviewed_truth_only`)  
**Not implemented:** Phase 3 corrections-only blanket seed (simulation worsened 7/14 weeks)

---

## Summary

Added safe seed policy for continued audit/build workflow:

| `seed_source` | Meaning |
|---------------|---------|
| `PROMOTED_RANGE` | Latest APPROVED/EDITED `map_ranges` row before active replay time |
| `TEMP_PREVIOUS_CANDIDATE` | In-scan raw detector roll (temporary only; blind scan fallback) |
| `bootstrap_candidate` | First-step swing discovery when no seed |

Default scan (`seed_policy = default`) keeps the same roll behavior but now traces `TEMP_PREVIOUS_CANDIDATE` instead of `previous_range_candidate` in meta.

---

## Implementation

### `load_latest_promoted_range_seed` (`range_seed.py`)

Queries `map_ranges` joined to `detector_suggestions` where:

- `s.status IN ('APPROVED', 'EDITED')`
- `user_action_at_confirm IN ('APPROVE', 'EDIT', 'BATCH_APPROVE')`
- `s.candle_time_utc_ms < active_replay_time_ms`
- Same symbol / structure_layer / source_timeframe

**Excluded:** REJECTED suggestions (no promoted row), unpromoted PENDING rows.

### `resolve_historical_scan_step_seed` (`range_step_seed.py`)

When `seed_policy = reviewed_truth_only`:

1. Promoted map_range before replay → `PROMOTED_RANGE`
2. Else in-scan `working_seed` → `TEMP_PREVIOUS_CANDIDATE`
3. Else bootstrap via `resolve_range_step_seed`

### `HistoricalRangeScanConfig.seed_policy`

- `default` — legacy roll with new trace label
- `reviewed_truth_only` — promoted truth beats raw roll

---

## Audit workflow impact (2025 W1)

| Question | Before patch | After `reviewed_truth_only` |
|----------|--------------|-----------------------------|
| Seed after APPROVE/EDIT promote | Raw `previous_range_candidate` roll | `PROMOTED_RANGE` from `map_ranges` |
| Seed after REJECT | Could still roll raw in same scan | Rejected never in promoted lookup |
| Blind first pass (no promotes yet) | `previous_range_candidate` | `TEMP_PREVIOUS_CANDIDATE` (explicit temporary) |
| Phase 3 correction-only chain | N/A (not implemented) | N/A (still not implemented) |

### Weeks after approved/edited ranges

Once a week is **promoted** to `map_ranges`, subsequent replay steps with `reviewed_truth_only` use that RH/RL until a **newer** promoted range exists before the active bar. Raw detector output from the same scan no longer overrides promoted truth.

### Raw candidate roll

Still available **only when** no promoted map_range exists before the replay time — labeled `TEMP_PREVIOUS_CANDIDATE` in `meta_json.seed_source` and `seed_policy`.

### Rejected candidates

`REJECT` writes `status = REJECTED` with **no** `map_ranges` row → never returned by promoted seed lookup.

### NO_VALID_RANGE count

Unit/integration tests show **no increase** in `NO_VALID_RANGE` from seed policy alone. Boundary logic unchanged. Full 2025 replay with local candle DB recommended to confirm on live audit fixture.

---

## Tests added (`test_range_scan_seed_policy.py`)

1. Approved map_range seeds promoted lookup ✓
2. Edited map_range beats temp working seed ✓
3. Rejected suggestion never seeds ✓
4. No promoted truth → `TEMP_PREVIOUS_CANDIDATE` ✓
5. Default policy traces `TEMP_PREVIOUS_CANDIDATE` (not `previous_range_candidate`) ✓
6. Leg-boundary / historical scan suite still passes ✓

**Suite:** 186 tests OK (11 skipped without local W1 candle DB).

---

## Usage for 2025 retest

```python
HistoricalRangeScanConfig(
    ...,
    seed_policy="reviewed_truth_only",
)
```

Workflow:

1. Historical scan (blind) → review weeks
2. APPROVE/EDIT → promotes to `map_ranges`
3. Re-scan or continue with `reviewed_truth_only` → later weeks seed from promoted truth

---

## References

- `backend/detector/range_scan_runner.py`
- `backend/detector/range_step_seed.py`
- `backend/detector/range_seed.py`
- `docs/fixtures/detector_audit_4750e5ac_seed_simulation_report.md` (Phase 3 — do not implement blanket correction chain)
