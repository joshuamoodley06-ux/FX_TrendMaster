# v087.12 HTF Stateful Reclaim + Ref Polarity Gates

Fixes false auto events caused by raw geometry parsing.

- Reclaim suggestions require accepted prior BOS state.
- Rebase suggestions require accepted reclaim AND accepted current high/low.
- Bearish ref candle suggestions require active candle still at high-side zone (75%+ / external high).
- Bullish ref candle suggestions require active candle still at low-side zone (25%- / external low).
- Old range remains preserved for retracement/profile stats.
