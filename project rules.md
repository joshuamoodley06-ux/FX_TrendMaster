# PROJECT.RULES.md

# FX TrendMaster Doctrine

## Primary Purpose

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

Current priority is data collection and statistical validation.

---

# Trader First Rule

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

---

# Solo User Rule

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

---

# Structural Data Rule

Lean does not mean weak.

Never remove, flatten, bypass, or simplify:

```text
MACRO → WEEKLY → DAILY → INTRADAY → MICRO hierarchy

parent_range_id
active_range_id
old_range_id

created_by_event_id
broken_by_event_id

range status
inactive_from_time

raw_case_id filtering

audit trails
exports

calculation_engine_version
```

Future analytics depend on clean structure.

Structure always wins.

---

# Workflow Over Detector Rule

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

---

# Statistics First Rule

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

# Mapping Campaign Rule

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

---

# Parent Child Coverage Rule

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

# Source Of Truth Rule

Backend storage is structural truth.

If local caching is introduced:

```text
Backend = Structural Truth

Local Cache = Performance Layer
```

Local cache may contain:

```text
Candles
Viewport optimization
Temporary render data
```

Local cache must never own:

```text
Ranges
Events
Hierarchy
Campaign state
Audit truth
```

---

# One Subsystem Rule

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
```

One task = one subsystem.

Cross-subsystem refactors require explicit approval.

---

# Restore Before Replace Rule

If a working feature is lost:

Restore before redesigning.

Never rebuild a subsystem that can be recovered from Git.

Recovery takes priority over reinvention.

---

# Non-Negotiable Workflow Features

The following are part of the product contract.

Do not remove, disable, replace, or redesign without explicit approval.

```text
Campaign Manager
Guided Mapping Cursor
Session Persistence
Auto BOS Save
Viewport Stabilization
Focus Mode
Coverage Audit
Parent Context Overlays
Hierarchy Navigation
Continue Campaign Workflow
```

These are considered production features.

---

# Chart Doctrine

The chart exists to support mapping.

The chart is not the product.

Priority order:

```text
Usability
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
```

---

# Event Doctrine

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

# Research Doctrine

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

# Commercialization Rule

Do not build subscription infrastructure until:

```text
Mapping workflow is stable

Data collection is active

Statistics provide measurable value

Josh would willingly pay for FXTM himself
```

Commercialization is a future evaluation.

Not a current objective.
