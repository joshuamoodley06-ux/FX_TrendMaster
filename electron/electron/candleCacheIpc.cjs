const { ipcMain } = require('electron');
const {
  fetchCandles,
  upsertCandles,
  initCandleCache,
  cacheDbPath,
  getCandleCacheStatus,
  validateMappingRangeUpsert,
  upsertMappingRange,
  listMappingRanges,
  listMappingRangesForRehydration,
} = require('./candleCache.cjs');
const { validateFractalRange } = require('./fractalRangeValidation.cjs');

function buildRangeValidationFailure(err, args) {
  return {
    ok: false,
    is_valid: false,
    origin: null,
    flags: ['error'],
    databasePath: cacheDbPath(),
    range_id: args?.range?.id ?? args?.id ?? null,
    reason: err?.message || String(err),
    error: err?.message || String(err),
  };
}

function registerCandleCacheIpc() {
  initCandleCache();

  ipcMain.handle('candles:fetch', async (_event, args) => {
    try {
      if (!args?.symbol || !args?.timeframe) {
        return {
          ok: false,
          symbol: String(args?.symbol || ''),
          timeframe: String(args?.timeframe || ''),
          source: 'cache',
          databasePath: cacheDbPath(),
          candles: [],
          error: 'symbol and timeframe are required',
        };
      }
      return fetchCandles(args);
    } catch (err) {
      return {
        ok: false,
        symbol: String(args?.symbol || ''),
        timeframe: String(args?.timeframe || ''),
        source: 'cache',
        databasePath: cacheDbPath(),
        candles: [],
        error: err?.message || String(err),
      };
    }
  });

  ipcMain.handle('candles:upsert', async (_event, args) => {
    try {
      return upsertCandles(args || {});
    } catch (err) {
      return {
        ok: false,
        databasePath: cacheDbPath(),
        upserted: 0,
        skipped: 0,
        error: err?.message || String(err),
      };
    }
  });

  ipcMain.handle('candles:status', async (_event, args) => {
    try {
      return getCandleCacheStatus(args || {});
    } catch (err) {
      return {
        ok: false,
        databasePath: cacheDbPath(),
        exists: false,
        readable: false,
        error: err?.message || String(err),
      };
    }
  });

  ipcMain.handle('ranges:validate', async (_event, args) => {
    try {
      return validateMappingRangeUpsert(args || {});
    } catch (err) {
      return buildRangeValidationFailure(err, args || {});
    }
  });

  ipcMain.handle('ranges:upsert', async (_event, args) => {
    try {
      return upsertMappingRange(args || {});
    } catch (err) {
      return {
        ...buildRangeValidationFailure(err, args || {}),
        upserted: false,
      };
    }
  });

  ipcMain.handle('ranges:list', async (_event, args) => {
    try {
      const payload = args || {};
      if (payload.validateRehydration || (payload.symbol && payload.timeframe)) {
        return listMappingRangesForRehydration(payload);
      }
      const rows = listMappingRanges(payload);
      return {
        ok: true,
        databasePath: cacheDbPath(),
        ranges: rows,
      };
    } catch (err) {
      return {
        ok: false,
        databasePath: cacheDbPath(),
        ranges: [],
        rehydration: null,
        error: err?.message || String(err),
      };
    }
  });
}

module.exports = {
  registerCandleCacheIpc,
  validateFractalRange,
};
