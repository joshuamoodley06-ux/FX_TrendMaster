FX TrendMaster Electron MVP v0.07 - Saved Maps + Editable Map Settings

Run:
  npm install
  npm run dev

Build later:
  npm run dist

v0.07 changes:
- Renamed graphs to maps.
- Overview shows saved maps only; points are locked to prevent accidental finger drags.
- Map Settings is the editable workspace for dragging points, adding swings, labels, mitigation states, range high/low and tick intervals.
- Weekly and Daily maps can sit next to each other.
- Intraday map and Trade Idea can sit next to each other.
- Price label spacing improved with fewer overlapping labels.
- Local save persists map state.


v0.07 changes:
- Overview saved maps now auto-space path points horizontally for cleaner reading.
- Dotted projected objective no longer pulls awkwardly across the whole map.
- Save state button only appears in Map Settings.


v0.15: Overview map declutter. Hidden point/line labels on read-only maps; path panels explain sequence. Current node remains dominant.


V040 NOTE: API base URL is set to https://api01.apexcoastalrentals.co.za. Localhost references are only for Vite dev server launching, not backend API.
