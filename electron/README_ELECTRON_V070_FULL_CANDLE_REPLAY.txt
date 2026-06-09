Electron v070 - Full candle-by-candle Map Studio replay

Adds to Map Studio:
- Candle Replay toggle in toolbar
- Previous / Play / Next / Slider candle controls
- Replay speed control
- Chart now rewinds the actual candle stream by slicing visible candles up to the replay cursor
- Selected candle can be used to capture:
  - Weekly High
  - Weekly Low
  - Daily High
  - Daily Low
- Seed Idea Builder panel
- Save Seed Idea button posts to /api/v1/mos/seed-idea
- Recent seed ideas list

Important:
- This is candle replay, not only MOS ledger replay.
- MOS ledger replay still exists separately.
- Build MOS State still saves official MOS state frames.
- Save Seed Idea saves calibration drafts for later review.
