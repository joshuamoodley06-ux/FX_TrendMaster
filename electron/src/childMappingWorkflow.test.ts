import { describe, expect, it } from 'vitest';
import {
  buildChildMappingSession,
  expectedChildLayerForParent,
  openChildMappingSetup,
  parentResearchWindowFromRange,
} from './childMappingWorkflow';

describe('childMappingWorkflow', () => {
  const weeklyParent = {
    range_id: 42,
    structure_layer: 'WEEKLY',
    range_scope: 'MAJOR',
    range_start_time: '2025-06-01T00:00:00.000Z',
    range_end_time: '2025-06-30T00:00:00.000Z',
    range_high_price: 3400,
    range_low_price: 3200,
  };

  it('maps WEEKLY parent to DAILY child layer', () => {
    expect(expectedChildLayerForParent('WEEKLY')).toBe('DAILY');
  });

  it('builds research window from parent span', () => {
    const win = parentResearchWindowFromRange(weeklyParent);
    expect(win.dateFrom).toBe('2025-06-01');
    expect(win.dateTo).toBe('2025-06-30');
    expect(win.start).toContain('2025-06-01');
  });

  it('builds child mapping session for weekly parent', () => {
    const session = buildChildMappingSession(weeklyParent);
    expect(session).not.toBeNull();
    expect(session?.childLayer).toBe('DAILY');
    expect(session?.childSourceTf).toBe('D1');
    expect(session?.parentRangeId).toBe('42');
    expect(session?.phase).toBe('scanning');
  });

  it('openChildMappingSetup returns chart timeframe D1', () => {
    const setup = openChildMappingSetup(weeklyParent);
    expect(setup?.chartTimeframe).toBe('D1');
    expect(setup?.gap.expectedChildLayer).toBe('DAILY');
  });

  const dailyParent = {
    range_id: 12,
    structure_layer: 'DAILY',
    range_scope: 'MAJOR',
    range_start_time: '2025-06-03T00:00:00.000Z',
    range_end_time: '2025-06-07T00:00:00.000Z',
    range_high_price: 3380,
    range_low_price: 3320,
    parent_range_id: 42,
  };

  it('maps DAILY parent to INTRADAY child layer', () => {
    expect(expectedChildLayerForParent('DAILY')).toBe('INTRADAY');
  });

  it('builds child mapping session for daily parent', () => {
    const session = buildChildMappingSession(dailyParent);
    expect(session).not.toBeNull();
    expect(session?.childLayer).toBe('INTRADAY');
    expect(session?.childSourceTf).toBe('H1');
    expect(session?.parentRangeId).toBe('12');
  });

  it('openChildMappingSetup returns chart timeframe H1 for intraday', () => {
    const setup = openChildMappingSetup(dailyParent);
    expect(setup?.chartTimeframe).toBe('H1');
    expect(setup?.gap.expectedChildLayer).toBe('INTRADAY');
    expect(setup?.gap.parentLayer).toBe('DAILY');
  });

  const intradayParent = {
    range_id: 44,
    structure_layer: 'INTRADAY',
    range_scope: 'MAJOR',
    range_start_time: '2025-06-04T08:00:00.000Z',
    range_end_time: '2025-06-04T20:00:00.000Z',
    range_high_price: 3365,
    range_low_price: 3340,
    parent_range_id: 12,
  };

  it('maps INTRADAY parent to MICRO child layer', () => {
    expect(expectedChildLayerForParent('INTRADAY')).toBe('MICRO');
  });

  it('builds child mapping session for intraday parent', () => {
    const session = buildChildMappingSession(intradayParent);
    expect(session).not.toBeNull();
    expect(session?.childLayer).toBe('MICRO');
    expect(session?.childSourceTf).toBe('M15');
    expect(session?.parentRangeId).toBe('44');
  });

  it('openChildMappingSetup returns chart timeframe M15 for micro', () => {
    const setup = openChildMappingSetup(intradayParent);
    expect(setup?.chartTimeframe).toBe('M15');
    expect(setup?.gap.expectedChildLayer).toBe('MICRO');
    expect(setup?.gap.parentLayer).toBe('INTRADAY');
  });
});
