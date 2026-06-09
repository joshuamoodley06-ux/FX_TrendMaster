Electron v079 safe Y-axis drag patch
- Restores manual vertical price panning on the right-side price strip.
- Uses frozen drag snapshot math to avoid recursive yScale jump bugs.
- Double-click price strip resets vertical pan/zoom.
- Keeps horizontal pan/zoom logic intact.
- Backend untouched.
