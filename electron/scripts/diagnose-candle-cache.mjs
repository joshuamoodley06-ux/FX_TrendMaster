import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';

const home = process.env.USERPROFILE || process.env.HOME || '';
const appData = process.env.APPDATA || '';
const oneDrive = process.env.OneDrive || process.env.ONEDRIVE || '';
const candidates = [
  {
    label: 'electron_current_default_documents',
    researchFolder: path.join(home, 'Documents', 'FXTM_Research'),
    dbPath: path.join(home, 'Documents', 'FXTM_Research', 'candle_cache.db'),
  },
  ...(oneDrive ? [{
    label: 'electron_current_onedrive_documents',
    researchFolder: path.join(oneDrive, 'Documents', 'FXTM_Research'),
    dbPath: path.join(oneDrive, 'Documents', 'FXTM_Research', 'candle_cache.db'),
  }] : []),
  {
    label: 'legacy_roaming_package',
    researchFolder: null,
    dbPath: path.join(appData, 'fx-trendmaster-electron', 'candle_cache.db'),
  },
  {
    label: 'legacy_roaming_product',
    researchFolder: null,
    dbPath: path.join(appData, 'FX TrendMaster Cockpit', 'candle_cache.db'),
  },
];

const tfs = ['W1', 'D1', 'H4', 'H1', 'M15'];
const windowAudits = [
  { label: 'failed_h1_case_window', timeframe: 'H1', start: '2024-10-27', end: '2024-12-10' },
  { label: 'last_observed_m15_case_window', timeframe: 'M15', start: '2024-10-05', end: '2024-11-02' },
];

for (const c of candidates) {
  console.log(`\n[${c.label}]`);
  if (c.researchFolder) console.log(`research_folder=${c.researchFolder}`);
  console.log(`candle_cache_db=${c.dbPath}`);
  console.log(`exists=${fs.existsSync(c.dbPath)}`);
  if (!fs.existsSync(c.dbPath)) continue;
  const db = new DatabaseSync(c.dbPath);
  const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all().map((r) => r.name);
  console.log(`tables=${tables.join(',')}`);
  const hasCandles = tables.includes('candles');
  const hasSync = tables.includes('candle_sync_state');
  if (!hasCandles) {
    db.close();
    continue;
  }
  const total = db.prepare('SELECT COUNT(*) AS n FROM candles').get();
  console.log(`total_candles=${total.n}`);
  for (const tf of tfs) {
    const row = db.prepare(
      'SELECT COUNT(*) AS n, MIN(time) AS first_time, MAX(time) AS last_time FROM candles WHERE symbol = ? AND timeframe = ?',
    ).get('XAUUSD', tf);
    const sync = hasSync
      ? db.prepare(
        'SELECT last_time, bar_count, last_sync_at, last_mode, last_error FROM candle_sync_state WHERE symbol = ? AND timeframe = ?',
      ).get('XAUUSD', tf) || {}
      : {};
    console.log(JSON.stringify({
      timeframe: tf,
      count: row.n,
      first_time: row.first_time || null,
      last_time: row.last_time || null,
      last_sync_at: sync.last_sync_at || null,
      last_mode: sync.last_mode || null,
      sync_last_time: sync.last_time || null,
      sync_bar_count: sync.bar_count || null,
      last_error: sync.last_error || null,
    }));
  }
  for (const audit of windowAudits) {
    const row = db.prepare(
      'SELECT COUNT(*) AS n, MIN(time) AS first_time, MAX(time) AS last_time FROM candles WHERE symbol = ? AND timeframe = ? AND time >= ? AND time < ?',
    ).get('XAUUSD', audit.timeframe, audit.start.replace(/-/g, '.') + ' 00:00', audit.end.replace(/-/g, '.') + ' 00:00');
    console.log(JSON.stringify({
      window_audit: audit.label,
      timeframe: audit.timeframe,
      start: audit.start,
      end: audit.end,
      local_count: row.n,
      first_time: row.first_time || null,
      last_time: row.last_time || null,
    }));
  }
  db.close();
}
