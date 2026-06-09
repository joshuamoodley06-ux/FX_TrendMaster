FX TrendMaster Electron v087.10 - HTF State Memory + Range Rebase

Patch goals:
- Stop repeated semi-auto suggestions after a transition has already been accepted.
- Lock accepted reclaim/ref-candle state for the active range cycle.
- Add range rebase candidates after BOS + reclaim while preserving the old range for retracement/profile statistics.

Key behaviour:
- Accepted OLD_HIGH/OLD_LOW reclaim suggestions are no longer suggested again for the same active range.
- Accepted bearish/bullish HTF ref candle suggestions are locked for the same zone cycle.
- A new RANGE_REBASE candidate appears after BOS + reclaim conditions.
- Accepting RANGE_REBASE resets the visible active fib to the new high/low pair.
- The previous/old range is stored in the HTF state snapshot as measurement_range_preserved for retracement depth, profile classifier, and future SQL/AI stats.

Important:
Official Set High/Low anchors remain manual. Rebase only occurs after the user accepts the semi-auto rebase suggestion.
