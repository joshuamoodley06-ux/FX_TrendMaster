import { describe, expect, it } from 'vitest';
import { isChildMappingGap, nextMappingCampaignGap } from './mappingCampaignWorkflow';

const span = {
  range_start_time: '2025-01-01T00:00:00.000Z',
  range_end_time: '2025-03-01T00:00:00.000Z',
};

describe('mappingCampaignWorkflow', () => {
  const rangesWithWeeklyGap = [
    { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
    { range_id: 2, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
    {
      range_id: 10,
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      parent_range_id: 1,
      ...span,
    },
    { range_id: 20, structure_layer: 'DAILY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
  ];

  it('prioritizes Weekly without Daily before Daily without Intraday', () => {
    const gap = nextMappingCampaignGap(rangesWithWeeklyGap);
    expect(gap?.parentLayer).toBe('WEEKLY');
    expect(gap?.parentId).toBe('2');
  });

  it('prioritizes Daily without Intraday and ignores Intraday without Micro', () => {
    const ranges = [
      { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
      {
        range_id: 10,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        ...span,
      },
      { range_id: 20, structure_layer: 'DAILY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
      {
        range_id: 44,
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 10,
        ...span,
      },
      { range_id: 45, structure_layer: 'INTRADAY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
    ];
    const gap = nextMappingCampaignGap(ranges);
    expect(gap?.parentLayer).toBe('DAILY');
    expect(gap?.parentId).toBe('20');
  });

  it('returns complete when only Intraday without Micro remains', () => {
    const ranges = [
      { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...span },
      {
        range_id: 10,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        ...span,
      },
      {
        range_id: 44,
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 10,
        ...span,
      },
      {
        range_id: 45,
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 10,
        ...span,
      },
    ];
    const gap = nextMappingCampaignGap(ranges);
    expect(gap).toBeNull();
  });

  it('detects child mapping gaps', () => {
    expect(isChildMappingGap({ parentLayer: 'DAILY', expectedChildLayer: 'INTRADAY' } as any)).toBe(true);
    expect(isChildMappingGap({ parentLayer: 'INTRADAY', expectedChildLayer: 'MICRO' } as any)).toBe(false);
    expect(isChildMappingGap({ parentLayer: 'MICRO', expectedChildLayer: 'NANO' } as any)).toBe(false);
  });
});
