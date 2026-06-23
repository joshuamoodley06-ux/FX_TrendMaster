# PROJECT.RULES.md — canonical doctrine pointer

The FX TrendMaster doctrine uses the **canonical filename** `PROJECT.RULES.md`.

In this repository, the full doctrine is stored at:

**[`project rules.md`](./project%20rules.md)** (repo root)

---

## Filename rule (from doctrine)

| Name | Role |
|------|------|
| **`PROJECT.RULES.md`** | Canonical name agents report in task briefs |
| **`project rules.md`** | Actual editable file on disk (do **not** rename without Josh approval) |

Agents must read **`project rules.md`** and report **`PROJECT.RULES.md read: yes`** in task reports.

Do not rename or normalize rule files during production bug fixes. Filename cleanup belongs in a dedicated docs/repo-control task approved by Josh.

---

## Control plane docs (read before coding)

```text
docs/architecture/SYSTEM_MAP.md
docs/architecture/FILE_OWNERSHIP.md
docs/architecture/DATA_FLOW_CONTRACTS.md
docs/architecture/PILOT_BACKSTOP_CHECKLIST.md
docs/agents/TASK_TEMPLATE.md
docs/testing/GOLDEN_SMOKE.md
docs/architecture/ADR/
```

See **Docs Control Plane Rule** (§38) in `project rules.md`.

---

# 57. Chart Engine Separation Rule

FX TrendMaster must separate chart rendering from structural truth.

The chart engine is not the mapping brain.

Required separation:

```text
Chart engine = visual surface and user interaction layer
FXTM = structural truth, mapping doctrine, saves, hierarchy, audit, and statistics
```

The chart engine may own:

```text
candles
pan
zoom
crosshair
price scale
time scale
visible range
marker rendering
line rendering
chart resize
touch-friendly chart interaction
```

The chart engine must not own:

```text
map_ranges truth
map_events truth
parent_range_id truth
active_range_id truth
Campaign truth
Hierarchy truth
BOS save logic
RH/RL save logic
backend structural saves
audit truth
statistics logic
Python Truth Engine outputs
```

The chart may display structure.

It must not become the source of structure.

---

# 58. TradingView Chart Engine Doctrine

TradingView Lightweight Charts is the preferred future chart engine for FX TrendMaster.

This decision exists to improve:

```text
chart smoothness
pan/zoom quality
time scale stability
price scale stability
crosshair behavior
live chart viewing
hierarchy range navigation
future Android/tablet chart experience
```

TradingView should replace custom chart-rendering pain.

TradingView must not replace FXTM's mapping brain.

Doctrine:

```text
TradingView = chart surface
FXTM = structural truth
D3 = legacy fallback during migration
```

TradingView may be used for:

```text
Live Chart View
timeframe switching
replay visualization
hierarchy jump visualization
range overlays
event markers
selected candle interaction
future mapping input
future Android/WebView chart surface
```

TradingView must not be used to bypass:

```text
candle-feed identity guard
backend saves
range/event validation
Campaign sequence
Hierarchy relationships
audit/export rules
```

No TradingView task may weaken candle correctness.

A smooth wrong chart is still poison.

---

# 59. D3 Legacy Fallback Rule

D3 remains allowed as a fallback during TradingView migration.

D3 must not receive major new chart-engine investment unless Josh explicitly approves.

Allowed D3 work:

```text
critical bug fix
fallback preservation
parity comparison
temporary migration bridge
```

Forbidden D3 work unless explicitly approved:

```text
major renderer rewrite
new viewport engine
new candle engine
new touch interaction system
large visual redesign
duplicating TradingView features permanently
```

The migration goal is:

```text
stop building a custom trading chart engine
use TradingView for chart mechanics
keep FXTM for structure, mapping, and statistics
```

D3 deletion is forbidden until TradingView has proven parity.

---

# 60. TradingView Migration Phase Rule

TradingView migration must be phased.

Do not jump directly to full mapping replacement.

Required phases:

```text
Phase 0: Sync Architect contract and Librarian audit
Phase 1: TradingView Live View only
Phase 2: TradingView hierarchy jump and overlay mirror
Phase 3: TradingView selected candle bridge
Phase 4: TradingView mapping input behind feature flag
Phase 5: D3 fallback only after parity
```

Phase 1 may only include:

```text
render candles
switch timeframe
read existing local candle library
show chart status
resize cleanly
update latest candle visually
```

