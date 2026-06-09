FX TrendMaster Electron v072 Security Console Fix

Changes:
- Added a Content-Security-Policy meta tag to index.html and dist/index.html.
- Removed automatic DevTools opening during npm run dev.
- DevTools can still be opened manually with Ctrl+Shift+I, or by running Electron with --devtools / ELECTRON_OPEN_DEVTOOLS=1.
- No backend changes required.

Purpose:
- Clears the Electron insecure CSP console warning shown in DevTools.
- Keeps Map Studio UI cleanup and full candle replay from v071/v070 intact.
