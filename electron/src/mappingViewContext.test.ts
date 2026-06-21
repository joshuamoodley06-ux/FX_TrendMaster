import { describe, expect, it } from 'vitest';
import {
  resolveChildChartTimeframe,
  resolveMappingViewChartTimeframe,
  resolveParentChartTimeframe,
} from './mappingViewContext';

describe('mappingViewContext', () => {
  it('resolves parent W1 when mapping DAILY', () => {
    expect(resolveParentChartTimeframe('DAILY')).toBe('W1');
    expect(resolveChildChartTimeframe('DAILY', 'D1')).toBe('D1');
    expect(resolveMappingViewChartTimeframe('parent', 'DAILY', 'D1')).toBe('W1');
    expect(resolveMappingViewChartTimeframe('child', 'DAILY', 'D1')).toBe('D1');
  });

  it('resolves parent D1 when mapping INTRADAY', () => {
    expect(resolveParentChartTimeframe('INTRADAY')).toBe('D1');
    expect(resolveMappingViewChartTimeframe('parent', 'INTRADAY', 'H1')).toBe('D1');
    expect(resolveMappingViewChartTimeframe('child', 'INTRADAY', 'H4')).toBe('H4');
  });
});
