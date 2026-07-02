/** Campaign-driven mapping — derived status from saved hierarchy only. */

import {
  computeMappingGaps,
  countDirectChildren,
  type MappingGap,
} from './mappingWorkflow';
import {
  computeParentChildCoverage,
  coverageExplorerBadgeLabel,
  parentChildPairForParentLayer,
} from './parentChildCoverage';

export type MappingTaskType =
  | 'MAP_WEEKLY'
  | 'MAP_DAILY'
  | 'MAP_INTRADAY'
  | 'MAP_MICRO'
  | 'CAMPAIGN_COMPLETE';

export type CampaignTierProgress = {
  taskType: MappingTaskType;
  parentLayer: string;
  childLayer: string;
  childLabel: string;
  mapped: number;
  total: number;
  complete: boolean;
  badgeLabel: string;
};

export type MappingTaskResult = {
  task: MappingTaskType;
  gap: MappingGap | null;
  targetLayer: string | null;
  targetParentId: string | null;
  targetParentLayer: string | null;
  targetLabel: string | null;
  summary: string;
};

export type CampaignStatus = {
  year: string;
  tiers: CampaignTierProgress[];
  nextTask: MappingTaskResult;
  campaignComplete: boolean;
};

const CHILD_LABEL: Record<string, string> = {
  WEEKLY: 'Weekly',
  DAILY: 'Daily',
  INTRADAY: 'Intraday',
  MICRO: 'Micro',
};

const TASK_BY_PAIR: Record<string, MappingTaskType> = {
  'MACRO|WEEKLY': 'MAP_WEEKLY',
  'WEEKLY|DAILY': 'MAP_DAILY',
  'DAILY|INTRADAY': 'MAP_INTRADAY',
};

const EXPLORER_CHILD_BY_PARENT: Record<string, [string, string]> = {
  MACRO: ['WEEKLY', 'Weekly'],
  WEEKLY: ['DAILY', 'Daily'],
  DAILY: ['INTRADAY', 'Intraday'],
};

function normalizeLayer(range: Record<string, unknown>): string {
  return String(range.structure_layer || range.layer || '').toUpperCase();
}

function isMajorRange(range: Record<string, unknown>): boolean {
  return String(range.range_scope || 'MAJOR').toUpperCase() !== 'MINOR';
}

function isMappingActiveRange(range: Record<string, unknown>): boolean {
  const status = String(range.status || '').toUpperCase();
  return status !== 'ABANDONED' && status !== 'ARCHIVED';
}

function rangeYearBucket(range: Record<string, unknown>): number | null {
  const parse = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null;
    const ms = Date.parse(String(value).includes('T') ? String(value) : String(value).replace(' ', 'T'));
    return Number.isFinite(ms) ? ms : null;
  };
  const activeFrom = parse(range.active_from_time);
  if (activeFrom !== null) return new Date(activeFrom).getUTCFullYear();
  const start = parse(range.range_start_time);
  if (start !== null) return new Date(start).getUTCFullYear();
  const rh = parse(range.range_high_time);
  const rl = parse(range.range_low_time);
  const span = [rh, rl].filter((x): x is number => x !== null);
  if (span.length) return new Date(Math.min(...span)).getUTCFullYear();
  return null;
}

export function filterRangesForCampaignYear(
  ranges: Record<string, unknown>[],
  yearFilter = 'all',
): Record<string, unknown>[] {
  if (!yearFilter || yearFilter === 'all') return ranges;
  const year = Number(yearFilter);
  if (!Number.isFinite(year)) return ranges;
  return ranges.filter((r) => rangeYearBucket(r) === year);
}

function activeMajorParents(
  ranges: Record<string, unknown>[],
  parentLayer: string,
): Record<string, unknown>[] {
  return ranges.filter(
    (r) => normalizeLayer(r) === parentLayer && isMajorRange(r) && isMappingActiveRange(r),
  );
}

export function computeCampaignTierProgress(
  ranges: Record<string, unknown>[],
  parentLayer: string,
  childLayer: string,
): CampaignTierProgress {
  const childLabel = CHILD_LABEL[childLayer] || childLayer;
  const taskType = TASK_BY_PAIR[`${parentLayer}|${childLayer}`] || 'CAMPAIGN_COMPLETE';
  const parents = activeMajorParents(ranges, parentLayer);
  const total = parents.length;
  const mapped = parents.filter((parent) => {
    const parentId = String(parent.range_id || parent.id || '');
    if (!parentId) return false;
    if (parentLayer === 'MACRO') {
      return countDirectChildren(parentId, childLayer, ranges) > 0;
    }
    const coverage = computeParentChildCoverage(parent, childLayer, ranges);
    return coverage.coverage_status === 'COMPLETE_COVERAGE';
  }).length;
  const complete = total > 0 && mapped === total;
  const badgeLabel = total === 0
    ? `No ${parentLayer}`
    : complete
      ? `${childLabel} Complete`
      : `${mapped}/${total} ${childLabel}`;
  return {
    taskType,
    parentLayer,
    childLayer,
    childLabel,
    mapped,
    total,
    complete,
    badgeLabel,
  };
}

