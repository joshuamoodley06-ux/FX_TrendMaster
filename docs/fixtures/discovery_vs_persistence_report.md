# Discovery vs persistence report

Split implementation: `PROMOTED_RANGE` supplies persistence context; week-local BOS→reclaim discovery emits when promoted lifecycle is stale.

## Summary

- Baseline audit weeks with candidates: **14**
- Weeks emitting RANGE after split: **7**
- Recovered from prior leg+reviewed-truth loss set: **3** / 10
- Still missing vs baseline: **7**
- Stale promoted cycles blocked from direct emit: **yes**
- Jun–Jul stale cluster local recovery: **3** / 5

### Recovered weeks

- `2025-06-08` — `LOCAL_ACTIVE_REPLAY` (local_discovery=RANGE_CANDIDATE)
- `2025-06-15` — `LOCAL_ACTIVE_REPLAY` (local_discovery=RANGE_CANDIDATE)
- `2025-07-13` — `LOCAL_ACTIVE_REPLAY` (local_discovery=RANGE_CANDIDATE)

### Still missing weeks

- `2025-01-19` — BOS detected; reclaim not yet confirmed
- `2025-06-29` — Promoted context reclaim stale; no bootstrap seed completed a fresh BOS→reclaim cycle near the active week
- `2025-07-06` — Promoted context reclaim stale; no bootstrap seed completed a fresh BOS→reclaim cycle near the active week
- `2025-07-20` — Reclaim confirmed; no leg boundary candidates
- `2025-07-27` — BOS detected; reclaim not yet confirmed
- `2025-08-10` — BOS detected; reclaim not yet confirmed
- `2025-12-07` — Reclaim confirmed; no leg boundary candidates

## Stale-week detail (Jun–Jul cluster)

| Week | Emitted | discovery_source | stale_rejected | local_result |
|------|---------|------------------|----------------|--------------|
| 2025-06-08 | yes | LOCAL_ACTIVE_REPLAY | True | RANGE_CANDIDATE |
| 2025-06-15 | yes | LOCAL_ACTIVE_REPLAY | True | RANGE_CANDIDATE |
| 2025-06-29 | no | — | True | no bootstrap seed completed a fresh BOS→reclaim cycle near the active week |
| 2025-07-06 | no | — | True | no bootstrap seed completed a fresh BOS→reclaim cycle near the active week |
| 2025-07-13 | yes | LOCAL_ACTIVE_REPLAY | True | RANGE_CANDIDATE |

## Discovery source counts

- `LOCAL_ACTIVE_REPLAY`: 3
- `PROMOTED_SEED_LIFECYCLE`: 2
- `—`: 2
