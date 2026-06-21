import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  buildStaleMappingRangesRehydrationFixture,
  createGhostMapStudioUiState,
  executeMapStudioSessionLoad,
  hasGhostMapStudioData,
  seedGhostMappingLocalStorage,
} from './mapStudioStaleRehydration';
import {
  mappingEventsContainerKey,
  readMappingEventsForContainer,
} from './mappingEventsPersistence';
import * as rangeRehydrationService from './rangeRehydrationService';
import * as syncService from './syncService';

function mockLocalStorage() {
  const bucket: Record<string, string> = {};
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => bucket[key] ?? null,
    setItem: (key: string, value: string) => { bucket[key] = value; },
    removeItem: (key: string) => { delete bucket[key]; },
    clear: () => { Object.keys(bucket).forEach((k) => delete bucket[k]); },
  });
}

describe('Integration Test — Stale Rehydration Scenario', () => {
  const symbol = 'XAUUSD';
  const timeframe = 'D1';
  const caseId = 'stale-case-ghost-1';
  const scopeKey = mappingEventsContainerKey(symbol, caseId);

  beforeEach(() => {
    mockLocalStorage();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('clears ghost RH/RL, ranges, overlays, and blocks chart on stale mapping_ranges cache', async () => {
    seedGhostMappingLocalStorage(symbol, caseId, timeframe);
    expect(readMappingEventsForContainer(scopeKey)[timeframe]?.length).toBe(1);

    const priorUi = createGhostMapStudioUiState(timeframe);
    expect(hasGhostMapStudioData(priorUi)).toBe(true);

    vi.spyOn(syncService, 'syncTimeframeFromVps').mockResolvedValue({
      timeframe,
      ok: true,
      fetched: 0,
      upserted: 0,
      skipped: 0,
    });
    vi.spyOn(rangeRehydrationService, 'validateRangeRehydration').mockResolvedValue(
      buildStaleMappingRangesRehydrationFixture(symbol, timeframe, caseId),
    );

    const outcome = await executeMapStudioSessionLoad({
      symbol,
      timeframe,
      caseId,
      priorUi,
    });

    expect(outcome.blocked).toBe(true);
    expect(outcome.sync.should_clear_ui).toBe(true);
    expect(outcome.sync.candles).toEqual([]);
    expect(outcome.ui.candles).toEqual([]);
    expect(outcome.ui.chartBlocked).toBe(true);
    expect(outcome.ui.rhAnchor.price).toBe('');
    expect(outcome.ui.rlAnchor.price).toBe('');
    expect(outcome.ui.structuralRanges).toEqual([]);
    expect(outcome.ui.savedStructuralRanges).toEqual([]);
    expect(outcome.ui.activeStructuralRangeId).toBe('');
    expect(outcome.ui.eventsByTf).toEqual({});
    expect(hasGhostMapStudioData(outcome.ui)).toBe(false);
    expect(readMappingEventsForContainer(scopeKey)).toEqual({});

    // eslint-disable-next-line no-console
    console.log('Integration Test [PASS].');
  });
});
