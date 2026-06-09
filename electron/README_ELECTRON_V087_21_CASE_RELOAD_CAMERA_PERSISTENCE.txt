Electron v087.21 - Case Reload + Layer Camera Persistence

Adds:
- Opening a saved case restores case metadata, active case id, case window, case H/L, and chart camera.
- W1/D1 timeframe switching preserves the active case date window instead of jumping to latest candles.
- Case payload endpoint is used when available to hydrate linked ranges/events for visual reload.
- History filter moves to ACTIVE_CASE when opening saved cases.
- D3 camera now fits the saved case window/rangeStart/rangeEnd when available.

Use flow: plot Weekly -> save case -> reopen case -> switch to Daily -> camera stays in the case window -> add Daily ranges -> update same case.
