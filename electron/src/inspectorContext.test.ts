import { describe, expect, it } from 'vitest';
import {
  buildCandleSelectionHint,
  buildRangeSelectionHint,
  routeInspectorForCandleSelection,
  routeInspectorForRangeSelection,
} from './inspectorContext';

describe('inspectorContext', () => {
  it('routes candle selection to Campaign (chart-native marking)', () => {
    expect(routeInspectorForCandleSelection()).toEqual({
      tab: 'campaign',
      reason: 'candle-selected',
    });
  });

  it('routes range selection to Hierarchy browse', () => {
    expect(routeInspectorForRangeSelection()).toEqual({
      tab: 'gps',
      reason: 'range-selected',
    });
  });

  it('builds candle hint metadata', () => {
    const hint = buildCandleSelectionHint({ timeLabel: '2026-01-02', price: 2650.5, timeframe: 'D1' });
    expect(hint.kind).toBe('candle');
    expect(hint.detail).toContain('2650.50');
    expect(hint.detail).toContain('D1');
  });

  it('builds range hint metadata', () => {
    const hint = buildRangeSelectionHint({
      rangeId: '42',
      structureLayer: 'WEEKLY',
      rangeScope: 'MAJOR',
      rangeHigh: 2700,
      rangeLow: 2500,
    });
    expect(hint.kind).toBe('range');
    expect(hint.title).toContain('42');
    expect(hint.detail).toContain('WEEKLY');
  });
});
