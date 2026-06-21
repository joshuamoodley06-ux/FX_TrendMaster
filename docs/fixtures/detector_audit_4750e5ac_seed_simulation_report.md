# Seed simulation report — audit run 4750e5ac

Phase 3 **pre-check** only. Compares historical-walk seeds (`previous_range_candidate`) vs simulated seeds from prior week `final_snapshot_json` (Josh-reviewed RH/RL).

**No detector code was changed.**

## Per-week comparison

| week | old_seed_source | old_seed_rh | old_seed_rl | sim_seed_source | sim_seed_rh | sim_seed_rl | josh_rh | josh_rl | old_ΔRH | old_ΔRL | sim_ΔRH | sim_ΔRL | improved? |
|------|-----------------|-------------|-------------|-----------------|-------------|-------------|---------|---------|---------|---------|---------|---------|-----------|
| 2025-01-12 | bootstrap_candidate | 2685.54 | 2471.83 | — | None | None | 2726.06 | 2586.4 | 40.52 | 114.57 | — | — | unchanged |
| 2025-01-19 | previous_range_candidate | 2697.75 | 2596 | audit_correction_final_snapshot | 2726.06 | 2586.4 | 2785.89 | 2586.4 | 88.14 | 9.6 | 59.83 | 0.0 | improved |
| 2025-02-02 | bootstrap_candidate | 2790.01 | 2602.55 | audit_correction_final_snapshot | 2785.89 | 2586.4 | 2956.15 | 2772.07 | 166.14 | 169.52 | 170.26 | 185.67 | worsened |
| 2025-06-08 | bootstrap_candidate | 3365.89 | 3120.81 | audit_correction_final_snapshot | 2956.15 | 2772.07 | 3499.88 | 2956.66 | 133.99 | 164.15 | 543.73 | 184.59 | worsened |
| 2025-06-15 | previous_range_candidate | 3403.23 | 3120.81 | audit_correction_final_snapshot | 3499.88 | 2956.66 | 3430.86 | 3120.81 | 27.63 | 0.0 | 69.02 | 164.15 | worsened |
| 2025-06-22 | previous_range_candidate | 3446.72 | 3120.81 | audit_correction_final_snapshot | 3430.86 | 3120.81 | 3451.19 | 3120.81 | 4.47 | 0.0 | 20.33 | 0.0 | worsened |
| 2025-06-29 | previous_range_candidate | 3451.19 | 3293.35 | audit_correction_final_snapshot | 3451.19 | 3120.81 | 3451.19 | 3248.86 | 0.0 | 44.49 | 0.0 | 128.05 | worsened |
| 2025-07-06 | previous_range_candidate | 3451.19 | 3256.12 | audit_correction_final_snapshot | 3451.19 | 3248.86 | 3453.82 | 3248.86 | 2.63 | 7.26 | 2.63 | 0.0 | improved |
| 2025-07-13 | bootstrap_candidate | 3365.89 | 3120.81 | audit_correction_final_snapshot | 3453.82 | 3248.86 | 3499.88 | 3120.81 | 133.99 | 0.0 | 46.06 | 128.05 | worsened |
| 2025-07-20 | previous_range_candidate | 3368.63 | 3248.86 | audit_correction_final_snapshot | 3499.88 | 3120.81 | 4381.25 | 3886.56 | 1012.62 | 637.7 | 881.37 | 765.75 | improved |
| 2025-07-27 | previous_range_candidate | 3377.43 | 3248.86 | audit_correction_final_snapshot | 4381.25 | 3886.56 | 4545.98 | 3886.56 | 1168.55 | 637.7 | 164.73 | 0.0 | improved |
| 2025-08-10 | bootstrap_candidate | 3365.89 | 3120.81 | audit_correction_final_snapshot | 4545.98 | 3886.56 | 5598.08 | 4274.6 | 2232.19 | 1153.79 | 1052.1 | 388.04 | improved |
| 2025-12-07 | bootstrap_candidate | 4244.93 | 3886.56 | audit_correction_final_snapshot | 5598.08 | 4274.6 | 4264.46 | 3997.99 | 19.53 | 111.43 | 1333.62 | 276.61 | worsened |
| 2025-12-28 | bootstrap_candidate | 4381.25 | 3311.42 | — | None | None | 4549.7 | 3997.99 | 168.45 | 686.57 | — | — | unchanged |

## Summary

- **Total weeks compared:** 14
- **Improved:** 5
- **Unchanged:** 2
- **Worsened:** 7
- **Avg RH seed |Δ| (old → sim):** 371.35 → 361.97
- **Avg RL seed |Δ| (old → sim):** 266.91 → 185.08
- **Jul–Aug improved / total:** 4 / 5 (worsened: 1)

## Recommendation

**DO NOT IMPLEMENT PHASE 3 YET**

Improvement = combined |seed−Josh| distance (RH+RL) smaller than old detector-rolled seed.
Week 1 has no prior audited correction → simulated seed N/A (unchanged).
