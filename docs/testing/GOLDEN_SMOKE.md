# FX TrendMaster — Golden Smoke Checklist

**Canonical doctrine:** `PROJECT.RULES.md` → [`project rules.md`](../../project%20rules.md)  
**Rules:** Golden Smoke Rule (§48) · Electron Smoke Rule (§46) · Candle Data vs Camera Rule (§11) · QA Gate Rule (§50)  
**When required:** Any patch touching chart, candles, Campaign, Hierarchy, replay, mapping shortcuts, session restore, viewport, or save logic.

**Pass criteria:** Every checked item must pass or be explicitly marked **N/A with reason**. Failed smoke → **no commit** (QA VERDICT: BLOCK).

---

## Environment legend

| Symbol | Meaning |
|--------|---------|
| **🖥️ E** | **Electron Cockpit required** — preload, local SQLite candle library, IPC, VPS bridge |
| **🌐 B** | Cursor browser at `localhost:5173` — insufficient alone when marked **E** |
| **Either** | Unit/logic only; browser may suffice for layout sanity |

---

## 1. Startup

| # | Check | Env | Pass |
|---|-------|-----|------|
| 1.1 | App starts without crash | 🖥️ E | ☐ |
| 1.2 | Pilot case opens (create or select mapping case) | 🖥️ E | ☐ |
| 1.3 | Candle library path / status visible (local count or status line) | 🖥️ E | ☐ |
| 1.4 | No blocking global resume modal on startup (non-blocking banner OK) | 🖥️ E | ☐ |

---

## 2. Candle loading (per timeframe)

Load each TF with a known case/window. Record local count + first/last candle time in notes.

| # | Check | Env | Pass |
|---|-------|-----|------|
| 2.1 | **W1** loads with expected bar count | 🖥️ E | ☐ |
| 2.2 | **D1** loads | 🖥️ E | ☐ |
| 2.3 | **H4** loads | 🖥️ E | ☐ |
| 2.4 | **H1** loads | 🖥️ E | ☐ |
| 2.5 | **M15** loads **OR** shows truthful missing-data warning (not wrong-TF fallback) | 🖥️ E | ☐ |

**Failure examples (automatic fail):**

- M15 tab showing D1/H1 candles
- Empty chart with no diagnostic message when data missing
- Stale previous-TF candles after failed switch

---

## 3. Timeframe switching

| # | Check | Env | Pass |
|---|-------|-----|------|
| 3.1 | **H1 → H4 → H1** — correct candles each step; no stale overwrite | 🖥️ E | ☐ |
| 3.2 | **D1 → M15** — correct load or truthful failure | 🖥️ E | ☐ |
| 3.3 | Selected tab TF = loaded TF = displayed data (`loadedCandleContext`) | 🖥️ E | ☐ |
| 3.4 | Mapping shortcuts disabled while loading/mismatch (if applicable) | 🖥️ E | ☐ |

---

## 4. Viewport stability (10-second rule)

Perform action, wait **10 seconds** without clicking — camera must not reset.

| # | Check | Env | Pass |
|---|-------|-----|------|
| 4.1 | **Fit All** stable 10s after async reload quiet refresh | 🖥️ E | ☐ |
| 4.2 | **Fit Range** stable 10s | 🖥️ E | ☐ |
| 4.3 | Manual pan/zoom not overridden by overlay/audit refresh | 🖥️ E | ☐ |

---

## 5. Replay

| # | Check | Env | Pass |
|---|-------|-----|------|
| 5.1 | Replay **forward** (Right arrow or UI) advances cursor | 🖥️ E | ☐ |
| 5.2 | Replay **back** (Left arrow or UI) | 🖥️ E | ☐ |
| 5.3 | Replay cursor seeds near range start after hierarchy jump (not end of chart) | 🖥️ E | ☐ |

---

## 6. Campaign workflow

| # | Check | Env | Pass |
|---|-------|-----|------|
| 6.1 | **Campaign Continue** boots guided mapping on next gap | 🖥️ E | ☐ |
| 6.2 | Tier badges / next task reflect saved ranges | 🖥️ E | ☐ |
| 6.3 | Gap queue click matches Continue behavior (guided cursor) | 🖥️ E | ☐ |

