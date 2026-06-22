# PROJECT.RULES.md

# FX TrendMaster Doctrine

This file is the canonical doctrine for FX TrendMaster.

Every agent, coding session, recovery task, refactor, and debug pass must follow this file.

The canonical filename is:

```text
PROJECT.RULES.md
```

If the repo contains another variant such as:

```text
project rules.md
Project Rules.md
PROJECT_RULES.md
```

agents must report the mismatch.

Do not rename or normalize rule files during production bug fixes. Filename cleanup belongs in a dedicated docs/repo-control task.

---

# 1. Mandatory Agent Rule

Before working on any FX TrendMaster task, every agent must read and follow:

```text
PROJECT.RULES.md
```

This applies to:

```text
Pilot
Cursor
Composer agents
AI agents
Librarian
Sync Architect
QA Agent
Manual refactor sessions
Recovery agents
Debug agents
```

Every task response must confirm:

```text
PROJECT.RULES.md read: yes/no
Relevant rules followed
Subsystem touched
Files changed
Tests run
Electron/browser smoke status
Commit created: yes/no
```

If a task conflicts with `PROJECT.RULES.md`, stop and ask Josh before continuing.

No agent may treat this file as optional context.

---

# 2. Primary Purpose

FX TrendMaster exists to improve Josh's trading through structured market mapping, research, and statistical analysis.

The objective is:

```text
Map market structure
Collect factual data
Generate statistics
Improve trading decisions
```

FX TrendMaster is not currently:

```text
A SaaS platform
A social trading platform
An AI prediction engine
A signal service
A copy-trading platform
```

Those may be evaluated later.

Current priority is:

```text
Data collection
Data quality
Statistical validation
Mapping speed
Mapping accuracy
```

---

# 3. Trader First Rule

Priority order:

```text
Trader
Researcher
Builder
Founder
```

If a feature does not improve:

```text
Mapping
Research
Statistics
Trading decisions
```

it is probably not important.

Do not build features because they are technically interesting.

Build only what helps Josh trade better.

---

# 4. Solo User Rule

This application is built for one primary user:

```text
Josh
```

Do not build commercial infrastructure unless explicitly requested.

Avoid:

```text
multi-user accounts
roles and permissions
billing
subscription systems
tenant management
enterprise administration
team collaboration
commercial onboarding
cloud scaling architecture
```

The app should feel like a personal trading cockpit.

Not a SaaS dashboard wearing a candle costume.

---

# 5. Private Edge Rule

Josh's personal hierarchy, trading logic, range doctrine, statistics filters, and strategy interpretation are private.

Do not expose Josh's private method as a public/commercial default.

Commercial versions may provide:

```text
configurable mapping profiles
mentor templates
editable labels
editable hotkeys
template export/import
student copies
```

Commercial versions must not expose:

```text
Josh's exact hierarchy doctrine
Josh's strategy logic
Josh's private mapping template
Josh's statistics filters
Josh's trading edge
```

The product is the mapping machine.

Josh's brain is not the product.

---

# 6. Commercial Framework Rule

A future commercial FXTM version may support:

```text
Speed Mapping
Trade Journaling
Historical Event Browser
Mentor Template Builder
Student Review Mode
Stats Dashboard
```

Commercial FXTM should allow traders or mentors to define their own:

```text
event names
hotkeys
colors
structure labels
timeframe hierarchy
mapping sequence
journal fields
templates
```

Commercial users should build their own method inside the tool.

Do not commercialize Josh's private setup.

Commercialization is a future evaluation.

Not a current objective.

---

# 7. Structural Data Rule

Lean does not mean weak.

Never remove, flatten, bypass, or simplify:

```text
MACRO → WEEKLY → DAILY → INTRADAY → MICRO hierarchy

parent_range_id
active_range_id
old_range_id
new_range_id

created_by_event_id
broken_by_event_id

range status
inactive_from_time
direction_of_break

raw_case_id filtering

audit trails
exports

calculation_engine_version
```

