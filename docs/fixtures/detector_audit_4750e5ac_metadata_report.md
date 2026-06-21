# Detector audit metadata report — run 4750e5ac

Phase 2: market-time keys for BOS/reclaim/boundaries. `bos_candle_index` / `reclaim_candle_index` are replay-window hints only (`candle_index_scope=replay_window`).

## Per-week metadata

| week | replay_until | old_bos_idx | bos_time | old_reclaim_idx | reclaim_time | rh_boundary_time | rl_boundary_time | idx_dup_103_104 | plausible |
|------|--------------|-------------|----------|-----------------|--------------|------------------|------------------|-----------------|-----------|
| 2025-01-12 | 2025-01-12 | 103 | — | 104 | — | — | — | True | — |
| 2025-01-19 | 2025-01-19 | 103 | — | 104 | — | — | — | True | — |
| 2025-02-02 | 2025-02-02 | 103 | — | 104 | — | — | — | True | — |
| 2025-06-08 | 2025-06-08 | 103 | — | 104 | — | — | — | True | — |
| 2025-06-15 | 2025-06-15 | 103 | — | 104 | — | — | — | True | — |
| 2025-06-22 | 2025-06-22 | 103 | — | 104 | — | — | — | True | — |
| 2025-06-29 | 2025-06-29 | 103 | — | 104 | — | — | — | True | — |
| 2025-07-06 | 2025-07-06 | 103 | — | 104 | — | — | — | True | — |
| 2025-07-13 | 2025-07-13 | 103 | — | 104 | — | — | — | True | — |
| 2025-07-20 | 2025-07-20 | 103 | — | 104 | — | — | — | True | — |
| 2025-07-27 | 2025-07-27 | 103 | — | 104 | — | — | — | True | — |
| 2025-08-10 | 2025-08-10 | 103 | — | 104 | — | — | — | True | — |
| 2025-12-07 | 2025-12-07 | 103 | — | 104 | — | — | — | True | — |
| 2025-12-28 | 2025-12-28 | 103 | — | 104 | — | — | — | True | — |

## Summary

- **Audited weeks:** 14
- **Live replay available:** False
- **Rows with valid `bos_time_ms` (live):** 0
- **Rows with valid `reclaim_time_ms` (live):** 0
- **Rows with valid `rh_boundary_time_ms` (live):** 0
- **Rows with valid `rl_boundary_time_ms` (live):** 0
- **Fixture rows with duplicated debug indices 103/104:** 14

After Phase 2, new suggestions carry `bos_time_ms` / `reclaim_time_ms` / `rh_boundary_time_ms` / `rl_boundary_time_ms`. Repeated `103`/`104` in the **frozen fixture** is legacy replay-window noise; live detector output uses market-time keys for audit joins.
