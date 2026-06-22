# FX TrendMaster — Pilot / Cursor Task Template

**Mandatory:** Copy this template into every Pilot/Cursor task brief. Do not start work until all required fields are filled.

**Canonical doctrine:** `PROJECT.RULES.md` → read [`project rules.md`](../../project%20rules.md) (filesystem) · [`PROJECT.RULES.md`](../../PROJECT.RULES.md) (pointer)

**Agent chain (§36):** Librarian → Sync Architect → Pilot → **QA** → Josh smoke/commit decision. Pilot must not code high-risk areas without backstop docs current.

---

## Task name

_(One sentence — the named bug or feature only.)_

---

## PROJECT.RULES.md read

- [ ] **yes** / [ ] no  
- **Filesystem file read:** [`project rules.md`](../../project%20rules.md) at repo root  
- Relevant rules followed: _(list section names, e.g. One Subsystem Rule, Candle Feed Identity Rule, Main TSX Risk Rule, Commit Scope Rule)_

---

## SYSTEM_MAP.md read

- [ ] **yes** / [ ] no  
- Subsystem(s) from map: _(exactly one unless Josh approved more)_

---

## Subsystem touched

_(Pick one from SYSTEM_MAP.md)_

```text
[ ] Chart rendering
[ ] Candle loader
[ ] Local candle library
[ ] Candle sync
[ ] Viewport ownership
[ ] Keyboard mapping
[ ] Mapping save / checkpoint
[ ] Campaign Manager
[ ] Hierarchy navigation
[ ] Session persistence
[ ] Parent context overlays
[ ] Audit / export
[ ] Backend API / VPS
[ ] Python / statistics
[ ] Startup shell
```

---

## Files allowed

_(Explicit list — smallest set that can fix the named issue.)_

```text
-
-
```

---

## Files forbidden

_(Default forbidden unless task explicitly includes them.)_

```text
electron/src/main.tsx          (unless declared below with section + reason)
backend/**                     (unless Backend subsystem task)
backend/detector/**            (unless detector task approved)
android/**                     (always forbidden unless Android task)
electron/electron/*.cjs        (unless IPC/library task)
project rules.md / PROJECT.RULES.md   (unless doctrine/docs-control task)
docs/architecture/**           (docs-only commits — see Commit Scope Rule §45)
```

**If `main.tsx` is allowed, declare:**

| Section touched | Lines / symbols | Why |
|-----------------|-----------------|-----|
| | | |

---

## Known-good baseline commit

```text
git rev-parse HEAD before patch: 
Rollback target if smoke fails:   
```

---

## Current git status

```text
(Paste `git status --short` before starting.)
```

---

## Expected behavior

_(What should work after the patch — observable, not implementation.)_

1.
2.
3.

---

## Stop condition

_(When is the task done? When must the agent stop?)_

- [ ] Named bug fixed and verified
- [ ] Tests listed below pass
- [ ] Electron smoke listed below passes
- [ ] No other issues fixed in this task

**Hard stop rule:**

> **If another issue is discovered, report it and stop. Do not fix a second issue inside the same task without Josh approval.**

---

## Tests required

```text
Command: npm run test (from electron/)
Minimum: all tests pass
Subsystem-specific:
  -
```

---

## Electron smoke required

- [ ] **yes** — full golden smoke (`docs/testing/GOLDEN_SMOKE.md`) or subset listed below
- [ ] **no** — docs-only / backend-only (justify)

**Subset if not full golden smoke:**

```text
-
```

---

## Regression checklist

Mark pass / fail / not tested for each:

| Check | Result |
|-------|--------|
| Candle loading | |
| Timeframe switching | |
| Hierarchy jump | |
| Campaign Continue | |
| Replay forward/back | |
| Viewport fit stability (10s) | |
| H/L shortcuts (valid feed) | |
| BOS shortcuts (valid feed) | |
| Session restore | |
| Audit refresh | |
| Export | |

---

## Commit allowed

- [ ] **yes** — only after smoke + tests pass + **QA VERDICT: PASS** (§50 QA Gate Rule)
- [ ] **no** — exploratory / audit / blocked

**Commit Scope Rule (§45):** One logical purpose only. Do not mix production patch with unrelated docs, release bundles, or rule rewrites. Run `git diff --cached --name-only` before commit.

**Commit message format:**

```text
fix(map-studio): <one subsystem, one reason>
```

---

## Agent report block (paste when done)

```text
PROJECT.RULES.md read: yes/no
SYSTEM_MAP.md read: yes/no
Task name:
Subsystem touched:
Known-good baseline commit:
Files touched:

Backend routes changed: yes/no
Detector changed: yes/no
Android changed: yes/no
Structural save logic changed: yes/no
Candle loading changed: yes/no
Timeframe switching changed: yes/no

Tests run:
Tests passed:

Electron cockpit smoke: yes/no
Cursor browser smoke: yes/no
Manual smoke notes:

Candle counts checked: yes/no
(if yes: symbol, TF, local count, VPS count, first/last time)

Regression checklist: (paste table)

Commit created: yes/no
Commit hash:
QA VERDICT: PASS / CONDITIONAL / BLOCK / not reviewed
Remaining issues:
Discovered-but-not-fixed issues:
```

---

## QA gate (§50 — required for production commits)

QA must verify: files touched · diff scope · tests · **Electron cockpit smoke** · regression checklist · architecture compliance · commit cleanliness.

```text
QA VERDICT: PASS          → commit allowed
QA VERDICT: CONDITIONAL   → commit only after conditions met + re-review
QA VERDICT: BLOCK         → do not commit; stash/revert
```

Unit tests alone are **not** sufficient for chart/candle/workflow patches.

---

*Template version: 2026-06-19 · Authority: `PROJECT.RULES.md` / [`project rules.md`](../../project%20rules.md)*