Future analytics depend on clean structure.

Structure always wins.

---

# 8. Source Of Truth Rule

Backend storage is structural truth.

```text
Backend/VPS = Structural Truth
Local Cache = Performance Layer
Python Truth Engine = Analytical Truth derived from backend truth
```

Local cache may contain:

```text
Candles
Viewport optimization
Temporary render data
Session draft state
Render cache
```

Local cache must never own:

```text
Ranges
Events
Hierarchy
Campaign truth
Audit truth
Final mapping truth
```

Saved structure must come from backend/VPS.

---

# 9. Local Candle Library Rule

FXTM must use a local candle library as the primary chart candle source.

Architecture:

```text
Backend/VPS = master candle source and structural truth
Local candle library = fast candle performance layer
Chart = reads local first
VPS = missing-window/delta provider
```

The chart must not request full candle history from the VPS on every timeframe switch.

The VPS must not be asked for all candles every 5 minutes.

Local candle storage may contain:

```text
symbol
timeframe
time
open
high
low
close
volume/tick_volume
source
synced_at
is_closed
```

Unique key:

```text
symbol + timeframe + time
```

Local candle cache must never own:

```text
ranges
events
hierarchy
campaign truth
audit truth
final mapping truth
```

If structural-adjacent tables exist in local candle cache for rehydration, they must be treated as temporary compatibility artifacts and flagged for future cleanup.

Do not clean them during unrelated candle/viewport fixes.

---

# 10. Incremental Candle Sync Rule

Active symbol/timeframes must sync incrementally.

Supported timeframes:

```text
M15
H1
H4
D1
W1
MN1 if needed later
```

Do not build M1 support unless explicitly requested.

Sync rule:

```text
every 5 minutes
fetch only missing/latest candle deltas
upsert locally
update latest forming candle state
```

For latest forming candle:

```text
update high
update low
update close
update volume/tick_volume if available
do not duplicate timestamp
mark is_closed = false if supported
```

When the candle closes:

```text
mark previous candle closed
insert/update next forming candle
```

The 5-minute background sync must not:

```text
own structural truth
change ranges/events/hierarchy
trigger mapping saves
move viewport
display wrong timeframe candles
```

---

# 11. Candle Data vs Camera Rule

Candle data updates and camera movement are separate concerns.

Allowed:

```text
background sync updates candle OHLC
background sync updates latest forming candle
background sync inserts a newly closed candle
chart redraws after candle data changes
```

Forbidden:

```text
background sync refits camera
background sync recenters chart
background sync overrides Fit All
background sync overrides user pan/zoom
background sync blocks candle updates just to protect camera
```

Correct behavior:

```text
data updates allowed
camera movement blocked unless explicitly requested
```

Stable viewport owners may block camera movement only.

Stable viewport owners must not block candle writes.

If new candle data arrives for the active chart timeframe:

```text
merge/update chart candles
preserve current camera owner
redraw chart without refit
```

Do not solve viewport jumping by making candles stale.

That is not a fix. That is hiding the body under the carpet.

---

# 12. Candle Availability Audit Rule

Before changing frontend candle logic, first prove candle availability.

For any candle-loading bug, report counts for:

```text
symbol
timeframe
window start
window end
local count
VPS/API count
first candle time
last candle time
exact candle_cache.db path
```

Do this before changing UI behavior.

If M15 data is missing, say:

```text
M15 data missing. Import/sync required.
```

Do not mask missing data with frontend fallback candles.

Do not show Daily/H1 candles under M15 just to avoid an empty chart.

A blank chart with a truthful warning is better than a beautiful chart saving poison.

---

# 13. Candle Feed Identity Rule

The app must never allow mapping against the wrong candle feed.

The active mapping context must match the loaded candle context.

Required invariant:

```text
structure_layer
source_timeframe
chart_timeframe
selected tab timeframe
loaded_candle_timeframe
displayed candle data
symbol
case_id
```

