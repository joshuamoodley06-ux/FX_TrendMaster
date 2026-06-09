Electron v082 - Replay No Fit Reset

Root cause:
- The candle replay step handler still called setJumpDate(...) and setFitToken(...).
- fitToken is intentionally wired to reset/recenter the chart.
- So every replay step behaved like Fit All / Go Date, making the chart zoom out/reset.

Fix:
- Removed setJumpDate(...) and setFitToken(...) from setCandleReplayFrame(...).
- Replay cursor movement now updates only replay state + selected candle + message.
- Chart camera remains user-owned. Use Latest/Fit All/Go Date manually when you actually want recentering.

Backend untouched.