export function computeCampaignStatus(
  ranges: Record<string, unknown>[],
  yearFilter = 'all',
): CampaignStatus {
  const scoped = filterRangesForCampaignYear(ranges, yearFilter);
  const tiers: CampaignTierProgress[] = [
    computeCampaignTierProgress(scoped, 'MACRO', 'WEEKLY'),
    computeCampaignTierProgress(scoped, 'WEEKLY', 'DAILY'),
    computeCampaignTierProgress(scoped, 'DAILY', 'INTRADAY'),
  ].filter((tier) => tier.total > 0);
  const nextTask = getNextMappingTask(ranges, { year: yearFilter });
  return {
    year: yearFilter,
    tiers,
    nextTask,
    campaignComplete: nextTask.task === 'CAMPAIGN_COMPLETE',
  };
}

function buildTaskResult(task: MappingTaskType, gap: MappingGap | null): MappingTaskResult {
  if (task === 'CAMPAIGN_COMPLETE' || !gap) {
    return {
      task: 'CAMPAIGN_COMPLETE',
      gap: null,
      targetLayer: null,
      targetParentId: null,
      targetParentLayer: null,
      targetLabel: null,
      summary: 'Campaign complete — all hierarchy tiers mapped for current scope.',
    };
  }
  return {
    task,
    gap,
    targetLayer: gap.expectedChildLayer,
    targetParentId: gap.parentId,
    targetParentLayer: gap.parentLayer,
    targetLabel: `${gap.expectedChildLayer} MAJOR under ${gap.parentLayer} #${gap.parentId}`,
    summary: gap.label,
  };
}

export function mappingTaskLabel(task: MappingTaskType): string {
  return ({
    MAP_WEEKLY: 'Map Weekly',
    MAP_DAILY: 'Map Daily',
    MAP_INTRADAY: 'Map Intraday',
    MAP_MICRO: 'Map Micro',
    CAMPAIGN_COMPLETE: 'Campaign Complete',
  })[task];
}

/**
 * Highest-priority unfinished mapping task for the campaign.
 * 1. Macro → Weekly
 * 2. Weekly → Daily
 * 3. Daily → Intraday
 */
export function getNextMappingTask(
  ranges: Record<string, unknown>[],
  options?: { year?: string },
): MappingTaskResult {
  const scoped = filterRangesForCampaignYear(ranges, options?.year || 'all');

  const weeklyGaps = computeMappingGaps(scoped, 'htf').filter(
    (g) => g.parentLayer === 'MACRO' && g.expectedChildLayer === 'WEEKLY',
  );
  if (weeklyGaps.length) return buildTaskResult('MAP_WEEKLY', weeklyGaps[0]);

  const dailyGaps = computeMappingGaps(scoped, 'htf').filter(
    (g) => g.parentLayer === 'WEEKLY' && g.expectedChildLayer === 'DAILY',
  );
  if (dailyGaps.length) return buildTaskResult('MAP_DAILY', dailyGaps[0]);

  const intradayGaps = computeMappingGaps(scoped, 'ltf').filter(
    (g) => g.parentLayer === 'DAILY' && g.expectedChildLayer === 'INTRADAY',
  );
  if (intradayGaps.length) return buildTaskResult('MAP_INTRADAY', intradayGaps[0]);

  return buildTaskResult('CAMPAIGN_COMPLETE', null);
}

/** Per-node explorer badge for a MAJOR parent (coverage-based). */
export function explorerParentTierBadge(
  parentRange: Record<string, unknown>,
  ranges: Record<string, unknown>[],
): { label: string; complete: boolean } | null {
  const parentLayer = normalizeLayer(parentRange);
  const pair = EXPLORER_CHILD_BY_PARENT[parentLayer];
  if (!pair || !isMajorRange(parentRange) || !isMappingActiveRange(parentRange)) return null;
  const [childLayer, label] = pair;
  const parentId = String(parentRange.range_id || parentRange.id || '');
  if (!parentId) return null;

  if (parentLayer === 'MACRO') {
    const count = countDirectChildren(parentId, childLayer, ranges);
    if (count > 0) return { label: `${label} Complete`, complete: true };
    return { label: `Needs ${label}`, complete: false };
  }

  const childLayerForCoverage = parentChildPairForParentLayer(parentLayer);
  if (!childLayerForCoverage) return null;
  const coverage = computeParentChildCoverage(parentRange, childLayerForCoverage, ranges);
  return coverageExplorerBadgeLabel(label, coverage);
}