must agree before allowing:

```text
H
L
BOS_UP
BOS_DOWN
auto checkpoint save
```

Expected defaults:

```text
WEEKLY    → W1
DAILY     → D1
INTRADAY  → H4 or H1
MICRO     → M15 or M5
```

If mismatch exists:

```text
Block mapping
Show warning
Reload correct candles
Do not save
```

Example:

```text
Active layer: MICRO
Expected TF: M15
Loaded TF: H1
```

This must block all H/L/BOS actions.

Wrong-timeframe saves are database poison.

---

# 14. No Wrong-Candle Display Rule

The chart must never display one timeframe while claiming another.

Required invariant:

```text
selected tab timeframe
requested timeframe
loaded candle timeframe
displayed candle data
loadedCandleContext
```

must match.

If a timeframe switch fails:

```text
clear stale candles
show diagnostic message
block H/L/BOS
do not display previous timeframe candles
```

Correct failure state:

```text
No M15 candles available for this window.
Sync/import required.
```

Incorrect failure state:

```text
M15 tab selected while Daily/H1 candles remain visible
```

Wrong-timeframe display is a critical bug.

---

# 15. Candle Loading Must Not Be Guarded Away

Candle-feed guards must never block candle loading.

Allowed guard scope:

```text
block H
block L
block BOS_UP
block BOS_DOWN
block auto range save
block auto BOS save
block auto chain save
```

Forbidden guard scope:

```text
blocking loadCandles()
blocking local candle reads
blocking VPS delta sync
blocking chart rendering after valid candles arrive
turning loading state into permanent mismatch
```

The app must always try to load the requested candles.

Then, only after load result is known, decide whether mapping is allowed.

---

# 16. Timeframe Switching Rule

Timeframe switching must be safe and fast.

Required behavior:

```text
Use local candle library per symbol/case/timeframe
Discard stale async candle loads
Do not let old H1 loads overwrite newer M15 loads
Show loading status when target TF is not loaded
Disable mapping shortcuts while candle feed is mismatched/loading
Render candles before overlays
Avoid audit/campaign refresh on ordinary timeframe switch
```

The app may visually indicate target timeframe while loading, but must not allow mapping until loaded candles match.

---

# 17. Timeframe Switch Load Window Rule

Timeframe switching must not use the current camera viewport as the candle data window unless explicitly requested.

Forbidden:

```text
use visible chart viewport timestamps as default data-load window
load only 1 candle because viewport is narrow
reject tiny load then keep stale candles visible
```

Required:

```text
use timeframe-aware padded data windows
use structural parent/context window when mapping
use local candle library first
fallback to VPS missing-window sync
clear stale candles if requested TF cannot load
```

---

# 18. Async Load Race Rule

Every candle load request must have a request id.

Only the latest matching request may update chart candle state.

Late responses must be discarded if they do not match the current requested timeframe/context.

Example:

```text
request 41 = H1
request 42 = M15
H1 returns after M15
discard H1
```

Never allow stale responses to overwrite current timeframe state.

---

# 19. Chart Doctrine

The chart exists to support mapping.

The chart is not the product.

Priority order:

```text
Usability
Correctness
Performance
Stability
Visual polish
```

Chart updates must never break:

```text
Viewport position
Replay position
Guided mapping flow
Session restore
Candle-feed identity
Overlay anchoring
Keyboard mapping
```

The user should not need to constantly adjust candle width/height.

Chart viewport must choose sane defaults automatically.

---

# 20. Viewport Ownership Rule

Camera and viewport changes must have clear ownership.

Late async effects must not override explicit user view choices.

Manual actions that should remain stable:

```text
Fit All
Fit Range
Fit Replay
Fit Case
User pan/zoom
Lock View
Campaign Continue fit
Hierarchy jump fit
Timeframe switch fit
```

Forbidden behavior:

