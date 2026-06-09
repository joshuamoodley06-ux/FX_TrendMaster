v087.13 HTF Sequence Authority Patch

- Decouples ref candle zone-cycle detection from structural BOS/reclaim/rebase chains.
- Structural reclaims now require accepted HTF BOS in the same strict range fingerprint.
- Structural rebase now requires accepted BOS + accepted reclaim + accepted current high/low.
- Strict HTF ledger lookup ignores legacy/manual ghosts without range metadata for structural chains.
- Weekly/Macro ref candle detection now uses a persistent zone-cycle watch: premium/discount entry starts the watch; the actual flipped candle confirms the ref when it breaches the previous/pre-ref candle side.
