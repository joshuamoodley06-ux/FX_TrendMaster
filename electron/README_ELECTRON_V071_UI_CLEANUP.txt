FX TrendMaster Electron v071 - Map Studio UI Cleanup

Patch type: UI cleanup only. No backend/schema changes.

Changes:
- Removed MOS playback ledger, narrative tracker, auto trajectory and event list from Map Studio vertical stack.
- Moved Map Studio right panel into a tab deck: GPS / Mark / Seed.
- Moved range/event inputs and chart tool controls into the Mark tab.
- Moved Seed Idea Builder into the Seed tab so candle replay + seed capture stays fast without page-length scrolling.
- Kept Candle Replay visible and compact.
- Compressed toolbar spacing and increased chart priority.
- Backend unchanged from v146.

Test:
1. Run backend v146.
2. Run Electron.
3. Open Map Studio.
4. Use Candle Replay.
5. Switch right tabs: GPS, Mark, Seed.
6. Confirm chart remains the focus and no long scroll is needed for normal seed capture.
