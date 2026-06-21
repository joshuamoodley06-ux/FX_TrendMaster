# Leg doctrine scorecard — audit run 4750e5ac

Scores `HTF_LEG_BASED_RANGE_DOCTRINE.md` against 2025 XAUUSD W1 **12 EDIT** corrections.

**No detector code was changed.**

## Doctrine targets (per week)

- **Expansion leg:** `expansion_leg_start` = BOS week (`replay_until − 1 W1 bar`); `expansion_leg_end` = reclaim week (`replay_until`).
- **Expansion extreme:** Josh broken-side final (`suggested_rh` if `broken_boundary=HIGH`, else `suggested_rl`).
- **Opposite anchor:** Josh non-broken-side final (`suggested_rl` / `range_start` week on bullish).
- **Match:** price within ±0.02 of leg target.

## Summary

| Metric | Count | % |
|--------|-------|---|
| Weeks scored | 12 | 100% |
| Josh RH matches leg extreme / opposite anchor | 12 | 100.0% |
| Josh RL matches opposite anchor / leg extreme | 12 | 100.0% |
| **Detector RH matches Josh (leg RH target)** | **2** | **16.7%** |
| **Detector RL matches Josh (leg RL target)** | **2** | **16.7%** |
| **Full range match (detector RH+RL)** | **0** | **0.0%** |
| Expansion extreme time before reclaim | 12 | 100.0% |

## Recommendation

**IMPLEMENT** — Josh corrections are 100% leg-consistent. Detector matches leg targets on 2/12 RH and 2/12 RL weeks. **Implement** leg-based detection; doctrine is sound, implementation is not.

## Per-week scorecard

| replay_until | broken | Josh RH | Josh RL | exp start | exp end | exp extreme | exp time | owner | opposite anchor | opp time | det RH leg? | det RL leg? | RH miss | RL miss |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-01-12 | HIGH | 2726.06 | 2586.4 | 2025-01-05 | 2025-01-12 | 2726.06 (RH) | 2025-01-05 | IMPULSE_SWING | 2586.4 | 2024-12-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-01-19 | HIGH | 2785.89 | 2586.4 | 2025-01-12 | 2025-01-19 | 2785.89 (RH) | 2025-01-12 | IMPULSE_SWING | 2586.4 | 2024-12-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-02-02 | HIGH | 2956.15 | 2772.07 | 2025-01-26 | 2025-02-02 | 2956.15 (RH) | 2025-01-26 | IMPULSE_SWING | 2772.07 | 2024-12-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-06-08 | HIGH | 3499.88 | 2956.66 | 2025-06-01 | 2025-06-08 | 3499.88 (RH) | 2025-06-01 | IMPULSE_SWING | 2956.66 | 2025-05-11 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-06-15 | HIGH | 3430.86 | 3120.81 | 2025-06-08 | 2025-06-15 | 3430.86 (RH) | 2025-06-08 | IMPULSE_SWING | 3120.81 | 2025-05-11 | **no** | yes | detector_RH=BOS_bar_not_expansion_extreme | — |
| 2025-06-22 | HIGH | 3451.19 | 3120.81 | 2025-06-15 | 2025-06-22 | 3451.19 (RH) | 2025-06-15 | BOS_CANDLE | 3120.81 | 2025-06-08 | yes | **no** | — | detector_RL=retrace_low_not_opposite_anchor |
| 2025-06-29 | LOW | 3451.19 | 3248.86 | 2025-06-22 | 2025-06-29 | 3248.86 (RL) | 2025-06-22 | IMPULSE_SWING | 3451.19 | 2025-06-15 | yes | **no** | — | detector_RL_mismatch |
| 2025-07-06 | LOW | 3453.82 | 3248.86 | 2025-06-29 | 2025-07-06 | 3248.86 (RL) | 2025-06-29 | BOS_CANDLE | 3453.82 | 2025-06-15 | **no** | yes | detector_RH_below_leg_extreme | — |
| 2025-07-13 | HIGH | 3499.88 | 3120.81 | 2025-07-06 | 2025-07-13 | 3499.88 (RH) | 2025-07-06 | IMPULSE_SWING | 3120.81 | 2025-06-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-07-20 | HIGH | 4381.25 | 3886.56 | 2025-07-13 | 2025-07-20 | 4381.25 (RH) | 2025-07-13 | IMPULSE_SWING | 3886.56 | 2025-06-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-07-27 | HIGH | 4545.98 | 3886.56 | 2025-07-20 | 2025-07-27 | 4545.98 (RH) | 2025-07-20 | IMPULSE_SWING | 3886.56 | 2025-06-29 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |
| 2025-08-10 | HIGH | 5598.08 | 4274.6 | 2025-08-03 | 2025-08-10 | 5598.08 (RH) | 2025-08-03 | IMPULSE_SWING | 4274.6 | 2025-07-27 | **no** | **no** | detector_RH=BOS_bar_not_expansion_extreme | detector_RL=retrace_low_not_opposite_anchor |

