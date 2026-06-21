import { describe, expect, it } from 'vitest';
import {
  expandRangeSpanX,
  isIntradayNavTimeframe,
  rangeWindowFieldsFromSavedRange,
  resolveCandleWindowTargetRange,
  resolveRangeChartTimeframe,
} from './hierarchyRangeNavigation';

describe('hierarchyRangeNavigation', () => {
  it('resolveRangeChartTimeframe prefers layer default when chart TF missing', () => {
    expect(resolveRangeChartTimeframe({ structure_layer: 'INTRADAY' }, 'D1')).toBe('H1');
    expect(resolveRangeChartTimeframe({ structure_layer: 'WEEKLY', chart_timeframe: 'W1' }, 'D1')).toBe('W1');
  });

  it('rangeWindowFieldsFromSavedRange reads span fields', () => {
    expect(rangeWindowFieldsFromSavedRange({
      range_start_time: '2025-06-01T00:00:00.000Z',
      range_end_time: '2025-06-05T00:00:00.000Z',
    })).toEqual({
      start: '2025-06-01T00:00:00.000Z',
      end: '2025-06-05T00:00:00.000Z',
    });
  });

  it('resolveCandleWindowTargetRange prefers active intraday range on H1', () => {
    const ranges = [
      { range_id: '7', structure_layer: 'DAILY' },
      { range_id: '44', structure_layer: 'INTRADAY', parent_range_id: '7' },
    ];
    expect(resolveCandleWindowTargetRange('H1', ranges, '44', '7')?.range_id).toBe('44');
  });

  it('resolveCandleWindowTargetRange uses active daily on D1', () => {
    const ranges = [{ range_id: '12', structure_layer: 'DAILY' }];
    expect(resolveCandleWindowTargetRange('D1', ranges, '12', '')?.range_id).toBe('12');
  });

  it('expandRangeSpanX enforces minimum readable span', () => {
    const out = expandRangeSpanX(400, 410, 60, 900);
    expect(out.x2 - out.x1).toBeGreaterThanOrEqual(96);
  });

  it('isIntradayNavTimeframe recognizes intraday chart TFs', () => {
    expect(isIntradayNavTimeframe('H1')).toBe(true);
    expect(isIntradayNavTimeframe('W1')).toBe(false);
  });
});
