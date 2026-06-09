Electron v086.5 - Mark Workbench + Case Autofill + Real History Toggle

Backend unchanged.

Changes:
- Mark floating panel is now a wider workbench.
- Left rail: selected candle, queue chips, mode buttons, Save/Clear.
- Right side: event taxonomy accordions, so event options are actually visible.
- Removed practical dependence on the old single Event dropdown workflow.
- History Marks OFF now hides backend-loaded archive markers and shows only marks created during the current working session.
- History Marks ON shows backend/archive marks again.
- Case Manager now auto-pulls Weekly/Daily anchors from plotted map points/range memory when available.
- Added Auto-fill From Marks button in Case Manager.

Run:
npm install
npm run build
npm run dev
