/** Parent → child time coverage audit (movement gaps inside parent campaign window). */

import { childSpanExceedsParentCampaign, parentCampaignWindowMs } from './hierarchyIntegrity';

export type CoverageStatus =
  | 'NO_CHILDREN'
  | 'PARTIAL_COVERAGE'
  | 'HAS_GAPS'
  | 'COMPLETE_COVERAGE'
  | 'OUT_OF_WINDOW_CHILD';

export type CoverageGap = {
  startMs: number;
  endMs: number;
  startIso: string;
  endIso: string;
};

export type ParentChildCoverage = {
  parent_range_id: string;
  parent_layer: string;
  child_layer: string;
  child_count: number;
  coverage_percent: number;
  gap_count: number;
  first_gap_start: string | null;
  first_gap_end: string | null;
  first_gap_start_ms: number | null;
  first_gap_end_ms: number | null;
  coverage_status: CoverageStatus;
  gaps: CoverageGap[];
};

const PARENT_CHILD_PAIRS: ReadonlyArray<[string, string]> = [
  ['WEEKLY', 'DAILY'],
  ['DAILY', 'INTRADAY'],
  ['INTRADAY', 'MICRO'],
];

const TOLERANCE_MS_BY_CHILD: Record<string, number> = {
  DAILY: 24 * 60 * 60 * 1000,
  INTRADAY: 60 * 60 * 1000,
  MICRO: 15 * 60 * 1000,
};

function normalizeLayer(range: Record<string, unknown>): string {
  return String(range.structure_layer || range.layer || '').toUpperCase();
}

function isMajorRange(range: Record<string, unknown>): boolean {
  return String(range.range_scope || 'MAJOR').toUpperCase() !== 'MINOR';
}

function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

function toIso(ms: number): string {
  return new Date(ms).toISOString();
}

export function toleranceMsForChildLayer(childLayer: string): number {
  return TOLERANCE_MS_BY_CHILD[childLayer.toUpperCase()] ?? 24 * 60 * 60 * 1000;
}

export function childSpanMs(child: Record<string, unknown>): { startMs: number; endMs: number } {
  const startMs = parseTimeMs(
    child.range_start_time
    || child.active_from_time
    || child.range_high_time
    || child.range_low_time,
  ) ?? 0;
  const endMs = parseTimeMs(
    child.range_end_time
    || child.range_low_time
    || child.range_high_time
    || child.range_start_time
    || child.active_from_time,
  ) ?? startMs;
  return { startMs: Math.min(startMs, endMs), endMs: Math.max(endMs, startMs) };
}

export function getDirectChildren(
  parentId: string,
  childLayer: string,
  ranges: Record<string, unknown>[],
): Record<string, unknown>[] {
  return ranges.filter(
    (r) =>
      String(r.parent_range_id || '') === parentId
      && normalizeLayer(r) === childLayer
      && isMajorRange(r),
  );
}

function mergedCoverageMs(
  intervals: Array<{ startMs: number; endMs: number }>,
  parentStart: number,
  parentEnd: number,
): number {
  const clipped = intervals
    .map(({ startMs, endMs }) => ({
      startMs: Math.max(parentStart, startMs),
      endMs: Math.min(parentEnd, endMs),
    }))
    .filter(({ startMs, endMs }) => endMs > startMs)
    .sort((a, b) => a.startMs - b.startMs);

  let covered = 0;
  let cursor = parentStart;
  for (const span of clipped) {
    if (span.startMs > cursor) {
      // uncovered gap — skip
    }
    const start = Math.max(cursor, span.startMs);
    const end = Math.min(parentEnd, span.endMs);
    if (end > start) {
      covered += end - start;
      cursor = Math.max(cursor, end);
    }
  }
  return covered;
}

export function detectCoverageGaps(
  parentStartMs: number,
  parentEndMs: number,
  children: Array<{ startMs: number; endMs: number }>,
  toleranceMs: number,
): CoverageGap[] {
  if (parentEndMs <= parentStartMs) return [];
  const sorted = [...children].sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const gaps: CoverageGap[] = [];

  if (!sorted.length) {
    gaps.push({
      startMs: parentStartMs,
      endMs: parentEndMs,
      startIso: toIso(parentStartMs),
      endIso: toIso(parentEndMs),
    });
    return gaps;
  }

  if (sorted[0].startMs - parentStartMs > toleranceMs) {
    gaps.push({
      startMs: parentStartMs,
      endMs: sorted[0].startMs,
      startIso: toIso(parentStartMs),
      endIso: toIso(sorted[0].startMs),
    });
  }

  for (let i = 0; i < sorted.length - 1; i += 1) {
    const end = sorted[i].endMs;
    const nextStart = sorted[i + 1].startMs;
    if (nextStart - end > toleranceMs) {
      gaps.push({
        startMs: end,
        endMs: nextStart,
        startIso: toIso(end),
        endIso: toIso(nextStart),
      });
    }
  }

  const lastEnd = sorted[sorted.length - 1].endMs;
  if (parentEndMs - lastEnd > toleranceMs) {
    gaps.push({
      startMs: lastEnd,
      endMs: parentEndMs,
      startIso: toIso(lastEnd),
      endIso: toIso(parentEndMs),
    });
  }

  return gaps;
}

