# Electron v087.18 - DB Audit + Rejected Candidate Storage

- Adds Export Case JSON button in Case Manager / Case Save.
- Export includes backend DB audit when backend v150 is installed.
- Rejected semi-auto HTF candidates now carry top-level candidate_status=REJECTED plus meta_json candidate_status.
- Rejected candidates remain stored for ML/audit without being treated as valid structure.
- No chart history filter changes in this patch; this avoids the prior reload blank-screen mess.
