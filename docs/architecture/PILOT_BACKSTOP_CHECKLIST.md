# Pilot Backstop Checklist

**Status:** Mandatory before any Pilot patch  
**Date:** 2026-06-19 (reconciled with control plane)  
**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../project%20rules.md) · [`PROJECT.RULES.md`](../../PROJECT.RULES.md)

**Agent chain (§36):** Librarian → Sync Architect → **Pilot** → QA → Josh. Pilot codes **one subsystem** only after this checklist and [`TASK_TEMPLATE.md`](../agents/TASK_TEMPLATE.md) are complete.

Copy into PR or task note. **Do not start coding until every row has an answer.**

---

## Pre-flight (answer in writing)

| # | Question | Your answer |
|---|----------|-------------|
| 1 | **Which subsystem am I touching?** (see [`SYSTEM_MAP.md`](SYSTEM_MAP.md)) | |
| 2 | **Which subsystems must I NOT touch?** | |
| 3 | **Is `main.tsx` involved?** (§39 Main TSX Risk — declare section/symbols) | |
| 4 | **Does this affect candle loading?** (local-first, VPS delta, TF switch) | |
| 5 | **Does this affect viewport?** (§11 Candle Data vs Camera — data vs camera separate) | |
| 6 | **Does this affect save logic?** (`inspectorCommit`) | |
| 7 | **Does this affect Campaign or Hierarchy?** | |
| 8 | **Electron smoke required?** ([`GOLDEN_SMOKE.md`](../testing/GOLDEN_SMOKE.md) subset) | |
| 9 | **Rollback commit / branch?** (§44 commit baseline) | |
| 10 | **Success criteria** (1–3 observable behaviors) | |
| 11 | **STOP signals** (regressions that abort patch) | |

---

## PROJECT.RULES rules checklist (confirm read)

| Rule | Confirmed |
|------|-----------|
| Agent Chain Rule (§36) | ☐ |
| QA Gate Rule (§50) — QA VERDICT before commit | ☐ |
| Docs Control Plane Rule (§38) — SYSTEM_MAP, FILE_OWNERSHIP, DATA_FLOW, this file, TASK_TEMPLATE, GOLDEN_SMOKE, ADR | ☐ |
| Main TSX Risk Rule (§39) | ☐ |
| Commit Scope Rule (§45) — no mixed docs/production/release | ☐ |
| Golden Smoke Rule (§48) if UI/chart/workflow | ☐ |
| Candle Data vs Camera Rule (§11) if sync or reload | ☐ |
| Background sync discipline (§10 + §11) — delta only; no camera refit | ☐ |
| Python Truth Engine Rule (§31) if Python touched | ☐ |
| Canonical filename rule — report `PROJECT.RULES.md read: yes`; edit `project rules.md` | ☐ |

---

## Subsystem touch matrix (quick reference)

| If you touch… | Do NOT also change… |
|---------------|---------------------|
| **Cache** (`localCandleLibrary`, `syncService`, `candleCache.cjs`) | Save logic, detector, campaign derive formulas |
| **Chart** (`loadCandles`, D3, feed identity) | Backend routes, `map_ranges` schema |
| **Viewport** (`chartViewportPolicy`, camera) | Campaign Manager, session persistence |
| **Session** (`useMappingSessionPersistence`) | Viewport stabilization, candle sync limits |
| **Campaign** (`mappingCampaignManager`, panel wire-up) | VPS writes, local candle schema |
| **Hierarchy** (explorer tree, jump) | Save funnel, detector promote |
| **Save** (`inspectorCommit`) | Chart TF switch windows, Android |

---

## Architecture doc gates

Before merge, confirm read:

- [ ] [`project rules.md`](../../project%20rules.md) / `PROJECT.RULES.md read: yes`
- [ ] [`SYSTEM_MAP.md`](SYSTEM_MAP.md)
- [ ] [`FILE_OWNERSHIP.md`](FILE_OWNERSHIP.md)
- [ ] [ADR-001](./ADR/ADR-001-local-candle-library.md) … [ADR-004](./ADR/ADR-004-candle-first-mapping.md)
- [ ] [`DATA_FLOW_CONTRACTS.md`](DATA_FLOW_CONTRACTS.md)

---

## Candle-specific stop conditions

Stop and escalate to Sync Architect if:

- TF switch triggers full VPS history pull
- M15 tab shows D1/H1 candles
- H/L/BOS saves without feed guard passing
- `loadCandles` early-returns because of **feed guard** (not stale-request discard)
- Background 5m sync **refits camera** (violates §11)
- Audit refresh refits camera
- Local cache writes range/event rows

---

## Viewport-specific stop conditions

Stop if:

- Fit All / Lock resets after quiet candle reload
- Ordinary TF switch causes double-fit flicker
- Campaign Continue fits twice
- Replay arrow auto-pans without explicit feature flag
- Background sync blocks candle **updates** to protect camera (forbidden §11)

---

## Session / Campaign stop conditions

Stop if:

- Resume applies range ids before VPS refresh
- Campaign panel writes localStorage campaign truth
- Continue bypasses `assertCandleFeedReady`
- Gap queue uses `mapping_data` localStorage instead of `savedStructuralRanges`

---

## Test minimums

| Patch type | Required |
|------------|----------|
| Cache / sync | `syncService.test.ts`, `localCandleLibrary.test.ts` |
| Feed identity | `candleFeedIdentity.test.ts` |
| Viewport | `chartViewportPolicy.test.ts` |
| Campaign | `mappingCampaignManager.test.ts` |
| Session | `useMappingSessionPersistence.test.ts` |
| Any `main.tsx` | Manual Electron smoke on affected flow |

---

## Agent task report template (paste after patch)

```text
PROJECT.RULES.md read: yes
SYSTEM_MAP.md read: yes/no
Subsystem touched: ___
Files changed: ___
Tests run: ___
Electron smoke: pass/fail/not run — ___
QA VERDICT: PASS / CONDITIONAL / BLOCK / not reviewed
Rollback: commit ___
Architecture docs updated: yes/no
Boundary violations found: ___
Commit scope clean (§45): yes/no
```

---

## Recommended Pilot restrictions (standing)

1. **One subsystem per PR** — no combined Session + Viewport + Cache mega-patches.
2. **`main.tsx`** — declare section per §39; extract to module when > ~50 lines new.
3. **Never disable `assertCandleFeedReady`** to “unblock” mapping bugs.
4. **Never full VPS fetch on TF switch** — missing-window + delta only ([ADR-001](./ADR/ADR-001-local-candle-library.md)).
5. **Campaign** — read-only VPS + derived compute; Continue → existing `activateMappingGap`.
6. **Do not touch** detector, Android, backend routes, save logic unless task says so.
7. **Viewport changes** — dedicated task + golden smoke §4; do not piggyback on unrelated fixes (baseline `59db083`).
8. **Commit Scope (§45)** — docs-only commits separate from production WIP.

---

## Commit recommendation (docs-only Sync Architect / Librarian pass)

```text
docs(control-plane): reconcile PROJECT.RULES references and agent chain

Align control-plane docs with canonical PROJECT.RULES.md doctrine.
No production logic changed.
```

Pilot feature commits: cite ADR / DATA_FLOW flow letter (A–E) in commit body.
