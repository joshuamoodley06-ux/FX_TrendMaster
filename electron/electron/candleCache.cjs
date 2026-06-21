const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { app } = require('electron');
const { validateFractalRange, resolveParentId } = require('./fractalRangeValidation.cjs');
const { ensureResearchFolder } = require('./localResearchSettings.cjs');

/** @type {import('node:sqlite').DatabaseSync | null} */
let db = null;

const MAX_FETCH_LIMIT = 10_000;
const DEFAULT_FETCH_LIMIT = 500;

function legacyCacheDbPath() {
  return path.join(app.getPath('userData'), 'candle_cache.db');
}

function cacheDbPath() {
  return path.join(ensureResearchFolder(), 'candle_cache.db');
}

function migrateLegacyCacheIfNeeded() {
  const target = cacheDbPath();
  const legacy = legacyCacheDbPath();
  if (fs.existsSync(target) || !fs.existsSync(legacy)) {
    return target;
  }
  try {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(legacy, target);
    for (const suffix of ['-wal', '-shm']) {
      const sidecar = `${legacy}${suffix}`;
      if (fs.existsSync(sidecar)) {
        fs.copyFileSync(sidecar, `${target}${suffix}`);
      }
    }
  } catch {
    // Best effort — fresh cache is still usable if migration fails.
  }
  return target;
}

function nowIso() {
  return new Date().toISOString();
}

function normaliseSymbol(raw) {
  return String(raw || 'XAUUSD').trim().toUpperCase();
}

function normaliseTimeframe(raw) {
  return String(raw || 'D1').trim().toUpperCase();
}

function normaliseQueryTime(raw) {
  if (raw == null || raw === '') return null;
  const text = String(raw).trim();
  if (!text) return null;
  // Accept ISO / YYYY-MM-DD and pass through MT5-style YYYY.MM.DD HH:MM unchanged.
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    const parsed = new Date(text.includes('T') ? text : `${text}T00:00:00.000Z`);
    if (!Number.isNaN(parsed.getTime())) {
      const y = parsed.getUTCFullYear();
      const mo = String(parsed.getUTCMonth() + 1).padStart(2, '0');
      const d = String(parsed.getUTCDate()).padStart(2, '0');
      const h = String(parsed.getUTCHours()).padStart(2, '0');
      const mi = String(parsed.getUTCMinutes()).padStart(2, '0');
      return `${y}.${mo}.${d} ${h}:${mi}`;
    }
  }
  return text;
}

function initSchema(database) {
  database.exec(`
    CREATE TABLE IF NOT EXISTS candles (
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      time TEXT NOT NULL,
      open REAL NOT NULL,
      high REAL NOT NULL,
      low REAL NOT NULL,
      close REAL NOT NULL,
      volume REAL DEFAULT 0,
      source TEXT DEFAULT 'unknown',
      updated_at TEXT NOT NULL,
      PRIMARY KEY (symbol, timeframe, time)
    );

    CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, time);

    CREATE TABLE IF NOT EXISTS candle_sync_state (
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      last_time TEXT,
      bar_count INTEGER DEFAULT 0,
      last_sync_at TEXT,
      last_mode TEXT,
      last_error TEXT,
      PRIMARY KEY (symbol, timeframe)
    );

    CREATE TABLE IF NOT EXISTS mapping_ranges (
      id TEXT PRIMARY KEY,
      case_id TEXT,
      symbol TEXT NOT NULL,
      timeframe TEXT NOT NULL,
      structure_layer TEXT,
      range_high REAL NOT NULL,
      range_low REAL NOT NULL,
      start_time TEXT,
      end_time TEXT,
      parent_id TEXT,
      origin TEXT NOT NULL DEFAULT 'Root',
      status TEXT DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_mapping_ranges_lookup
      ON mapping_ranges(symbol, timeframe, case_id);
    CREATE INDEX IF NOT EXISTS idx_mapping_ranges_parent
      ON mapping_ranges(parent_id);
  `);
}

function connect() {
  if (db) return db;
  const dbPath = migrateLegacyCacheIfNeeded();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const { DatabaseSync } = require('node:sqlite');
  db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA synchronous = NORMAL');
  db.exec('PRAGMA busy_timeout = 60000');
  initSchema(db);
  return db;
}

function initCandleCache() {
  return connect();
}

function closeCandleCache() {
  if (db) {
    db.close();
    db = null;
  }
}

