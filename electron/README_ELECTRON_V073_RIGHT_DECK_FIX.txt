# Electron v073 Right Deck Tab Fix

Fixes blank screen caused by `rightDeckTab is not defined` in MapStudio.

Changed:
- Added missing React state declaration:
  const [rightDeckTab, setRightDeckTab] = useState<'gps'|'mark'|'seed'>('gps');

Notes:
- Electron only.
- No backend changes.
- Run `npm run build` locally after replacing files so `dist/` is regenerated from the fixed source.
