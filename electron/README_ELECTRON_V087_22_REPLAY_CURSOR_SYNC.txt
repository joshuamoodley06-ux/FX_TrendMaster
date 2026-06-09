FX TrendMaster Electron v087.22 - Replay Cursor Sync + Chart Scrub

- Adds a master replay cursor timestamp shared across timeframes.
- Rewinding/stepping on W1 now moves the global timestamp; D1/H1/M15 render only candles at or before that time.
- Switching W1/D1 preserves the same replay cursor instead of leaking future lower-timeframe candles.
- Candle Replay inspect mode now supports chart scrub: while Candle Replay is ON and tool mode is Inspect, click a candle to move the replay cursor to that candle.
- Slider/buttons use the effective cursor index for the active timeframe.
- Backend does not need a schema change for this patch.
