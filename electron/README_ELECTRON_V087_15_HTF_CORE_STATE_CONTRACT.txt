FX TrendMaster Electron v087.15 - HTF Core State Contract

Purpose:
This patch stops expanding features and tightens the HTF engine to the sane minimum contract:
Range exists -> BOS can occur -> reclaim can occur only after accepted BOS -> rebase only after accepted BOS + reclaim + current H/L.
Ref candles remain a separate zone-reversal pipeline and do not imply BOS/reclaim/rebase.

Key changes:
1. New local lock namespace v087.15 to avoid polluted test locks from older patches.
2. Living Range State now reports legal state:
   ACTIVE_RANGE, BREACHED_UP, BREACHED_DOWN, RECLAIMED.
3. Mid-range after Set H/L should show no action suggestions except next-watch guidance.
4. BOS Up/Down remains pure HTF wick break:
   high > range high = BOS Up, low < range low = BOS Down.
5. Reclaim now requires accepted BOS first AND candle close back inside old boundary:
   BOS Up -> close <= old high = Old High / Ref High Reclaim.
   BOS Down -> close >= old low = Old Low / Ref Low Reclaim.
6. Rebase remains disabled until accepted BOS + accepted reclaim + confirmed current H/L.
7. Weekly/Macro ref watch lookback extended so premium/discount watch cycles are less likely to be missed.
8. Ref candle remains separate from structure:
   premium/external watch -> flipped bearish candle breaking pre-ref low = bearish ref candle.
   discount/external watch -> flipped bullish candle breaking pre-ref high = bullish ref candle.

Backend:
No backend update required. Continue using backend v149.
