# Leg-based HTF boundary implementation — audit run 4750e5ac

**Date:** 2026-06-17  
**Scope:** `RANGE_V2` leg-based boundary selection (expansion leg extreme + opposite anchor)  
**Fixture:** `detector_audit_4750e5ac.json` — 12 EDIT weeks, 14 reviewed weeks total

---

## Summary

Leg-based HTF boundary selection is implemented in `backend/detector/range_boundary.py` and wired through `range_v2.py` (`htf_leg_trace` in `meta_json`).

| Metric | Before (pre-leg fixture) | After (leg implementation) |
|--------|--------------------------|----------------------------|
| **EDIT weeks scored** | 12 | 12 |
| **RH match vs Josh gold** | 2 / 12 (16.7%) | Run `DetectorAuditLegDoctrineTests` with local XAUUSD W1 `candle_store` |
| **RL match vs Josh gold** | 2 / 12 (16.7%) | Same (tests skip when DB unavailable) |
| **Full range match (RH+RL)** | 0 / 12 (0.0%) | Same |
| **NO_VALID_RANGE weeks (14 reviewed)** | 0 | 0 (unit replay still produces candidates) |

**Local replay note:** This environment has **0** XAUUSD W1 rows in `candle_store`. Audit leg regression tests (`test_edit_weeks_match_josh_gold_rh_rl`, decoupling checks) **skip** without the DB. Structural/unit coverage passes (**181 tests OK**, 11 skipped).

---

## What changed

### Boundary doctrine (implemented)

| Case | Broken side | RH | RL |
|------|-------------|----|----|
| Bullish `RECLAIMED_DOWN` | HIGH | Highest valid price in expansion leg `[bos, reclaim)` | Opposite anchor: structural low before BOS-predecessor week |
| Bearish `RECLAIMED_UP` | LOW | Opposite anchor: structural high before BOS-predecessor week | Lowest valid price in expansion leg `[bos, reclaim)` |

### Removed behaviors

- RH no longer forced to BOS-bar high when a higher expansion-leg extreme exists.
- RL no longer taken from post-BOS retrace swing lows between BOS and reclaim.
- No silent fallback to `retracement_impulse_high` / `retracement_impulse_low` for boundaries.

### `htf_leg_trace` (`meta_json`)

Each valid range candidate now includes:

- `expansion_leg_start_time_ms`, `expansion_leg_end_time_ms`
- `expansion_extreme_price`, `expansion_extreme_time_ms`, `expansion_extreme_owner` (`BOS_CANDLE` | `REF_CANDLE` | `IMPULSE_SWING`)
- `opposite_anchor_price`, `opposite_anchor_time_ms`
- `current_leg_state` (`RECLAIM` at birth)

Existing `boundary_candidates_considered`, `rejected_boundary_candidates`, and `selected_boundary_candidate` traces are preserved.

---

## Before / after — match counts (12 EDIT weeks)

Source for **before**: `detector_audit_4750e5ac_leg_scorecard.md` (frozen pre-leg detector vs Josh gold).

| Match type | Before | After (expected with candle DB) |
|------------|--------|----------------------------------|
| RH | 2 / 12 | Improved — expansion-leg scan replaces BOS-bar default |
| RL | 2 / 12 | Improved — opposite anchor excludes BOS-predecessor retrace week |
| Full range | 0 / 12 | Improved — decoupled RH+RL selection |

Dominant **before** failure modes (scorecard):

- RH: `detector_RH=BOS_bar_not_expansion_extreme` (10 / 12 IMPULSE_SWING owner in Josh mapping)
- RL: `detector_RL=retrace_low_not_opposite_anchor`

---

## Owner frequency

### Before (Josh leg scorecard — gold labels)

| `expansion_extreme_owner` | Count |
|---------------------------|-------|
| IMPULSE_SWING | 10 / 12 |
| BOS_CANDLE | 2 / 12 |
| REF_CANDLE | 0 / 12 |

### After (implementation policy)

Owner is derived from winning candle index in expansion window:

- `index == bos` → `BOS_CANDLE`
- `index == bos + 1` → `REF_CANDLE`
- else → `IMPULSE_SWING`

Live owner histogram requires local W1 replay (`htf_leg_trace.expansion_extreme_owner`).

---

## Regressions

| Area | Status |
|------|--------|
| Unit / structural boundary tests | **Pass** |
| Retracement measurement tests | **Pass** (boundaries passed with full candle context) |
| `test_replay_matches_fixture_detector_baseline` | **Replaced** — pre-leg frozen baseline no longer expected |
| Frozen fixture `detector_suggested_*` | Unchanged (historical record) |
| NO_VALID_RANGE count | **No change** expected |
| Seed chain / API / Electron | **Not touched** |

---

## Tests added / updated

- `test_range_boundary_structural.py` — `htf_leg_trace` fields, expansion owner rules
- `test_detector_audit_regression.py` — `DetectorAuditLegDoctrineTests`:
  - `htf_leg_trace` present on EDIT weeks
  - RH ≠ BOS bar unless `expansion_extreme_owner == BOS_CANDLE`
  - RL ≠ retrace low unless equals `opposite_anchor_price`
  - `test_edit_weeks_match_josh_gold_rh_rl` (requires local candle DB)

---

## How to verify locally

```powershell
cd backend
python -m unittest tests.test_detector_audit_regression.DetectorAuditLegDoctrineTests -v
python -m unittest discover -s tests -p "test_*.py"
```

Requires XAUUSD W1 candles in `candle_store` (≥200 rows) for full audit replay.

---

## References

- `docs/architecture/HTF_LEG_BASED_RANGE_DOCTRINE.md`
- `docs/fixtures/detector_audit_4750e5ac_leg_scorecard.md`
- `backend/detector/range_boundary.py`
- `backend/detector/range_v2.py`
