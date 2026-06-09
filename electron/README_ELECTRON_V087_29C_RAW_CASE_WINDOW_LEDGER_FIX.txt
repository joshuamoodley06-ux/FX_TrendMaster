Electron v087.29c - Raw Case Window + Ledger Save Fix

Fixes:
- Case Manager window no longer falls back to old rangeWindowByTf chart/YTD windows.
- Window Start/End now derive only from selected Case High/Low anchor candle times or manual input.
- Name YTD no longer mutates the case window.
- Events in TF no longer counts legacy /api/v1/map events; it shows raw ledger mode instead.
- Case Save now creates/uses /api/v1/raw-mapping/cases only and does not POST old bundled map events.
- Raw event saves create a raw mapping case automatically if needed.
- Delete raw event uses the raw UUID case id when available.

Install:
Copy patch files over the current Electron folder, rebuild/restart Electron.
