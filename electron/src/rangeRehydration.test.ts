import { describe, expect, it, vi } from 'vitest';
import {
  ghostRangeUiClearMessage,
  shouldClearRangeUiFromRehydration,
  validateRangeRehydration,
} from './rangeRehydrationService';

describe('rangeRehydrationService', () => {
  it('flags stale cache for UI clearing', () => {
    expect(shouldClearRangeUiFromRehydration({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      ranges: [],
      rehydration: {
        context_match: false,
        should_clear_ui: true,
        matching_count: 0,
        stale_count: 2,
        mismatched_count: 0,
        total_count: 2,
      },
    })).toBe(true);
  });

  it('allows render when cache matches current symbol/timeframe', () => {
    expect(shouldClearRangeUiFromRehydration({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      ranges: [{ id: 'r1', symbol: 'XAUUSD', timeframe: 'D1', range_high: 2400, range_low: 2300 }],
      rehydration: {
        context_match: true,
        should_clear_ui: false,
        matching_count: 1,
        stale_count: 0,
        mismatched_count: 0,
        total_count: 1,
      },
    })).toBe(false);
  });

  it('calls electronAPI.ranges.list with rehydration validation', async () => {
    const list = vi.fn().mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      symbol: 'XAUUSD',
      timeframe: 'D1',
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
    vi.stubGlobal('window', {
      electronAPI: { ranges: { list } },
    });

    const result = await validateRangeRehydration('xauusd', 'd1', 'case-1');
    expect(list).toHaveBeenCalledWith({
      symbol: 'XAUUSD',
      timeframe: 'D1',
      case_id: 'case-1',
      validateRehydration: true,
    });
    expect(result.ok).toBe(true);

    vi.unstubAllGlobals();
  });

  it('builds a clear-state message for ghost range UI', () => {
    expect(ghostRangeUiClearMessage('xauusd', 'd1')).toContain('XAUUSD D1');
  });
});
