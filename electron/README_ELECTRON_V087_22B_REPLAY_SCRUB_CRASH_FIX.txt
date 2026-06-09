FX TrendMaster Electron v087.22b - Replay Scrub Crash Fix

Fixes Map Studio blank screen caused by ReferenceError: setCandleReplayFrameByTime is not defined.

Changes:
- Adds setCandleReplayFrameByTime(time) wrapper for chart scrub clicks.
- Replay step buttons now update global replay cursor time too.
- Keeps backend v154 unchanged.

Install:
- Use with backend_v154_case_reload_payload.zip.
