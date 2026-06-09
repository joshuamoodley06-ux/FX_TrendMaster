v086.10 Fib Low Anchor Fix

Fixes the case where Set W Low / Set M Low / Set D Low markers plotted correctly but the active fib range could keep an older backend low. Range-anchor saves now directly update the local range memory for the active timeframe after saving the marker bundle, so the fib engine receives the selected candle high/low immediately.

Backend untouched.