```text
Fit All works then resets seconds later
Audit refresh refits camera
Overlay refresh refits camera
Saved range refresh refits camera
Replay step auto-pans without explicit permission
Background candle sync refits camera
Local candle reread refits camera
```

Any camera mutation must identify its reason/source during debugging.

Camera mutation debug logs should include:

```text
camera update: reason=... source=... ownerBefore=... ownerAfter=... candleCount=...
```

---

# 21. Overlay Projection Rule

Higher-timeframe overlays must project correctly onto lower-timeframe charts.

Rules:

```text
Weekly lines on Daily/H1/M15 use Weekly RH/RL prices
Daily lines on H1/M15 use Daily RH/RL prices
Intraday lines on M15 use Intraday RH/RL prices
```

Overlays must use the same price scale as candles.

Never use a separate overlay y-scale.

When mapping Intraday:

```text
Macro = faint background
Weekly = muted parent context
Daily = active container
Intraday = current focus
Micro = hidden unless drilling
```

When mapping Micro:

```text
Weekly = faint background
Daily = muted container
Intraday = active parent
Micro = current focus
```

Parent context must anchor the user, not confuse the chart.

---

# 22. Candle-First Mapping Rule

The main product workflow is candle-first mapping.

The user should spend time:

```text
reading candles
selecting structure
moving through replay
mapping hierarchy
```

not managing buttons.

Preferred interaction:

```text
Click candle
H = RH
L = RL
Arrow Up = BOS_UP
Arrow Down = BOS_DOWN
Left Arrow = replay back
Right Arrow = replay forward
U = undo draft action
Esc = clear selection / cancel draft
```

The machine handles bookkeeping.

The user chooses structural candles.

---

# 23. Configurable Mapping Profile Rule

Josh's current setup is the default private profile.

Future profiles may allow editable:

```text
event names
display labels
hotkeys
colors
layer availability
mapping sequence
```

However, database structure must use canonical event meaning.

Good:

```text
event_type = ANCHOR_HIGH
user_label = RH
hotkey = H
```

Bad:

```text
event_type = Josh's RH Thing
```

Customization may affect:

```text
UI labels
hotkeys
display names
colors
shortcut help
```

Customization must not break:

```text
range hierarchy
BOS links
parent/child chain
statistics
audit
exports
```

---

# 24. Machine Responsibility Rule

The machine must handle completed structural checkpoints.

When RH + RL exist:

```text
create/update current working range
show solid selected range lines
link parent_range_id
refresh hierarchy/campaign quietly
```

When BOS is marked:

```text
save BOS event
link active_range_id
mark old range BROKEN
set broken_by_event_id
set inactive_from_time
set direction_of_break
prepare next range context
```

When next RH + RL are set after BOS:

```text
create/update next range
set old_range_id
set created_by_event_id
set previous range new_range_id
preserve/derive valid parent_range_id
```

The user should not need primary workflow buttons like:

```text
Save Range
Update Daily Range
Update Broken Range
Save Event
Save Next Range
Refresh Campaign
Refresh Audit
```

Those may exist under advanced/correction tools, but they must not be required for normal mapping.

---

# 25. Workflow Over Detector Rule

The detector is an assistant.

The mapping workflow is the product.

If forced to choose:

```text
Working Mapping Workflow
>
Detector Sophistication
```

A reliable manual workflow is preferable to a sophisticated detector that disrupts mapping.

Detector outputs are suggestions only.

Mapping progress takes priority.

Do not let detector logic auto-switch layer, timeframe, or save structure unless the candle feed and mapping context are verified.

---

# 26. Mapping Campaign Rule

The mapping campaign is the core workflow.

Campaign flow:

```text
Map Weekly
↓
Map Daily
↓
Map Intraday
↓
Map Micro
↓
Cover Parent Range Completely
↓
Save BOS Events
↓
Generate Statistics
```

Campaign completeness is based on coverage.

Not child count.

The preferred mapping habit is:

```text
Weekly container first
Daily skeleton second
Intraday detail third
Micro confirmation last
```

