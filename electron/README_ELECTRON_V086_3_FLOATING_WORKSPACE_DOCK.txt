Electron v086.3 - Floating Workspace Dock

Electron-only patch.
Backend untouched.

Changes:
- Chart now owns the workspace again.
- Removed fixed right sidebar grid from Map Studio.
- Added vertical floating dock: N / G / M / S.
- Clicking a dock item opens the matching floating workspace panel.
- Clicking the same dock item toggles the panel closed.
- ESC closes active floating panel.
- Mark opens in Click Candle mode by default.
- Legacy event dropdown is hidden inside the floating Mark panel.
- Mark panel keeps selected candle header, queue chips, scrollable event groups, and sticky Save/Clear footer.

Test:
1. Launch Electron.
2. Open Map Studio.
3. Confirm chart is wider/larger.
4. Click M dock button.
5. Select candle, choose event buttons, Save to Narrative.
6. Close panel and confirm map remains large.
