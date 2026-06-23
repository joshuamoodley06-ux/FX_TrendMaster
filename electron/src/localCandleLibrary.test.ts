import { describe, expect, it, vi } from 'vitest';
import * as localResearchClient from './localResearchClient';
import * as rangeRehydrationService from './rangeRehydrationService';
import * as syncService from './syncService';
import {
  CHART_LIBRARY_TIMEFRAMES,
  candlesChanged,
  formatMissingCandleMessage,
  loadChartCandlesLocalFirst,
  mergeParsedCandleRowsForChart,
} from './localCandleLibrary';

describe('localCandleLibrary', () => {
  it('loadChartCandlesLocalFirst reads local library without VPS when candles exist', async () => {
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'H4',
      ranges: [],
      rehydration: {
        context_match: true,
        should_clear_ui: false,
        matching_count: 1,
        stale_count: 0,
        mismatched_count: 0,
        total_count: 1,
      },
    });
    vi.spyOn(localResearchClient, 'fetchLocalCandles').mockResolvedValue({
      ok: true,
      symbol: 'XAUUSD',
      timeframe: 'H4',
      source: 'cache',
      databasePath: 'C:\\cache\\candle_cache.db',
      candles: [{ time: '2024.01.02 08:00', open: 1, high: 2, low: 0.5, close: 1.5 }],
    });
    vi.spyOn(localResearchClient, 'getLocalCandlesStatus').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      exists: true,
      readable: true,
      symbolCandles: 120,
      syncState: { symbol: 'XAUUSD', timeframe: 'H4', last_sync_at: '2025-06-01T00:00:00.000Z', last_mode: 'incremental_delta' },
    });
    const vps = vi.spyOn(syncService, 'syncMissingWindowFromVps');

    const result = await loadChartCandlesLocalFirst({
      symbol: 'XAUUSD',
      timeframe: 'H4',
    });

    expect(result.ok).toBe(true);
    expect(result.source).toBe('local');
    expect(result.candles).toHaveLength(1);
    expect(vps).not.toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it('requests missing window from VPS only when local window is empty', async () => {
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'M15',
      ranges: [],
      rehydration: {
        context_match: true,
        should_clear_ui: false,
        matching_count: 0,
        stale_count: 0,
        mismatched_count: 0,
        total_count: 0,
      },
    });
    vi.spyOn(localResearchClient, 'fetchLocalCandles')
      .mockResolvedValueOnce({
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'M15',
        source: 'cache',
        databasePath: 'C:\\cache\\candle_cache.db',
        candles: [],
      })
      .mockResolvedValueOnce({
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'M15',
        source: 'cache',
        databasePath: 'C:\\cache\\candle_cache.db',
        candles: [{ time: '2024.01.02 08:15', open: 1, high: 2, low: 0.5, close: 1.5 }],
      });
    vi.spyOn(localResearchClient, 'getLocalCandlesStatus').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      exists: true,
      readable: true,
      symbolCandles: 1,
    });
    const vps = vi.spyOn(syncService, 'syncMissingWindowFromVps').mockResolvedValue({
      timeframe: 'M15',
      ok: true,
      fetched: 1,
      upserted: 1,
      skipped: 0,
    });

    const result = await loadChartCandlesLocalFirst({
      symbol: 'XAUUSD',
      timeframe: 'M15',
      window: { start: '2024-01-01', end: '2024-01-10' },
    });

    expect(vps).toHaveBeenCalledTimes(1);
    expect(result.source).toBe('local+missing_window');
    expect(result.ok).toBe(true);
    vi.restoreAllMocks();
  });

  it('does not request missing window from VPS when explicitly localOnly', async () => {
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'H1',
      ranges: [],
      rehydration: {
        context_match: true,
        should_clear_ui: false,
        matching_count: 0,
        stale_count: 0,
        mismatched_count: 0,
        total_count: 0,
      },
    });
    vi.spyOn(localResearchClient, 'fetchLocalCandles').mockResolvedValue({
      ok: true,
      symbol: 'XAUUSD',
      timeframe: 'H1',
      source: 'cache',
      databasePath: 'C:\\cache\\candle_cache.db',
      candles: [],
    });
    vi.spyOn(localResearchClient, 'getLocalCandlesStatus').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      exists: true,
      readable: true,
      symbolCandles: 3271,
    });
    const vps = vi.spyOn(syncService, 'syncMissingWindowFromVps');

    const result = await loadChartCandlesLocalFirst({
      symbol: 'XAUUSD',
      timeframe: 'H1',
      window: { start: '2024-10-27', end: '2024-12-10' },
      localOnly: true,
    });

    expect(vps).not.toHaveBeenCalled();
    expect(result.ok).toBe(false);
    expect(result.source).toBe('none');
    vi.restoreAllMocks();
  });

  it('formatMissingCandleMessage surfaces sync/import guidance', () => {
    expect(formatMissingCandleMessage('M15')).toMatch(/No M15 candles available/);
    expect(formatMissingCandleMessage('M15')).toMatch(/Sync\/import required/);
  });

  it('candlesChanged detects latest-bar OHLC update without duplicate row', () => {
    const before = [{ time: '2024.01.02 08:00', open: 1, high: 2, low: 0.5, close: 1.5 }];
    const afterSame = [{ time: '2024.01.02 08:00', open: 1, high: 2, low: 0.5, close: 1.5 }];
    const afterUpdated = [{ time: '2024.01.02 08:00', open: 1, high: 2.2, low: 0.5, close: 1.8 }];
    expect(candlesChanged(before, afterSame)).toBe(false);
    expect(candlesChanged(before, afterUpdated)).toBe(true);
  });

  it('mergeParsedCandleRowsForChart upserts by timestamp key', () => {
    const merged = mergeParsedCandleRowsForChart(
      [{ time: 'a', open: 1, high: 1, low: 1, close: 1 }],
      [{ time: 'a', open: 1, high: 2, low: 1, close: 1.5 }, { time: 'b', open: 2, high: 3, low: 2, close: 2.5 }],
    );
    expect(merged).toHaveLength(2);
    expect(merged[0].high).toBe(2);
  });

  it('CHART_LIBRARY_TIMEFRAMES excludes M1 and includes M15', () => {
    expect(CHART_LIBRARY_TIMEFRAMES).toContain('M15');
    expect(CHART_LIBRARY_TIMEFRAMES).not.toContain('M1');
  });
});
