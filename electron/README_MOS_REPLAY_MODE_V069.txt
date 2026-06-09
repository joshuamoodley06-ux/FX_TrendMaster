FX TrendMaster Electron v069 - MOS Replay Mode Patch

What changed:
- Added visible Replay Mode controls directly to Map Studio toolbar.
- Added Story ID input, Load Replay, Seed Case 03, Prev, Play/Pause, Next, and slider controls.
- Selecting a replay frame now applies it to the Market GPS panel and MOS editor fields.
- Added replay frame banner above the candle map showing phase, lifecycle, zone, objective, profile, trigger, and lookahead result.
- Added clickable playback ledger rows in the side panel.

How to test:
1. Start backend.
2. Open Electron > Map Studio.
3. Click Seed Case 03.
4. Replay Mode should turn useful instead of hiding in a corner.
5. Use Prev / Play / Next / slider to scrub Story ID 3 frames.

Notes:
- This is replay of MOS state frames, not candle-by-candle chart simulation yet.
- Canvas repaint/price marker overlay can be added next if needed.