## Doctrine failures (detector vs leg targets)

**12 / 12** weeks where detector does not match leg targets (Josh gold).

- **2025-01-12** (WRONG_RH) — RH: **2697.75** vs leg 2726.06 (detector_RH=BOS_bar_not_expansion_extreme); RL: **2596** vs leg 2586.4 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-01-19** (WRONG_RH) — RH: **2724.66** vs leg 2785.89 (detector_RH=BOS_bar_not_expansion_extreme); RL: **2596** vs leg 2586.4 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-02-02** (WRONG_RH) — RH: **2817.05** vs leg 2956.15 (detector_RH=BOS_bar_not_expansion_extreme); RL: **2596** vs leg 2772.07 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-06-08** (WRONG_RH) — RH: **3403.23** vs leg 3499.88 (detector_RH=BOS_bar_not_expansion_extreme); RL: **3120.81** vs leg 2956.66 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-06-15** (WRONG_RH) — RH: **3446.72** vs leg 3430.86 (detector_RH=BOS_bar_not_expansion_extreme); RL: match (—)
- **2025-06-22** (WRONG_RL) — RH: match (—); RL: **3293.35** vs leg 3120.81 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-06-29** (WRONG_RL) — RH: match (—); RL: **3256.12** vs leg 3248.86 (detector_RL_mismatch)
- **2025-07-06** (WRONG_RH) — RH: **3451.19** vs leg 3453.82 (detector_RH_below_leg_extreme); RL: match (—)
- **2025-07-13** (WRONG_RH) — RH: **3368.63** vs leg 3499.88 (detector_RH=BOS_bar_not_expansion_extreme); RL: **3248.86** vs leg 3120.81 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-07-20** (WRONG_RH) — RH: **3377.43** vs leg 4381.25 (detector_RH=BOS_bar_not_expansion_extreme); RL: **3248.86** vs leg 3886.56 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-07-27** (WRONG_RH) — RH: **3438.81** vs leg 4545.98 (detector_RH=BOS_bar_not_expansion_extreme); RL: **3248.86** vs leg 3886.56 (detector_RL=retrace_low_not_opposite_anchor)
- **2025-08-10** (WRONG_RH) — RH: **3407.59** vs leg 5598.08 (detector_RH=BOS_bar_not_expansion_extreme); RL: **3268.06** vs leg 4274.6 (detector_RL=retrace_low_not_opposite_anchor)

## Josh vs leg doctrine (sanity)

Josh finals **define** leg targets in this scorecard. All 12/12 weeks are internally leg-consistent (expansion extreme on broken side, opposite anchor on `range_start` week).

The gap is **detector vs leg**, not Josh vs leg.

## References

- `docs/architecture/HTF_LEG_BASED_RANGE_DOCTRINE.md`
- `docs/fixtures/detector_audit_4750e5ac.json`
