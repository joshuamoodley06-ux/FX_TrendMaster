import { describe, expect, it } from 'vitest';
import {
  computeCampaignStatus,
  computeCampaignTierProgress,
  explorerParentTierBadge,
  getNextMappingTask,
  mappingTaskLabel,
} from './mappingCampaignManager';

const weekSpan = {
  range_start_time: '2025-01-01T00:00:00.000Z',
  range_end_time: '2025-03-01T00:00:00.000Z',
};

const fullDailySpan = {
  range_start_time: '2025-01-01T00:00:00.000Z',
  range_end_time: '2025-03-01T00:00:00.000Z',
};

describe('mappingCampaignManager', () => {
  const rangesWithWeeklyGap = [
    { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan },
    { range_id: 2, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan },
    {
      range_id: 10,
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      parent_range_id: 1,
      ...fullDailySpan,
    },
  ];

  it('getNextMappingTask returns MAP_DAILY for weekly without daily', () => {
    const result = getNextMappingTask(rangesWithWeeklyGap);
    expect(result.task).toBe('MAP_DAILY');
    expect(result.gap?.parentId).toBe('2');
    expect(result.targetParentLayer).toBe('WEEKLY');
  });

  it('getNextMappingTask returns CAMPAIGN_COMPLETE when hierarchy filled', () => {
    const ranges = [
      { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan },
      {
        range_id: 10,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        ...fullDailySpan,
      },
      {
        range_id: 44,
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 10,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-03-01T00:00:00.000Z',
      },
      {
        range_id: 99,
        structure_layer: 'MICRO',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 44,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-03-01T00:00:00.000Z',
      },
    ];
    const result = getNextMappingTask(ranges);
    expect(result.task).toBe('CAMPAIGN_COMPLETE');
    expect(result.gap).toBeNull();
  });

  it('getNextMappingTask does not create automatic Micro tasks for Intraday parents', () => {
    const ranges = [
      { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan },
      {
        range_id: 10,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        ...fullDailySpan,
      },
      {
        range_id: 44,
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 10,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-03-01T00:00:00.000Z',
      },
    ];
    const result = getNextMappingTask(ranges);
    expect(result.task).toBe('CAMPAIGN_COMPLETE');
    expect(result.gap).toBeNull();
  });

  it('prioritizes MAP_WEEKLY before MAP_DAILY when macro gaps exist', () => {
    const ranges = [
      { range_id: 100, structure_layer: 'MACRO', range_scope: 'MAJOR', status: 'ACTIVE' },
      { range_id: 101, structure_layer: 'MACRO', range_scope: 'MAJOR', status: 'ACTIVE' },
      { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', parent_range_id: 100 },
    ];
    const result = getNextMappingTask(ranges);
    expect(result.task).toBe('MAP_WEEKLY');
    expect(result.gap?.parentId).toBe('101');
  });

  it('computeCampaignTierProgress shows fraction and complete labels', () => {
    const tier = computeCampaignTierProgress(rangesWithWeeklyGap, 'WEEKLY', 'DAILY');
    expect(tier.mapped).toBe(1);
    expect(tier.total).toBe(2);
    expect(tier.badgeLabel).toBe('1/2 Daily');
    expect(tier.complete).toBe(false);

    const complete = computeCampaignTierProgress(
      [
        { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan },
        {
          range_id: 10,
          structure_layer: 'DAILY',
          range_scope: 'MAJOR',
          status: 'ACTIVE',
          parent_range_id: 1,
          ...fullDailySpan,
        },
      ],
      'WEEKLY',
      'DAILY',
    );
    expect(complete.badgeLabel).toBe('Daily Complete');
    expect(complete.complete).toBe(true);
  });

  it('computeCampaignStatus bundles tiers and next task', () => {
    const status = computeCampaignStatus(rangesWithWeeklyGap, 'all');
    expect(status.campaignComplete).toBe(false);
    expect(status.nextTask.task).toBe('MAP_DAILY');
    expect(status.tiers.some((t) => t.badgeLabel === '1/2 Daily')).toBe(true);
  });

  it('explorerParentTierBadge shows needs vs complete vs gaps', () => {
    const weekly = { range_id: 2, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan };
    expect(explorerParentTierBadge(weekly, rangesWithWeeklyGap)?.label).toBe('Needs Daily');

    const weeklyDone = { range_id: 1, structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', ...weekSpan };
    expect(explorerParentTierBadge(weeklyDone, rangesWithWeeklyGap)?.label).toBe('Daily complete');

    const weeklyPartial = {
      range_id: 3,
      structure_layer: 'WEEKLY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      ...weekSpan,
    };
    const partialRanges = [
      weeklyPartial,
      {
        range_id: 30,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 3,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-01-10T00:00:00.000Z',
      },
    ];
    expect(explorerParentTierBadge(weeklyPartial, partialRanges)?.label).toBe('Daily has gaps');
  });

  it('mappingTaskLabel humanizes task codes', () => {
    expect(mappingTaskLabel('MAP_MICRO')).toBe('Map Micro');
    expect(mappingTaskLabel('CAMPAIGN_COMPLETE')).toBe('Campaign Complete');
  });
});
