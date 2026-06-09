Electron v086.11 - Explicit Fib Anchors

Fixes active fib range precision.

- Fib high/low now listens only to explicit Set M/W/D High/Low commands.
- Weekly/Daily current high/current low events no longer silently override the active fib range.
- Set M/W/D High uses selected candle.high exactly.
- Set M/W/D Low uses selected candle.low exactly.
- To make a current high/low become the active range, queue the relevant Set High/Low button on that candle too.
- Backend untouched.
