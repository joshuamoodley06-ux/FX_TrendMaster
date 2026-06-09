Electron v086.13 - Independent Case Manager + Range Memory Guard

- Case Manager no longer assumes Weekly+Daily must be saved together.
- Case scopes: Macro, Weekly, Daily, Intraday, Micro.
- Case save can wrap the active timeframe independently.
- Case save includes current scope/timeframe, high/low, range window, and saved event count.
- Removed automatic last-120-candle default range generation.
- Explicit local range anchors are persisted in localStorage.
- Backend map range can fill blanks but cannot overwrite explicit local Set M/W/D anchors.
- Event ledger remains the source of truth; Case remains a convenience wrapper/bookmark.
- Backend unchanged.
