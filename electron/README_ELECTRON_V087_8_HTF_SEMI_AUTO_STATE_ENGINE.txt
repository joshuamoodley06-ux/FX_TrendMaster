FX TrendMaster Electron v087.8 - HTF Semi-Auto State Engine

Purpose:
- Keep HTF overview lite.
- User manually inputs only official range H/L and rare judgement.
- Frontend auto-detects simple math: HTF wick BOS, range location %, PDH/PDL sweeps, reclaim attempts, profile suggestions, weekly ref-candle flips.
- Semi-auto suggestions require Accept / Edit / Reject before being stored as event facts.
- Accepted events save primitive + derived event + movement rule + metadata for SQL/AI/ML.
- No automatic fib/range anchor hijacking. Official range anchors still require Set M/W/D High/Low.

Notes:
- Ref High = Old High, Ref Low = Old Low.
- Current High/Low and Range High/Low can be same at range start; point roles split only after BOS/reclaim progression.
- Objectives remain hidden from the overview and are stored/used for stats later.
