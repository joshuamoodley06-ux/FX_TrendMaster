Electron v086.6 - Weekly/Daily Range Anchor Sync

Fixes:
- Weekly event markers like WEEKLY_EXTERNAL_HIGH / WEEKLY_EXTERNAL_LOW now update the active range high/low.
- Weekly ref/current/extreme high/low markers can also drive the active fib range.
- Daily external/extreme/PDH/PDL reference anchors can update the active daily range.
- Macro external/extreme anchors can update macro range when used on MN1.
- Fibs/range box should move to the latest valid high/low anchor for the selected timeframe.
- Range save payload now uses the new taxonomy anchors, not only the old RANGE_HIGH/RANGE_LOW event names.
- Backend unchanged.

Test:
1. Open W1.
2. Mark WEEKLY_EXTERNAL_HIGH on the current WEH candle.
3. Mark WEEKLY_EXTERNAL_LOW on the current WEL candle.
4. Fibs should move to those anchors.
5. Toggle Range Scale if you want the chart Y scale to frame the whole active range.
