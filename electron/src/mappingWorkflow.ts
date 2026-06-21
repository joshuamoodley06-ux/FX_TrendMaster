/** Master mapping workflow helpers — UI-side gap queue, no Python. */

import {
  computeParentChildCoverage,
  coverageGapSortKey,
  isCoverageIncomplete,
  type ParentChildCoverage,
} from './parentChildCoverage';

export type ExplorerMappingMode = 'htf' | 'ltf';

export type MappingGap = {
  parentId: string;
  parentRange: Record<string, unknown>;
  parentLayer: string;
  expectedChildLayer: string;
  label: string;
  coverage?: ParentChildCoverage;
};

const HTF_LAYERS = ['MACRO', 'WEEKLY', 'DAILY'] as const;

const HTF_GAP_PAIRS: ReadonlyArray<[string, string]> = [
  ['MACRO', 'WEEKLY'],
  ['WEEKLY', 'DAILY'],
];

const LTF_GAP_PAIRS: ReadonlyArray<[string, string]> = [
  ['DAILY', 'INTRADAY'],
  ['INTRADAY', 'MICRO'],
];

export function buildMasterCaseName(symbol: string, startYear = 2019, endYear = 2026): string {
  const sym = String(symbol || 'XAUUSD').toUpperCase();
  return `${sym}_MASTER_${startYear}_${endYear}`;
}

function normalizeLayer(range: Record<string, unknown>): string {
  return String(range.structure_layer || range.layer || '').toUpperCase();
}

function normalizeRangeScope(range: Record<string, unknown>): string {
  const scope = String(range.range_scope || 'MAJOR').toUpperCase();
  return scope === 'MINOR' ? 'MINOR' : 'MAJOR';
}

function isMajorRange(range: Record<string, unknown>): boolean {
  return normalizeRangeScope(range) === 'MAJOR';
}

function rangeStartSortKey(range: Record<string, unknown>): number {
  const raw = range.range_start_time || range.active_from_time || range.range_high_time || 0;
  const ms = new Date(String(raw)).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

function isMappingActiveRange(range: Record<string, unknown>): boolean {
  const status = String(range.status || '').toUpperCase();
  return status !== 'ABANDONED' && status !== 'ARCHIVED';
}

export function filterRangesForExplorerMode(
  ranges: Record<string, unknown>[],
  mode: ExplorerMappingMode,
): Record<string, unknown>[] {
  if (mode !== 'htf') return ranges;
  return ranges.filter((r) => HTF_LAYERS.includes(normalizeLayer(r) as typeof HTF_LAYERS[number]));
}

export function countDirectChildren(
  parentId: string,
  childLayer: string,
  ranges: Record<string, unknown>[],
): number {
  return ranges.filter(
    (r) =>
      String(r.parent_range_id || '') === parentId
      && normalizeLayer(r) === childLayer
      && isMajorRange(r),
  ).length;
}

export function computeMappingGaps(
  ranges: Record<string, unknown>[],
  mode: ExplorerMappingMode,
): MappingGap[] {
  const pairs = mode === 'htf' ? HTF_GAP_PAIRS : LTF_GAP_PAIRS;
  const gaps: MappingGap[] = [];

  for (const [parentLayer, childLayer] of pairs) {
    const parents = ranges
      .filter((r) => normalizeLayer(r) === parentLayer && isMajorRange(r) && isMappingActiveRange(r))
      .sort(
        (a, b) =>
          rangeStartSortKey(a) - rangeStartSortKey(b) ||
          String(a.range_id || a.id).localeCompare(String(b.range_id || b.id)),
      );

    const pairGaps: MappingGap[] = [];

    for (const parent of parents) {
      const parentId = String(parent.range_id || parent.id || '');
      if (!parentId) continue;

      if (parentLayer === 'MACRO') {
        if (countDirectChildren(parentId, childLayer, ranges) > 0) continue;
        pairGaps.push({
          parentId,
          parentRange: parent,
          parentLayer,
          expectedChildLayer: childLayer,
          label: `${parentLayer} MAJOR #${parentId} → map ${childLayer} MAJOR`,
        });
        continue;
      }

      const coverage = computeParentChildCoverage(parent, childLayer, ranges);
      if (!isCoverageIncomplete(coverage.coverage_status)) continue;

      const gapNote = coverage.first_gap_start
        ? ` · gap ${coverage.first_gap_start.slice(0, 10)} → ${(coverage.first_gap_end || '').slice(0, 10)}`
        : coverage.coverage_status === 'NO_CHILDREN'
          ? ''
          : ` · ${coverage.coverage_percent}% covered`;
      pairGaps.push({
        parentId,
        parentRange: parent,
        parentLayer,
        expectedChildLayer: childLayer,
        label: `${parentLayer} MAJOR #${parentId} → map ${childLayer} MAJOR${gapNote}`,
        coverage,
      });
    }

    pairGaps.sort((a, b) => {
      const priA = a.coverage ? coverageGapSortKey(a.coverage) : 0;
      const priB = b.coverage ? coverageGapSortKey(b.coverage) : 0;
      if (priA !== priB) return priA - priB;
      return rangeStartSortKey(a.parentRange) - rangeStartSortKey(b.parentRange)
        || String(a.parentId).localeCompare(String(b.parentId));
    });
    gaps.push(...pairGaps);
  }

  return gaps;
}