function normaliseCandleRow(raw, defaults = {}) {
  const symbol = normaliseSymbol(raw?.symbol ?? defaults.symbol);
  const timeframe = normaliseTimeframe(raw?.timeframe ?? defaults.timeframe);
  const time = String(raw?.time ?? '').trim();
  if (!time) {
    throw new Error('candle time is required');
  }
  const open = Number(raw?.open);
  const high = Number(raw?.high);
  const low = Number(raw?.low);
  const close = Number(raw?.close);
  if (![open, high, low, close].every(Number.isFinite)) {
    throw new Error(`invalid OHLC for ${symbol} ${timeframe} ${time}`);
  }
  const volumeRaw = raw?.volume;
  const volume = volumeRaw == null || volumeRaw === '' ? 0 : Number(volumeRaw);
  return {
    symbol,
    timeframe,
    time,
    open,
    high,
    low,
    close,
    volume: Number.isFinite(volume) ? volume : 0,
    source: String(raw?.source ?? defaults.source ?? 'unknown'),
  };
}

function fetchCandles(args = {}) {
  const database = connect();
  const symbol = normaliseSymbol(args.symbol);
  const timeframe = normaliseTimeframe(args.timeframe);
  const start = normaliseQueryTime(args.start ?? args.from);
  const end = normaliseQueryTime(args.end ?? args.to);
  const limit = Math.max(1, Math.min(Number(args.limit) || DEFAULT_FETCH_LIMIT, MAX_FETCH_LIMIT));

  let sql = `
    SELECT time, open, high, low, close, volume
    FROM candles
    WHERE symbol = ? AND timeframe = ?
  `;
  const params = [symbol, timeframe];
  if (start) {
    sql += ' AND time >= ?';
    params.push(start);
  }
  if (end) {
    sql += ' AND time < ?';
    params.push(end);
  }
  sql += ' ORDER BY time DESC LIMIT ?';
  params.push(limit);

  const rows = database.prepare(sql).all(...params);
  rows.reverse();

  return {
    ok: true,
    symbol,
    timeframe,
    source: 'cache',
    databasePath: cacheDbPath(),
    candles: rows.map((row) => ({
      time: row.time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume ?? 0,
    })),
  };
}

function upsertSyncState(database, state) {
  if (!state || typeof state !== 'object') return;
  const symbol = normaliseSymbol(state.symbol);
  const timeframe = normaliseTimeframe(state.timeframe);
  database.prepare(`
    INSERT INTO candle_sync_state(symbol, timeframe, last_time, bar_count, last_sync_at, last_mode, last_error)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, timeframe) DO UPDATE SET
      last_time = excluded.last_time,
      bar_count = excluded.bar_count,
      last_sync_at = excluded.last_sync_at,
      last_mode = excluded.last_mode,
      last_error = excluded.last_error
  `).run(
    symbol,
    timeframe,
    state.last_time ?? null,
    Number.isFinite(Number(state.bar_count)) ? Number(state.bar_count) : 0,
    state.last_sync_at ?? null,
    state.last_mode ?? null,
    state.last_error ?? null,
  );
}

function upsertCandles(args = {}) {
  const database = connect();
  const rows = Array.isArray(args.candles) ? args.candles : [];
  if (rows.length === 0) {
    return {
      ok: false,
      databasePath: cacheDbPath(),
      upserted: 0,
      skipped: 0,
      error: 'candles array is required and must not be empty',
    };
  }

  const defaultSymbol = args.symbol;
  const defaultTimeframe = args.timeframe;
  const defaultSource = args.source || 'unknown';
  const updatedAt = nowIso();
  const insert = database.prepare(`
    INSERT INTO candles(symbol, timeframe, time, open, high, low, close, volume, source, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, timeframe, time) DO UPDATE SET
      open = excluded.open,
      high = excluded.high,
      low = excluded.low,
      close = excluded.close,
      volume = excluded.volume,
      source = excluded.source,
      updated_at = excluded.updated_at
  `);

  let upserted = 0;
  let skipped = 0;
  database.exec('BEGIN IMMEDIATE');
  try {
    for (const raw of rows) {
      try {
        const candle = normaliseCandleRow(raw, {
          symbol: defaultSymbol,
          timeframe: defaultTimeframe,
          source: defaultSource,
        });
        insert.run(
          candle.symbol,
          candle.timeframe,
          candle.time,
          candle.open,
          candle.high,
          candle.low,
          candle.close,
          candle.volume,
          candle.source,
          updatedAt,
        );
        upserted += 1;
      } catch {
        skipped += 1;
      }
    }
    if (args.syncState) {
      upsertSyncState(database, args.syncState);
    }
    if (Array.isArray(args.syncStates)) {
      for (const state of args.syncStates) {
        upsertSyncState(database, state);
      }
    }
    database.exec('COMMIT');
  } catch (err) {
    database.exec('ROLLBACK');
    throw err;
  }

  return {
    ok: true,
    databasePath: cacheDbPath(),
    upserted,
    skipped,
  };
}

