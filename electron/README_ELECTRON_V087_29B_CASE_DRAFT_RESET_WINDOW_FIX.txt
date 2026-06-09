# Electron v087.29b - Case Draft Reset + Window Anchor Fix

This patch fixes stale case/range windows after cancelling or clearing an old case.

## Fixes
- Bumps localStorage keys for range anchors/windows and active case so old v087.29 local state does not keep anchoring boxes from 2019.
- `Clear Active` now clears case high/low, anchor times, range_start/range_end, current TF range, and current TF window.
- Capturing Case High/Low now rebuilds the visual window only from the newly selected case anchor candle times.
- No more merging old `rangeWindowByTf` values into fresh 2026 case selections.

## Expected behaviour
When a fresh 2026 high/low is selected, the case box starts between those selected anchor candle times, not from an old 2019 case window.

Backend v159d stays unchanged.
