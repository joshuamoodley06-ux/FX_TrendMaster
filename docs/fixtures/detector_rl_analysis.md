# Detector RL analysis — audit run 4750e5ac

XAUUSD W1 weekly range audit (14 reviewed weeks). **No code changes** — fixture-only report.

## Summary

- **RL failure count:** 14 / 14 weeks show RL tied to retracement logic
- **Explicit WRONG_RL edits:** 2

## Per-week table

| week | detector_rl | josh_rl | retracement_price | impulse_low | impulse_high | failure_kind | audit_reason |
|------|-------------|---------|-------------------|-------------|--------------|--------------|--------------|
| 2025-01-12 | 2596 | 2586.4 | 2656.66 | 2596 | 2697.75 | equals_retracement_impulse_low | WRONG_RH |
| 2025-01-19 | 2596 | 2586.4 | 2689.34 | 2596 | 2724.66 | equals_retracement_impulse_low | WRONG_RH |
| 2025-02-02 | 2596 | 2772.07 | 2772.07 | 2596 | 2817.05 | equals_retracement_impulse_low | WRONG_RH |
| 2025-06-08 | 3120.81 | 2956.66 | 3293.35 | 3120.81 | 3403.23 | equals_retracement_impulse_low | WRONG_RH |
| 2025-06-15 | 3120.81 | 3120.81 | 3340.34 | 3120.81 | 3446.72 | equals_retracement_impulse_low | WRONG_RH |
| 2025-06-22 | 3293.35 | 3120.81 | 3256.12 | 3293.35 | 3451.19 | equals_retracement_impulse_low | WRONG_RL |
| 2025-06-29 | 3256.12 | 3248.86 | 3365.65 | 3256.12 | 3451.19 | equals_retracement_impulse_low | WRONG_RL |
| 2025-07-06 | 3248.86 | 3248.86 | 3368.63 | 3248.86 | 3451.19 | equals_retracement_impulse_low | WRONG_RH |
| 2025-07-13 | 3248.86 | 3120.81 | 3309.68 | 3248.86 | 3368.63 | equals_retracement_impulse_low | WRONG_RH |
| 2025-07-20 | 3248.86 | 3886.56 | 3324.91 | 3248.86 | 3377.43 | equals_retracement_impulse_low | WRONG_RH |
| 2025-07-27 | 3248.86 | 3886.56 | 3268.06 | 3248.86 | 3438.81 | equals_retracement_impulse_low | WRONG_RH |
| 2025-08-10 | 3268.06 | 4274.6 | 3329.75 | 3268.06 | 3407.59 | equals_retracement_impulse_low | WRONG_RH |
| 2025-12-07 | 3997.99 | 3997.99 | 4169.92 | 3997.99 | 4264.46 | equals_retracement_impulse_low | WRONG_RH |
| 2025-12-28 | 3997.99 | 3997.99 | 4274.6 | 3997.99 | 4549.7 | equals_retracement_impulse_low | WRONG_RH |

## Affected weeks (RL ≡ retracement-derived)

- **2025-01-12** — `equals_retracement_impulse_low`; detector RL 2596, Josh RL 2586.4, retracement 2656.66; reason: Measured lowest low after BOS through reclaim
- **2025-01-19** — `equals_retracement_impulse_low`; detector RL 2596, Josh RL 2586.4, retracement 2689.34; reason: Measured lowest low after BOS through reclaim
- **2025-02-02** — `equals_retracement_impulse_low`; detector RL 2596, Josh RL 2772.07, retracement 2772.07; reason: Measured lowest low after BOS through reclaim
- **2025-06-08** — `equals_retracement_impulse_low`; detector RL 3120.81, Josh RL 2956.66, retracement 3293.35; reason: Measured lowest low after BOS through reclaim
- **2025-06-15** — `equals_retracement_impulse_low`; detector RL 3120.81, Josh RL 3120.81, retracement 3340.34; reason: Measured lowest low after BOS through reclaim
- **2025-06-22** — `equals_retracement_impulse_low`; detector RL 3293.35, Josh RL 3120.81, retracement 3256.12; reason: Measured lowest low after BOS through reclaim
- **2025-06-29** — `equals_retracement_impulse_low`; detector RL 3256.12, Josh RL 3248.86, retracement 3365.65; reason: Measured highest high after BOS through reclaim
- **2025-07-06** — `equals_retracement_impulse_low`; detector RL 3248.86, Josh RL 3248.86, retracement 3368.63; reason: Measured highest high after BOS through reclaim
- **2025-07-13** — `equals_retracement_impulse_low`; detector RL 3248.86, Josh RL 3120.81, retracement 3309.68; reason: Measured lowest low after BOS through reclaim
- **2025-07-20** — `equals_retracement_impulse_low`; detector RL 3248.86, Josh RL 3886.56, retracement 3324.91; reason: Measured lowest low after BOS through reclaim
- **2025-07-27** — `equals_retracement_impulse_low`; detector RL 3248.86, Josh RL 3886.56, retracement 3268.06; reason: Measured lowest low after BOS through reclaim
- **2025-08-10** — `equals_retracement_impulse_low`; detector RL 3268.06, Josh RL 4274.6, retracement 3329.75; reason: Measured lowest low after BOS through reclaim
- **2025-12-07** — `equals_retracement_impulse_low`; detector RL 3997.99, Josh RL 3997.99, retracement 4169.92; reason: Measured lowest low after BOS through reclaim
- **2025-12-28** — `equals_retracement_impulse_low`; detector RL 3997.99, Josh RL 3997.99, retracement 4274.6; reason: Measured lowest low after BOS through reclaim

## Strongest RL signal

In **12/12 EDIT weeks** with `detector_suggested_rl`, RL equals `retracement_impulse_low` (the post-BOS retrace measurement anchor), not the structural swing low Josh selected. Weeks **2025-06-22** and **2025-06-29** were explicitly corrected for WRONG_RL.
