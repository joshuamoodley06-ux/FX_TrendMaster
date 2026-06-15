## Solo-User Architecture Rule

This app is built for one primary user: Josh.

Do not build commercial/SaaS infrastructure unless Josh explicitly asks for it.

Avoid:

```text
multi-user accounts
roles and permissions
billing
teams
tenant management
enterprise admin panels
cloud scaling architecture
commercial onboarding flows
generic public-user settings
```

However, do not weaken the structural data model.

The app still requires a durable core because future analytics depend on clean mapping facts.

Do not remove, flatten, or skip:

```text
MACRO → WEEKLY → DAILY → INTRADAY hierarchy
parent_range_id
active_range_id
old_range_id
created_by_event_id
broken_by_event_id
range status
inactive_from_time
raw_case_id filtering
audit
export
calculation_engine_version for analytics later
```

Lean does not mean weak.

Lean means:

```text
simple UI
single-user workflow
no commercial bloat
strong structural storage
clean audit/export
```

The priority is Josh’s mapping rhythm, not commercial polish.
