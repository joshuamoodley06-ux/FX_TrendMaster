Electron v086 - Mark Save + Replay Dock Fix

Backend untouched.

Changes:
- Mark tab now queues selected event buttons instead of instantly saving each click.
- Added pinned Queued / Save to Narrative / Clear Queue footer.
- Selected event buttons highlight in gold while queued.
- Save to Narrative commits all queued events for the selected candle.
- Clear / Close clears queued selections safely.
- Replay dock layout tightened and chart min-height relaxed so the bottom ribbon stays visible.

Run:
npm install   # only if dependencies are missing
npm run build
npm run dev
