# Electron v086.12 — Anchor Side Preserve Fix

Fixes fib range anchors resetting after saving the opposite side.

Core rule:
- Set W Low updates only the weekly low from the selected candle.low.
- Set W High updates only the weekly high from the selected candle.high.
- Same for Macro and Daily.
- Saving a high no longer re-syncs the low from old backend/legacy events.
- Saving a low no longer re-syncs the high from old backend/legacy events.
- Range persistence now prefers explicit SET_* anchors over old RANGE_HIGH/RANGE_LOW markers.

Backend untouched.
Build tested successfully.