---

# 27. Parent Child Coverage Rule

Every parent range must be covered end-to-end.

Coverage must detect:

```text
Front gaps
Middle gaps
Tail gaps
Out-of-window children
```

Campaign completion requires:

```text
COMPLETE_COVERAGE
```

not merely:

```text
HAS_CHILDREN
```

---

# 28. Event Doctrine

Events represent factual market actions.

Events should remain simple.

Preferred event model:

```text
BOS_UP
BOS_DOWN

SWEEP_HIGH
SWEEP_LOW

RECLAIM_HIGH
RECLAIM_LOW

CUSTOM_EVENT
```

Statistics derive meaning later.

Do not force strategy interpretation into storage.

---

# 29. Correction Doctrine

Before backend commit:

```text
Undo draft action
Clear draft
Replace selected RH/RL/BOS
```

After backend commit:

```text
Use explicit correction mode
Audit the correction
Never silently delete structural truth
```

Correction tools may include:

```text
Edit selected range
Correct RH/RL
Void/replace BOS event
View audit trail
Force commit
```

These belong under advanced/correction tools, not the primary mapping path.

---

# 30. Statistics First Rule

Do not build:

```text
AI prediction engines
signal generators
autonomous trading systems
machine learning models
```

unless explicitly requested.

Priority order:

```text
Data Collection
↓
Data Quality
↓
Statistics
↓
Research
↓
Machine Learning
```

Statistics must prove value before ML is considered.

---

# 31. Python Truth Engine Rule

Python may derive clean analytical truth from raw mapping data, but it must not silently mutate raw structural truth.

Raw backend mapping data remains auditable and rebuildable.

Python may create:

```text
clean_ranges
clean_events
clean_range_chains
clean_parent_child_coverage
clean_trade_context
clean_profile_classifications
statistical_summary_tables
Parquet analytical exports
structured JSON analytical exports
```

Python must not silently rewrite:

```text
map_ranges
map_events
hierarchy truth
BOS truth
audit trail
raw mapping ledger
```

Any correction to raw structural truth must use explicit correction mode and audit.

Recommended processing fields:

```text
processing_status
processing_version
processed_at
processing_error
source_raw_updated_at
```

Suggested statuses:

```text
PENDING
PROCESSED
FAILED
NEEDS_REPROCESS
```

If the processing logic changes:

```text
mark clean outputs stale
rebuild clean analytical truth from raw backend truth
do not alter raw mapping history silently
```

Analytics should read clean processed truth, not dirty raw drafts.

---

# 32. Trade Journal Doctrine

Trade journaling is a future module.

It should link trades to factual structure.

A trade may link to:

```text
entry candle
exit candle
range_id
BOS event
session
setup label
risk
result
screenshots
notes
```

Trade journaling must not replace structural mapping.

Structural mapping remains the foundation.

---

# 33. Historical Explorer Doctrine

The future historical explorer should allow folder-style browsing of:

```text
years
symbols
cases
ranges
events
trades
sessions
screenshots
notes
```

Clicking an item should open the relevant chart context.

Historical explorer must read from backend truth and local candle library.

It must not create a separate structural truth.

---

# 34. Research Doctrine

The goal is not to prove a strategy.

The goal is to discover what price actually does.

Research questions include:

```text
Continuation frequency
Reversal frequency
Abandonment frequency
Reclaim frequency
Weekly → Daily relationships
Daily → Intraday relationships
Intraday → Micro relationships
Day-of-week behaviour
Session behaviour
Profile transitions
```

---

# 35. One Subsystem Rule

A task may modify only one major subsystem.

Subsystems:

```text
Chart
Campaign
Session
Hierarchy
Detector
Cache
Statistics
API
Keyboard Mapping
Viewport
Overlays
Startup Shell
Candle Loader
Candle Sync
Local Candle Library
QA / Docs
```

One task = one subsystem.

Cross-subsystem refactors require explicit approval from Josh.

