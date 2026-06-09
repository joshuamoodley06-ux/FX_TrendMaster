# Electron v087.11 - HTF State Guard Hard Lock

Purpose:
- Stop duplicate semi-auto HTF suggestions after a transition is accepted.
- Add lifecycle lock keys for accepted suggestions using timeframe + range fingerprint + movement_rule + side.
- Harden accepted event memory hydration by reading movement_rule / derived_event_code from both top-level event fields and meta_json.
- Keep the HTF engine stateful enough to avoid repeating old reclaim/ref candle suggestions while replay continues through the same zone.

Key fixes:
- Accepted Old Low / Ref Low Reclaim should not prompt again for the same range cycle.
- Accepted Old High / Ref High Reclaim should not prompt again for the same range cycle.
- Accepted Bearish/Bullish HTF Ref Candle should not repeatedly prompt again in the same range/zone lifecycle.
- Reclaim still requires prior BOS state; spatial overlap alone should not create the suggestion.

Backend:
- Use existing backend v149 HTF Semi-Auto State Storage.