Phase 1 must not include:

```text
RH/RL save
BOS save
mapping input
Campaign mutation
Hierarchy mutation
backend structural writes
D3 deletion
```

Feature flags must exist before mapping migration:

```text
USE_TRADINGVIEW_LIVE_VIEW
USE_TRADINGVIEW_MAP_CHART
USE_TRADINGVIEW_MAPPING_INPUT
```

Default migration posture:

```text
Live View may be enabled.
Map Chart remains D3 until TradingView selection and overlays are proven.
Mapping Input remains disabled until QA approves.
```

---

# 61. TradingView Candle Adapter Rule

TradingView must receive candles through an explicit adapter.

Do not feed raw backend/local candle rows directly into TradingView components.

Required adapter contract:

```text
FXTM candle row
↓
validated adapter
↓
TradingView candle shape
```

TradingView candle output must include only valid:

```text
time
open
high
low
close
```

The adapter must reject or skip invalid rows safely.

The adapter must not:

```text
guess missing OHLC values
synthesize candles
change timeframe
change symbol
change candle source
silently mix candle feeds
silently change timestamps
```

The adapter must respect existing feed identity:

```text
symbol
source_timeframe
chart_timeframe
loaded_candle_timeframe
selected tab timeframe
active mapping context
```

If the candle feed is invalid, TradingView must show a truthful warning or empty state.

It must not display stale candles from another timeframe.

---

# 62. TradingView Hierarchy And Overlay Rule

TradingView hierarchy integration must use existing hierarchy truth.

When a user selects a hierarchy range, TradingView may:

```text
jump to range start/end
fit visible time range
fit visible price range
show parent context overlays
show RH/RL lines
show BOS markers
show active path context
```

TradingView must not:

```text
create ranges
edit ranges
relink parents
mark Campaign complete
change active_range_id
change parent_range_id
save BOS events
save RH/RL anchors
```

Hierarchy selection remains owned by FXTM.

TradingView only visualizes the selected hierarchy context.

Expected overlay path:

```text
Macro selected      → Macro only
Weekly selected     → Macro + Weekly
Daily selected      → Macro + Weekly + Daily
Intraday selected   → Macro + Weekly + Daily + Intraday
Micro selected      → Parent path + Micro focus
```

Overlay drawing must use the same price scale as candles.

No separate overlay y-scale is allowed.

---

# 63. TradingView Mapping Input Rule

TradingView mapping input is future work and must remain behind a feature flag until proven.

Required flag:

```text
USE_TRADINGVIEW_MAPPING_INPUT=false
```

Before enabling TradingView mapping input, QA must verify:

```text
click candle resolves exact OHLC row
selected candle time matches loaded candle data
selected timeframe matches active mapping context
H/L/BOS shortcuts use existing FXTM save flow
feed mismatch blocks all mapping writes
D3 fallback still works
backend saves are unchanged
```

TradingView may provide:

```text
click candle
crosshair candle info
selected candle highlight
marker display
range line display
touch selection later
```

TradingView must not provide independent save logic.

Correct flow:

```text
TradingView click
↓
selectedCandle bridge
↓
existing FXTM feed guard
↓
existing H/L/BOS action
↓
existing backend save path
↓
existing audit/export/statistics path
```

Incorrect flow:

```text
TradingView click
↓
direct save to backend
```

That bypass is forbidden.

---

# 64. Josh Focus / Agent Ownership Rule

Josh's primary responsibility is trading judgement, structure doctrine, and final product validation.

Agents must own coding, infrastructure, deployment sequencing, QA gates, and task handoffs wherever tools/access allow.

Do not push Git, VPS, command-line, deploy, code-search, or QA bookkeeping work onto Josh unless physical access is required.

Correct ownership:

```text
Repo-Control = push/merge/commit discipline
Pilot = approved code or deploy task
QA = tests, smoke, verdict
Librarian = read-only audit
Sync Architect = boundaries/contracts
Josh = trading decision, doctrine decision, final smoke judgement
```

If an agent lacks VPS/RDP/remote-shell access, it must say so clearly and provide one exact manual action for Josh.

Do not make Josh debug agent sequencing.

Do not make Josh remind agents to push before deploy.

Do not make Josh hunt for two lines in a script when a full replacement file is safer.

Protect Josh's time.

His brain is for trading.

The machine can do the plumbing.
