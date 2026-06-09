FX TrendMaster Electron v080 - Replay View Preservation + Seed Guard

Electron-only patch. Backend remains untouched.

Changes:
- Candle replay no longer passes a shrinking candle array into the chart.
- Chart uses the full candle universe for its X-scale and clips rendering using replayCutTime.
- Stepping replay forward/back preserves pan/zoom/Y-drag viewport instead of resetting the map view.
- Existing backend map events and seed idea anchors are plotted only up to the replay cursor.
- Seed idea anchors are rendered as yellow seed markers and are read-only in drag mode.
- Client-side duplicate seed guard blocks saving the same candle + Weekly/Daily H/L anchor set twice.

Test:
1. npm run build
2. npm run dev
3. Enable Candle Replay.
4. Pan/zoom/drag Y-axis.
5. Step forward/backward. View should not reset.
6. Save a seed, then attempt the same seed again. Duplicate should be blocked.
