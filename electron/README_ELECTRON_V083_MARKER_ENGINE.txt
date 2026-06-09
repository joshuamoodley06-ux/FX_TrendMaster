Electron v083 Marker Engine

- Electron only; backend untouched.
- Click Candle mode now captures nearest high/low anchor price.
- Mark tab buttons commit deterministic structural markers using symbol/timeframe/candle-index/event-type IDs.
- Re-marking the same event on the same candle updates/replaces instead of duplicating.
- Selected candle marker persists visually while panning/zooming/replaying.
- Existing map events remain plotted through replay up to the replay cursor.

Workflow: turn on Candle Replay, choose Click Candle, click a candle, then use Mark tab buttons for RH/RL/Ref/BOS/CHoCH/Sweeps.
