# Detector RH analysis — audit run 4750e5ac

Grouped by `boundary_selection_reason`. **No code changes** — fixture-only report.

## Per-week RH delta

| week | detector_rh | josh_rh | difference | rh == impulse_high | scan_chain | seed_rh | audit_reason |
|------|-------------|---------|------------|--------------------|------------|---------|--------------|
| 2025-01-12 | 2697.75 | 2726.06 | 28.31 | True | 0 | 2685.54 | WRONG_RH |
| 2025-01-19 | 2724.66 | 2785.89 | 61.23 | True | 1 | 2697.75 | WRONG_RH |
| 2025-02-02 | 2817.05 | 2956.15 | 139.1 | True | 2 | 2790.01 | WRONG_RH |
| 2025-06-08 | 3403.23 | 3499.88 | 96.65 | True | 3 | 3365.89 | WRONG_RH |
| 2025-06-15 | 3446.72 | 3430.86 | -15.86 | True | 4 | 3403.23 | WRONG_RH |
| 2025-06-22 | 3451.19 | 3451.19 | 0.0 | True | 5 | 3446.72 | WRONG_RL |
| 2025-06-29 | 3451.19 | 3451.19 | 0.0 | True | 6 | 3451.19 | WRONG_RL |
| 2025-07-06 | 3451.19 | 3453.82 | 2.63 | True | 7 | 3451.19 | WRONG_RH |
| 2025-07-13 | 3368.63 | 3499.88 | 131.25 | True | 8 | 3365.89 | WRONG_RH |
| 2025-07-20 | 3377.43 | 4381.25 | 1003.82 | True | 9 | 3368.63 | WRONG_RH |
| 2025-07-27 | 3438.81 | 4545.98 | 1107.17 | True | 10 | 3377.43 | WRONG_RH |
| 2025-08-10 | 3407.59 | 5598.08 | 2190.49 | True | 11 | 3365.89 | WRONG_RH |
| 2025-12-07 | 4264.46 | 4264.46 | 0.0 | True | 12 | 4244.93 | WRONG_RH |
| 2025-12-28 | 4549.7 | 4549.7 | 0.0 | True | 13 | 4381.25 | WRONG_RH |

## Grouped by boundary_selection_reason

### `LAST_OPPOSITE_SWING_BEFORE_BOS` (14 weeks, 12 WRONG_RH)

- **2025-01-12** — detector 2697.75, Josh 2726.06, Δ 28.31; seed 2685.54/2471.83; chain index 0
- **2025-01-19** — detector 2724.66, Josh 2785.89, Δ 61.23; seed 2697.75/2596; chain index 1
- **2025-02-02** — detector 2817.05, Josh 2956.15, Δ 139.1; seed 2790.01/2602.55; chain index 2
- **2025-06-08** — detector 3403.23, Josh 3499.88, Δ 96.65; seed 3365.89/3120.81; chain index 3
- **2025-06-15** — detector 3446.72, Josh 3430.86, Δ -15.86; seed 3403.23/3120.81; chain index 4
- **2025-06-22** — detector 3451.19, Josh 3451.19, Δ 0.0; seed 3446.72/3120.81; chain index 5
- **2025-06-29** — detector 3451.19, Josh 3451.19, Δ 0.0; seed 3451.19/3293.35; chain index 6
- **2025-07-06** — detector 3451.19, Josh 3453.82, Δ 2.63; seed 3451.19/3256.12; chain index 7
- **2025-07-13** — detector 3368.63, Josh 3499.88, Δ 131.25; seed 3365.89/3120.81; chain index 8
- **2025-07-20** — detector 3377.43, Josh 4381.25, Δ 1003.82; seed 3368.63/3248.86; chain index 9
- **2025-07-27** — detector 3438.81, Josh 4545.98, Δ 1107.17; seed 3377.43/3248.86; chain index 10
- **2025-08-10** — detector 3407.59, Josh 5598.08, Δ 2190.49; seed 3365.89/3120.81; chain index 11
- **2025-12-07** — detector 4264.46, Josh 4264.46, Δ 0.0; seed 4244.93/3886.56; chain index 12
- **2025-12-28** — detector 4549.7, Josh 4549.7, Δ 0.0; seed 4381.25/3311.42; chain index 13

## Error pattern hypotheses (data only)

1. **BOS high selection** — detector RH equals `retracement_impulse_high` (BOS bar high) in **14/14** weeks.
2. **Swing selection** — all weeks use `LAST_OPPOSITE_SWING_BEFORE_BOS` for the opposite boundary; RL side pinned to stale pre-BOS swing or retrace impulse low.
3. **Stale seed influence** — `seed_rh`/`seed_rl` roll from prior detector output (`scan_chain_index` 0→13); Jul–Aug weeks show largest RH deltas as chain compounds.
4. **Chain compounding** — weeks 2025-07-20 through 2025-08-10: Josh RH exceeds detector by 1000–2190 pts while seeds still reflect earlier wrong ranges.
