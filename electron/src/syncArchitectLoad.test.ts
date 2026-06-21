import { describe, expect, it, vi } from 'vitest';
import * as localResearchClient from './localResearchClient';
import * as rangeRehydrationService from './rangeRehydrationService';
import { loadSessionFromSyncArchitect } from './syncArchitectLoad';
import * as syncService from './syncService';

describe('loadSessionFromSyncArchitect', () => {
  it('blocks warm boot candle rehydration when mapping_ranges context mismatches', async () => {
    vi.spyOn(syncService, 'syncTimeframeFromVps').mockResolvedValue({
      timeframe: 'D1',
      ok: true,
      fetched: 10,
      upserted: 10,
      skipped: 0,
    });
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
    expect(fetchLocal).not.toHaveBeenCalled();

    vi.restoreAllMocks();
  });
});
