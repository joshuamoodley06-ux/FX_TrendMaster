# Electron v078 - Auto-scale Breathing Fix

Backend untouched.

Changes:
- D3 auto-scale now uses the most recent visible candle cluster instead of being pinned by old giant candles in the viewport.
- Range scale still respects the full selected range.
- Added a wider 18% vertical breathing buffer so candles stop scraping the canvas floor/ceiling.

Test:
1. npm run build
2. npm run dev
3. Open Map Studio
4. Enable Candle Replay
5. Pan/step through replay and confirm recent candles stay readable instead of glued to the bottom.
