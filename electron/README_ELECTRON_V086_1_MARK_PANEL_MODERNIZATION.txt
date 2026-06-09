Electron v086.1 - Mark Panel Modernization

Backend untouched.

Changes:
- Rebuilt Mark tab into modern three-zone layout:
  1) fixed selected candle + queue chips header
  2) scrollable middle event taxonomy
  3) fixed footer with Clear + Save to Narrative
- Event options are visible again instead of being blocked by Save/Clear.
- Save disabled until candle + queued event exists.
- Queue chips can be clicked to remove staged events.

Run:
npm install
npm run build
npm run dev
