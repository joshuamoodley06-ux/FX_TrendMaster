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