---

## 7. Hierarchy navigation

| # | Check | Env | Pass |
|---|-------|-----|------|
| 7.1 | **Hierarchy jump** — row click switches layer/TF/window coherently | 🖥️ E | ☐ |
| 7.2 | Cross-layer jump (e.g. Weekly → Daily chart) loads windowed candles | 🖥️ E | ☐ |
| 7.3 | Parent context lines visible when mapping child layer | 🖥️ E | ☐ |

---

## 8. Keyboard mapping (valid feed only)

Precondition: candle feed identity guard **ready** (correct TF loaded, not loading).

| # | Check | Env | Pass |
|---|-------|-----|------|
| 8.1 | **H** sets RH on selected candle | 🖥️ E | ☐ |
| 8.2 | **L** sets RL | 🖥️ E | ☐ |
| 8.3 | **↑ BOS** saves only when feed valid | 🖥️ E | ☐ |
| 8.4 | **↓ BOS** saves only when feed valid | 🖥️ E | ☐ |
| 8.5 | H/L/BOS **blocked** when TF mismatch (warning shown) | 🖥️ E | ☐ |
| 8.6 | **U** undo draft / **Esc** clear selection | 🖥️ E | ☐ |

---

## 9. Audit / export

| # | Check | Env | Pass |
|---|-------|-----|------|
| 9.1 | **Hierarchy audit refresh** returns PASS/WARN/FAIL without breaking camera | 🖥️ E | ☐ |
| 9.2 | **Export** (audit JSON or mapping JSON) downloads | 🖥️ E | ☐ |
| 9.3 | Export does not write structural truth (file only) | 🖥️ E | ☐ |

---

## 10. Session restore

| # | Check | Env | Pass |
|---|-------|-----|------|
| 10.1 | Reload app — session resume restores layer/range/TF | 🖥️ E | ☐ |
| 10.2 | Guided cursor restores if active before reload | 🖥️ E | ☐ |
| 10.3 | Resume does not race boot candle loads (no double bootstrap) | 🖥️ E | ☐ |

---

## 11. Background sync vs camera (Candle Data vs Camera Rule §11)

Wait **10 seconds** after a quiet period with chart on active TF. Camera must not refit.

| # | Check | Env | Pass |
|---|-------|-----|------|
| 11.1 | 5-minute incremental sync (or manual quiet refresh) **updates** OHLC for active TF if new data exists | 🖥️ E | ☐ |
| 11.2 | Same sync/refresh does **not** refit Fit All / pan / zoom | 🖥️ E | ☐ |
| 11.3 | Sync does not display wrong-TF candles under active tab | 🖥️ E | ☐ |

---

## Smoke notes template

```text
Date:
Agent:
Baseline commit:
Electron version/build:

Symbol:
Case ID:

Candle counts:
  W1:  local ___  VPS ___
  D1:  local ___  VPS ___
  H4:  local ___  VPS ___
  H1:  local ___  VPS ___
  M15: local ___  VPS ___  (or MISSING — message shown: ___)

Failures (exact step):
-

Partial / N/A:
-
```

---

## Quick vs full golden smoke

| Patch type | Minimum smoke |
|------------|----------------|
| Docs only | None |
| Unit-test-only module (no main.tsx) | `npm run test` |
| `main.tsx` candle/viewport | Sections 1–4 + affected TF checks |
| Cache / background sync | Sections 1–2 + **11** |
| Campaign / hierarchy | Sections 6–7 |
| Session | Section 10 |
| Keyboard / save | Sections 8 + 2–3 |
| Release candidate | **Full checklist** (sections 1–11) |

---

## QA gate reminder

Production commits require **QA VERDICT: PASS** after this checklist (or documented subset) in Electron cockpit. See [`TASK_TEMPLATE.md`](../agents/TASK_TEMPLATE.md) §50.

*Cursor browser alone does not satisfy items marked 🖥️ E.*