export function computeParentChildCoverage(
  parent: Record<string, unknown>,
  childLayer: string,
  ranges: Record<string, unknown>[],
): ParentChildCoverage {
  const parentId = String(parent.range_id || parent.id || '');
  const parentLayer = normalizeLayer(parent);
  const { startMs: parentStartMs, endMs: parentEndMs } = parentCampaignWindowMs(parent);
  const toleranceMs = toleranceMsForChildLayer(childLayer);
  const children = getDirectChildren(parentId, childLayer, ranges);
  const childSpans = children.map(childSpanMs);

  const outOfWindow = children.some((child) => childSpanExceedsParentCampaign(parent, {
    range_start_time: child.range_start_time as string | null,
    range_end_time: child.range_end_time as string | null,
    range_high_time: child.range_high_time as string | null,
    range_low_time: child.range_low_time as string | null,
    active_from_time: child.active_from_time as string | null,
  }));

  const parentDuration = Math.max(parentEndMs - parentStartMs, 1);
  const coveredMs = mergedCoverageMs(childSpans, parentStartMs, parentEndMs);
  const coveragePercent = Math.min(100, Math.round((coveredMs / parentDuration) * 100));
  const gaps = detectCoverageGaps(parentStartMs, parentEndMs, childSpans, toleranceMs);
  const firstGap = gaps[0] || null;

  let coverage_status: CoverageStatus;
  if (outOfWindow) {
    coverage_status = 'OUT_OF_WINDOW_CHILD';
  } else if (children.length === 0) {
    coverage_status = 'NO_CHILDREN';
  } else if (gaps.length === 0 && coveragePercent >= 100) {
    coverage_status = 'COMPLETE_COVERAGE';
  } else if (gaps.length > 0) {
    coverage_status = 'HAS_GAPS';
  } else {
    coverage_status = 'PARTIAL_COVERAGE';
  }

  return {
    parent_range_id: parentId,
    parent_layer: parentLayer,
    child_layer: childLayer,
    child_count: children.length,
    coverage_percent: children.length === 0 ? 0 : coveragePercent,
    gap_count: gaps.length,
    first_gap_start: firstGap?.startIso ?? null,
    first_gap_end: firstGap?.endIso ?? null,
    first_gap_start_ms: firstGap?.startMs ?? null,
    first_gap_end_ms: firstGap?.endMs ?? null,
    coverage_status,
    gaps,
  };
}

export function isCoverageIncomplete(status: CoverageStatus): boolean {
  return status !== 'COMPLETE_COVERAGE';
}

const COVERAGE_GAP_PRIORITY: Record<CoverageStatus, number> = {
  NO_CHILDREN: 0,
  HAS_GAPS: 1,
  PARTIAL_COVERAGE: 2,
  OUT_OF_WINDOW_CHILD: 3,
  COMPLETE_COVERAGE: 99,
};

export function coverageGapSortKey(coverage: ParentChildCoverage): number {
  return COVERAGE_GAP_PRIORITY[coverage.coverage_status] ?? 50;
}

export function buildHierarchyCoverageAudit(
  ranges: Record<string, unknown>[],
): ParentChildCoverage[] {
  const results: ParentChildCoverage[] = [];
  for (const [parentLayer, childLayer] of PARENT_CHILD_PAIRS) {
    const parents = ranges.filter(
      (r) => normalizeLayer(r) === parentLayer && isMajorRange(r),
    );
    for (const parent of parents) {
      results.push(computeParentChildCoverage(parent, childLayer, ranges));
    }
  }
  return results;
}

export function coverageExplorerBadgeLabel(
  childLabel: string,
  coverage: ParentChildCoverage,
): { label: string; complete: boolean } {
  switch (coverage.coverage_status) {
    case 'COMPLETE_COVERAGE':
      return { label: `${childLabel} complete`, complete: true };
    case 'NO_CHILDREN':
      return { label: `Needs ${childLabel}`, complete: false };
    case 'HAS_GAPS':
      return { label: `${childLabel} has gaps`, complete: false };
    case 'OUT_OF_WINDOW_CHILD':
      return { label: `${childLabel} out of window`, complete: false };
    case 'PARTIAL_COVERAGE':
    default:
      return { label: `${childLabel} coverage ${coverage.coverage_percent}%`, complete: false };
  }
}

export function parentChildPairForParentLayer(parentLayer: string): string | null {
  const pair = PARENT_CHILD_PAIRS.find(([p]) => p === parentLayer.toUpperCase());
  return pair ? pair[1] : null;
}
