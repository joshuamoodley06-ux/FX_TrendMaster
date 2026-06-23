import { describe, expect, it, vi } from 'vitest';
import * as localResearchClient from './localResearchClient';
import * as rangeRehydrationService from './rangeRehydrationService';
import { loadSessionFromSyncArchitect } from './syncArchitectLoad';

describe('loadSessionFromSyncArchitect', () => {
  it('blocks warm boot candle rehydration when mapping_ranges context mismatches', async () => {
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'D1',
      ranges: [],
      rehydration: {
        context_match: false,
        should_clear_ui: true,
        matching_count: 0,
        stale_count: 1,
        mismatched_count: 0,
        total_count: 1,
      },
    });
    const fetchLocal = vi.spyOn(localResearchClient, 'fetchLocalCandles');

    const result = await loadSessionFromSyncArchitect('XAUUSD', 'D1', { caseId: 'case-1' });
    expect(result.should_clear_ui).toBe(true);
    expect(result.candles).toEqual([]);
    expect(result.synced).toBe(false);
    expect(fetchLocal).not.toHaveBeenCalled();

    vi.restoreAllMocks();
  });

  it('reads local candles without VPS sync', async () => {
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'H1',
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
      timeframe: 'H1',
      source: 'cache',
      databasePath: 'C:\\cache\\candle_cache.db',
      candles: [{ time: '2024.01.02 10:00', open: 1, high: 2, low: 0.5, close: 1.5 }],
    });

    const result = await loadSessionFromSyncArchitect('XAUUSD', 'H1');
    expect(result.ok).toBe(true);
    expect(result.synced).toBe(false);
    expect(result.candles).toHaveLength(1);
    vi.restoreAllMocks();
  });
});
