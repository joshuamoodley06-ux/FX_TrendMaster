# FX TrendMaster Electron v087.18b - Reload Safe DB Audit + Reject Storage

Fixes blank screen on cold reload introduced in v087.18.

Root cause:
- The history mark filter memo referenced activeCaseLedger before activeCaseLedger was initialized on renderer boot.
- Build passed, but runtime crashed on reload.

Fix:
- Removed activeCaseLedger dependency from visibleEvents filtering.
- Active Case history filter now uses explicit case_id only at this stage.
- Rejected candidate saving and Export Case JSON remain included.

Backend:
- Use backend v150 for /api/v1/mos/seed-idea/{case_id}/audit.
