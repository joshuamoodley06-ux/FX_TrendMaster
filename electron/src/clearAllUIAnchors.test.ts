import { describe, expect, it, vi } from 'vitest';
import {
  STALE_CACHE_BLOCKED,
  clearAllUIAnchors,
  navChromeExcludedFromClearHandlers,
} from './clearAllUIAnchors';

describe('clearAllUIAnchors', () => {
  it('keeps nav chrome handler keys out of the purge contract', () => {
    expect(navChromeExcludedFromClearHandlers).toBe(true);
  });

  it('exports STALE_CACHE_BLOCKED sentinel', () => {
    expect(STALE_CACHE_BLOCKED).toBe('STALE_CACHE_BLOCKED');
  });

  it('purges structural ranges, events, and anchor drafts', () => {
    const setActiveStructuralRangeId = vi.fn();
    const setSelectedParentRangeId = vi.fn();
    const setStructuralRanges = vi.fn();
    const setSavedStructuralRanges = vi.fn();
    const setStructuralAnchorsByLayer = vi.fn();
    const setSessionEventIds = vi.fn();
    const setEventsByTf = vi.fn();
    const clearEventsByTfRef = vi.fn();
    const setRangeByTf = vi.fn();
    const setRangeWindowByTf = vi.fn();
    const setMeasurementRangeByTf = vi.fn();
    const setRhAnchor = vi.fn();
    const setRlAnchor = vi.fn();
    const setStructuralRangeDraftDirty = vi.fn();
    const clearMappingEventsBucket = vi.fn();

    clearAllUIAnchors({
      setActiveStructuralRangeId,
      setSelectedParentRangeId,
      setStructuralRanges,
      setSavedStructuralRanges,
      setStructuralAnchorsByLayer,
      setSessionEventIds,
      setEventsByTf,
      clearEventsByTfRef,
      setRangeByTf,
      setRangeWindowByTf,
      setMeasurementRangeByTf,
      setRhAnchor,
      setRlAnchor,
      setStructuralRangeDraftDirty,
      clearMappingEventsBucket,
      mappingEventsScopeKey: 'XAUUSD|case-1',
    });

    expect(setSavedStructuralRanges).toHaveBeenCalledWith([]);
    expect(setEventsByTf).toHaveBeenCalledWith({});
    expect(clearEventsByTfRef).toHaveBeenCalled();
    expect(clearMappingEventsBucket).toHaveBeenCalledWith('XAUUSD|case-1');
    expect(setRhAnchor).toHaveBeenCalledWith({ price: '', time: '', candle: null });
    expect(setRlAnchor).toHaveBeenCalledWith({ price: '', time: '', candle: null });
    expect(setStructuralRangeDraftDirty).toHaveBeenCalledWith(false);
  });
});