function getSyncState(symbol, timeframe) {
  const database = connect();
  const row = database.prepare(`
    SELECT symbol, timeframe, last_time, bar_count, last_sync_at, last_mode, last_error
    FROM candle_sync_state
    WHERE symbol = ? AND timeframe = ?
  `).get(normaliseSymbol(symbol), normaliseTimeframe(timeframe));
  return row || null;
}

function getCandleCacheStatus(args = {}) {
  const dbPath = cacheDbPath();
  const exists = fs.existsSync(dbPath);
  const base = {
    ok: true,
    databasePath: dbPath,
    exists,
    readable: false,
    totalCandles: null,
    symbolCandles: null,
  };

  if (!exists) {
    return base;
  }

  try {
    const database = connect();
    const totalRow = database.prepare('SELECT COUNT(*) AS n FROM candles').get();
    base.readable = true;
    base.totalCandles = totalRow?.n ?? 0;

    if (args.symbol && args.timeframe) {
      const symbol = normaliseSymbol(args.symbol);
      const timeframe = normaliseTimeframe(args.timeframe);
      const symRow = database.prepare(
        'SELECT COUNT(*) AS n, MIN(time) AS first_time, MAX(time) AS last_time FROM candles WHERE symbol = ? AND timeframe = ?',
      ).get(symbol, timeframe);
      base.symbol = symbol;
      base.timeframe = timeframe;
      base.symbolCandles = symRow?.n ?? 0;
      base.firstTime = symRow?.first_time ?? null;
      base.lastTime = symRow?.last_time ?? null;
      base.syncState = getSyncState(symbol, timeframe);
    }

    return base;
  } catch (err) {
    return {
      ...base,
      ok: false,
      error: err?.message || String(err),
    };
  }
}

function normaliseMappingRangeRow(raw = {}) {
  const symbol = normaliseSymbol(raw.symbol);
  const timeframe = normaliseTimeframe(raw.timeframe);
  const rangeHigh = Number(raw.range_high ?? raw.rangeHigh);
  const rangeLow = Number(raw.range_low ?? raw.rangeLow);
  if (!Number.isFinite(rangeHigh) || !Number.isFinite(rangeLow)) {
    throw new Error('range_high and range_low are required');
  }
  const parentId = resolveParentId(raw);
  return {
    id: String(raw.id ?? raw.range_id ?? `range_${crypto.randomUUID()}`),
    case_id: raw.case_id ?? raw.caseId ?? null,
    symbol,
    timeframe,
    structure_layer: raw.structure_layer ?? raw.structureLayer ?? null,
    range_high: rangeHigh,
    range_low: rangeLow,
    start_time: raw.start_time ?? raw.startTime ?? null,
    end_time: raw.end_time ?? raw.endTime ?? null,
    parent_id: parentId,
    status: String(raw.status || 'active'),
  };
}

function listMappingRanges(args = {}) {
  const database = connect();
  let sql = `
    SELECT id, case_id, symbol, timeframe, structure_layer, range_high, range_low,
           start_time, end_time, parent_id, origin, status, created_at, updated_at
    FROM mapping_ranges
    WHERE 1=1
  `;
  const params = [];
  if (args.symbol) {
    sql += ' AND symbol = ?';
    params.push(normaliseSymbol(args.symbol));
  }
  if (args.timeframe) {
    sql += ' AND timeframe = ?';
    params.push(normaliseTimeframe(args.timeframe));
  }
  if (args.case_id ?? args.caseId) {
    sql += ' AND case_id = ?';
    params.push(String(args.case_id ?? args.caseId));
  }
  sql += ' ORDER BY updated_at DESC';
  return database.prepare(sql).all(...params);
}