Do not sneak in bonus refactors.

Do not “clean up nearby code” unless explicitly requested.

Bonus improvements are how working systems get murdered politely.

---

# 36. Agent Chain Rule

FXTM work must use the agent chain.

```text
Librarian → Sync Architect → Pilot → QA → Josh smoke/commit decision
```

Responsibilities:

```text
Librarian = map code ownership, duplicate logic, fragile files, docs
Sync Architect = define subsystem boundaries, data-flow contracts, stop conditions
Pilot = patch one approved subsystem only
QA = review evidence, diff, smoke, and commit safety
Josh = final product judgement and manual cockpit validation
```

Pilot must not receive broad debugging tasks without Librarian and Sync Architect backstops when the task touches:

```text
candle loading
local candle library
sync service
viewport
chart rendering
Campaign
Hierarchy
mapping saves
session restore
audit/export
main.tsx
```

Many agents may inspect.

Only one agent may code production logic at a time.

Many eyes. One hand on the code.

---

# 37. Cursor / Pilot Containment Rule

Cursor/Pilot must not perform creative repair work.

Allowed:

```text
diagnose named bug
patch named bug
test named bug
report named bug
```

Forbidden unless explicitly approved:

```text
bonus refactors
nearby cleanup
UI redesign
architecture rewrite
touching unrelated files
changing behavior outside the named bug
fixing second discovered issue inside same patch
```

If another issue is discovered, report it and stop.

Do not fix a second issue inside the same task unless Josh explicitly approves.

---

# 38. Docs Control Plane Rule

The following docs are part of the FXTM control plane:

```text
docs/architecture/SYSTEM_MAP.md
docs/architecture/FILE_OWNERSHIP.md
docs/architecture/DATA_FLOW_CONTRACTS.md
docs/architecture/PILOT_BACKSTOP_CHECKLIST.md
docs/agents/TASK_TEMPLATE.md
docs/testing/GOLDEN_SMOKE.md
docs/architecture/ADR/
```

Agents must use these before coding.

If these docs are missing, stale, or contradictory, stop and report before risky production work.

Docs may guide code.

Docs must not be mixed into unrelated production commits.

---

# 39. Main TSX Risk Rule

`electron/src/main.tsx` is high-risk orchestration code.

Any task touching `main.tsx` must declare:

```text
which section is being edited
which symbols/functions are touched
why module-level change is not enough
which subsystems could be affected
```

Large `main.tsx` patches require extra QA.

If `main.tsx` changes exceed a small targeted patch, QA must treat the patch as high risk.

`main.tsx` should orchestrate.

It should not become the permanent home for every subsystem.

---

# 40. No-Taking-Chances Rule

When FXTM is close to a mapping marathon, stability outranks speed.

If a task can possibly affect:

```text
candle loading
timeframe switching
mapping saves
Campaign Continue
Hierarchy navigation
replay
viewport
session restore
audit/export
```

then it is a high-risk task.

High-risk tasks require:

```text
small patch
one subsystem only
manual Electron smoke
no commit until smoke passes
```

Unit tests alone are not enough.

---

# 41. Restore Before Replace Rule

If a working feature is lost:

```text
Restore before redesigning.
```

Never rebuild a subsystem that can be recovered from Git.

Recovery takes priority over reinvention.

---

# 42. Known-Good Baseline Rule

Before risky work begins, confirm the current known-good commit.

Every risky patch must answer:

```text
What is the rollback commit?
What changed since that commit?
Can we return to baseline cleanly?
```

If a patch breaks candle loading, mapping, or replay:

```text
stop
do not stack fixes
stash/revert the patch
confirm baseline works
then reapply a smaller fix
```

Never repair a broken patch by adding more unrelated changes on top of it.

---

# 43. Uncommitted Work Rule

Uncommitted work is dangerous.

Before starting a new task:

```text
git status
git diff
```

If there are uncommitted changes:

```text
commit if stable
stash if experimental
discard if broken
```

