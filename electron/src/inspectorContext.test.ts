import { describe, expect, it } from 'vitest';
import {
  buildCandleSelectionHint,
  buildRangeSelectionHint,
  routeInspectorForCandleSelection,
  routeInspectorForRangeSelection,
} from './inspectorContext';

describe('inspectorContext', () => {
  it('routes candle selection to Mark / HTF', () => {
    expect(routeInspectorForCandleSelection()).toEqual({
      tab: 'mark',
      markWorkspaceMode: 'htf',
      reason: 'candle-selected',
    });
  });

  it('routes range selection to Mark / HTF', () => {
    expect(routeInspectorForRangeSelection()).toEqual({
      tab: 'mark',
      markWorkspaceMode: 'htf',
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