function buildRangeRehydrationReport(args = {}) {
  const symbol = normaliseSymbol(args.symbol);
  const timeframe = normaliseTimeframe(args.timeframe);
  const caseId = args.case_id ?? args.caseId ?? null;
  const database = connect();

  const totalRow = database.prepare('SELECT COUNT(*) AS n FROM mapping_ranges').get();
  const staleRow = database.prepare(`
    SELECT COUNT(*) AS n FROM mapping_ranges
    WHERE symbol != ? OR timeframe != ?
  `).get(symbol, timeframe);

  const listArgs = { symbol, timeframe };
  if (caseId) listArgs.case_id = String(caseId);
  const ranges = listMappingRanges(listArgs);

  const mismatchedRows = ranges.filter(
    (row) => normaliseSymbol(row.symbol) !== symbol || normaliseTimeframe(row.timeframe) !== timeframe,
  );

  const totalCount = Number(totalRow?.n ?? 0);
  const staleCount = Number(staleRow?.n ?? 0);
  const matchingCount = ranges.length - mismatchedRows.length;
  const shouldClearUi = (totalCount > 0 && matchingCount === 0) || mismatchedRows.length > 0;
  const contextMatch = !shouldClearUi;

  return {
    symbol,
    timeframe,
    case_id: caseId,
    context_match: contextMatch,
    should_clear_ui: shouldClearUi,
    matching_count: matchingCount,
    stale_count: staleCount,
    mismatched_count: mismatchedRows.length,
    total_count: totalCount,
  };
}

function listMappingRangesForRehydration(args = {}) {
  if (!args.symbol || !args.timeframe) {
    return {
      ok: false,
      databasePath: cacheDbPath(),
      ranges: [],
      rehydration: null,
      error: 'symbol and timeframe are required for rehydration validation',
    };
  }

  const rehydration = buildRangeRehydrationReport(args);
  const listArgs = {
    symbol: rehydration.symbol,
    timeframe: rehydration.timeframe,
  };
  if (rehydration.case_id) listArgs.case_id = rehydration.case_id;
  const ranges = rehydration.should_clear_ui ? [] : listMappingRanges(listArgs);

  return {
    ok: true,
    databasePath: cacheDbPath(),
    symbol: rehydration.symbol,
    timeframe: rehydration.timeframe,
    case_id: rehydration.case_id,
    ranges,
    rehydration,
  };
}

function validateMappingRangeUpsert(args = {}) {
  const range = normaliseMappingRangeRow(args.range || args);
  const validation = validateFractalRange(range);
  return {
    ok: true,
    databasePath: cacheDbPath(),
    range_id: range.id,
    upserted: validation.is_valid,
    ...validation,
  };
}

function upsertMappingRange(args = {}) {
  const range = normaliseMappingRangeRow(args.range || args);
  const validation = validateFractalRange(range);
  if (!validation.is_valid) {
    return {
      ok: true,
      ...validation,
      databasePath: cacheDbPath(),
      range_id: range.id,
      upserted: false,
    };
  }

  const database = connect();
  const updatedAt = nowIso();
  const createdAt = args.created_at ?? args.createdAt ?? updatedAt;
  const origin = validation.origin || 'Root';

  database.prepare(`
    INSERT INTO mapping_ranges(
      id, case_id, symbol, timeframe, structure_layer,
      range_high, range_low, start_time, end_time,
      parent_id, origin, status, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      case_id = excluded.case_id,
      symbol = excluded.symbol,
      timeframe = excluded.timeframe,
      structure_layer = excluded.structure_layer,
      range_high = excluded.range_high,
      range_low = excluded.range_low,
      start_time = excluded.start_time,
      end_time = excluded.end_time,
      parent_id = excluded.parent_id,
      origin = excluded.origin,
      status = excluded.status,
      updated_at = excluded.updated_at
  `).run(
    range.id,
    range.case_id,
    range.symbol,
    range.timeframe,
    range.structure_layer,
    range.range_high,
    range.range_low,
    range.start_time,
    range.end_time,
    range.parent_id,
    origin,
    range.status,
    createdAt,
    updatedAt,
  );

  return {
    ...validation,
    ok: true,
    upserted: true,
    databasePath: cacheDbPath(),
    range_id: range.id,
  };
}

module.exports = {
  cacheDbPath,
  initCandleCache,
  closeCandleCache,
  fetchCandles,
  upsertCandles,
  getSyncState,
  getCandleCacheStatus,
  listMappingRanges,
  listMappingRangesForRehydration,
  validateMappingRangeUpsert,
  upsertMappingRange,
  normaliseSymbol,
  normaliseTimeframe,
};