Do not start a second task while broken or unverified work is still loose.

---

# 44. Commit Discipline Rule

Major working milestones must be committed before risky work.

Required:

```text
One logical task
One focused patch
One commit
One smoke test
```

Do not combine unrelated work into one giant commit.

Examples:

```text
Good:
feat(map-studio): add candle-first skeleton mapping workflow

Good:
fix(map-studio): stabilize chart viewport and timeframe fitting

Bad:
fix chart, campaign, keyboard, detector, cache, and vibes
```

Before starting risky refactors:

```text
commit current stable baseline
```

---

# 45. Commit Scope Rule

A commit must contain one logical purpose only.

Production patches must not include unrelated docs, release bundles, generated artifacts, or rule rewrites.

Forbidden mixed commits:

```text
candle loader fix + PROJECT.RULES.md rewrite
viewport fix + release bundle
Campaign fix + backend schema cleanup
main.tsx patch + unrelated formatting sweep
```

Required separation:

```text
docs-only commit
production-code commit
test-only commit if needed
release artifact commit only when explicitly requested
```

Before commit:

```text
git diff --cached --name-only
```

If out-of-scope files are staged, unstage them.

Never commit:

```text
electron/release-*
typo files
temporary diagnostics unless intentionally kept
large generated bundles
unrelated rule rewrites inside production patch
```

---

# 46. Electron Smoke Rule

Any task affecting chart, candles, Campaign, Hierarchy, replay, mapping shortcuts, or session restore requires manual Electron cockpit smoke.

Cursor browser at `localhost:5173` is not enough when Electron preload/local SQLite/VPS bridge is involved.

Required smoke must state:

```text
Electron cockpit tested: yes/no
Cursor browser only: yes/no
```

If only Cursor browser was tested, the task is not complete.

---

# 47. Browser Smoke Failure Rule

If smoke fails:

```text
do not commit
do not continue feature work
report exact failing step
preserve or stash patch
return to known-good baseline if needed
```

Do not describe failed smoke as “partial pass” unless the untested parts are clearly marked unsafe.

---

# 48. Golden Smoke Rule

High-risk patches must run the golden smoke checklist in Electron.

Minimum golden smoke:

```text
app starts
pilot case opens
candle library path visible/verified
W1 loads or truthful warning
D1 loads or truthful warning
H4 loads or truthful warning
H1 loads or truthful warning
M15 loads or truthful warning
H1 → H4 → H1 switch
D1 → M15 switch
no wrong timeframe candles displayed
Fit All stable after 10 seconds
Fit Range stable after 10 seconds if available
replay forward/back works
Campaign Continue works if relevant
Hierarchy jump works if relevant
H/L shortcuts work only with valid feed
BOS ↑/↓ works only with valid feed
audit refresh works if relevant
export works if relevant
reload/session restore works if relevant
background candle sync updates data without moving camera
```

If a golden smoke item is not tested, say:

```text
not tested
```

Do not imply pass.

---

# 49. Regression Checklist Rule

Every patch must verify it did not break:

```text
candle loading
timeframe switching
Hierarchy jump
Campaign Continue
replay forward/back
viewport fit stability
H/L shortcuts
BOS shortcuts
session restore
audit refresh
export
```

If the patch touches only one subsystem, still check that these critical paths were not obviously broken.

---

# 50. QA Gate Rule

No production patch may be committed until QA gives one of:

```text
QA VERDICT: PASS
QA VERDICT: CONDITIONAL
QA VERDICT: BLOCK
```

Commit is allowed only on:

```text
QA VERDICT: PASS
```

A conditional verdict does not permit commit unless the listed conditions are completed and re-reviewed.

A block verdict means:

```text
do not commit
do not stack fixes blindly
revise or stash/revert
```

QA must verify:

```text
files touched
git diff scope
tests run
Electron cockpit smoke
critical regression checklist
architecture compliance
commit cleanliness
```

For chart/candle/workflow tasks, unit tests are not enough.

No Electron smoke means no production commit.

---

# 51. Commit Acceptance Rule

A commit is allowed only when:

```text
PROJECT.RULES.md read
one subsystem touched
tests pass
manual Electron smoke passes if UI/chart/workflow affected
QA verdict is PASS if production code changed
no known critical regression
rollback baseline identified
commit scope is clean
```

A commit is not allowed when:

```text
candles do not load
wrong timeframe candles display
H/L/BOS can save on mismatch
Campaign Continue is broken
Hierarchy jump is broken
replay is broken
audit/export is broken
viewport jumps unexpectedly
background sync blocks candle updates
production patch contains unrelated docs or release artifacts
```

---

# 52. Agent Reporting Rule

Every agent report must include:

```text
PROJECT.RULES.md read: yes/no

Task name:
Subsystem touched:
Known-good baseline commit:
Files touched:
Files intentionally excluded:

Backend routes changed: yes/no
Detector changed: yes/no
Android changed: yes/no
Structural save logic changed: yes/no
Candle loading changed: yes/no
Timeframe switching changed: yes/no
Viewport/camera changed: yes/no
main.tsx changed: yes/no

Tests run:
Tests passed:

Electron cockpit smoke: yes/no
Cursor browser smoke: yes/no
Manual smoke notes:

Candle counts checked: yes/no
If yes:
- symbol
- timeframe counts
- local count
- VPS/API count
- first/last candle time
- exact candle DB path

Critical regression checklist:
- candle loading: pass/fail/not tested
- timeframe switching: pass/fail/not tested
- hierarchy jump: pass/fail/not tested
- Campaign Continue: pass/fail/not tested
- replay: pass/fail/not tested
- viewport fit: pass/fail/not tested
- background sync data update: pass/fail/not tested
- H/L shortcuts: pass/fail/not tested
- BOS shortcuts: pass/fail/not tested
- audit/export: pass/fail/not tested

QA verdict if applicable:
Commit created: yes/no
Commit hash:
Remaining issues:
```

If browser or Electron smoke is not run, say so clearly.

Do not present unit tests as proof of browser workflow correctness.

Humans still have to click the cursed thing.

---

# 53. Non-Negotiable Workflow Features

The following are part of the product contract.

Do not remove, disable, replace, or redesign without explicit approval.

```text
Campaign Manager
Guided Mapping Cursor
Session Persistence
BOS checkpoint save
Viewport Stabilization
Focus Mode
Coverage Audit
Parent Context Overlays
Hierarchy Navigation
Continue Campaign Workflow
Keyboard-first candle mapping
Candle-feed identity guard
Local candle library
Incremental candle sync
```

These are considered production features.

---

# 54. Startup Doctrine

Startup must not block the app with annoying modals.

Preferred entry modes:

```text
Live Chart View
Mapping Session
```

Live Chart View:

```text
opens chart immediately
allows timeframe switching
allows replay/checking
does not force Campaign resume
```

Mapping Session:

```text
lives in Campaign tab
shows resume/start new controls
restores guided task context
```

If a previous mapping session exists, show a non-blocking card/banner inside Campaign.

Do not block startup with a global “Resume Mapping Session?” modal.

---

# 55. Commercialization Rule

Do not build subscription infrastructure until:

```text
Mapping workflow is stable
Data collection is active
Statistics provide measurable value
Josh would willingly pay for FXTM himself
```

Commercialization is a future evaluation.

Not a current objective.

---

# 56. Final Rule

When unsure, protect:

```text
Mapping workflow
Backend truth
Chart correctness
Candle-feed correctness
Campaign sequence
Auditability
Josh's time
```

Everything else is secondary.

A blank chart with a truthful warning is better than a beautiful chart saving poison.

Never choose:

```text
show stale candles
guess timeframe
allow mapping
hide mismatch
commit uncertain structure
mix unrelated fixes
let AI freestyle across subsystems
```
