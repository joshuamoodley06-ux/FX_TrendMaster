export type HierarchyLayer = 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO';
export type TimeInterval = { startMs: number; endMs: number };
export type CoverageGap = TimeInterval & { startIso: string; endIso: string };
export type HierarchyCoverageRow = {
  parent: Record<string, unknown>; parentId: string; parentLayer: HierarchyLayer;
  childLayer: HierarchyLayer | null; coveredMs: number; durationMs: number;
  coveragePercent: number | null; gaps: CoverageGap[];
};
export type CoverageYearRange = { fromYear: number; toYear: number };

const CHILD_LAYER: Record<HierarchyLayer, HierarchyLayer | null> = {
  WEEKLY: 'DAILY', DAILY: 'INTRADAY', INTRADAY: 'MICRO', MICRO: null,
};

function parseTime(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const parsed = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(parsed) ? parsed : null;
}
function layerOf(range: Record<string, unknown>): HierarchyLayer | null {
  const layer = String(range.structure_layer || range.layer || '').toUpperCase();
  return layer in CHILD_LAYER ? layer as HierarchyLayer : null;
}
function rangeIdOf(range: Record<string, unknown>): string { return String(range.range_id || range.id || ''); }
function isMajor(range: Record<string, unknown>): boolean { return String(range.range_scope || 'MAJOR').toUpperCase() !== 'MINOR'; }

export function rangeInterval(range: Record<string, unknown>): TimeInterval | null {
  const start = parseTime(range.range_start_time || range.active_from_time || range.range_high_time || range.range_low_time);
  const end = parseTime(range.range_end_time || range.inactive_from_time || range.range_low_time || range.range_high_time);
  if (start === null || end === null || start === end) return null;
  return { startMs: Math.min(start, end), endMs: Math.max(start, end) };
}

export function mergeClippedIntervals(intervals: TimeInterval[], window: TimeInterval): TimeInterval[] {
  const clipped = intervals.map((interval) => ({
    startMs: Math.max(window.startMs, Math.min(interval.startMs, interval.endMs)),
    endMs: Math.min(window.endMs, Math.max(interval.startMs, interval.endMs)),
  })).filter((interval) => interval.endMs > interval.startMs)
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const merged: TimeInterval[] = [];
  for (const interval of clipped) {
    const previous = merged[merged.length - 1];
    if (!previous || interval.startMs > previous.endMs) merged.push({ ...interval });
    else previous.endMs = Math.max(previous.endMs, interval.endMs);
  }
  return merged;
}

export function uncoveredIntervals(window: TimeInterval, covered: TimeInterval[]): CoverageGap[] {
  if (window.endMs <= window.startMs) return [];
  const merged = mergeClippedIntervals(covered, window);
  const gaps: CoverageGap[] = [];
  let cursor = window.startMs;
  const pushGap = (startMs: number, endMs: number) => gaps.push({
    startMs, endMs, startIso: new Date(startMs).toISOString(), endIso: new Date(endMs).toISOString(),
  });
  for (const interval of merged) {
    if (interval.startMs > cursor) pushGap(cursor, interval.startMs);
    cursor = Math.max(cursor, interval.endMs);
  }
  if (cursor < window.endMs) pushGap(cursor, window.endMs);
  return gaps;
}

export function buildHierarchyCoverageRows(ranges: Record<string, unknown>[], filterLayer: HierarchyLayer): HierarchyCoverageRow[] {
  return ranges.filter((range) => layerOf(range) === filterLayer && isMajor(range)).map((parent) => {
    const parentId = rangeIdOf(parent);
    const parentWindow = rangeInterval(parent);
    const childLayer = CHILD_LAYER[filterLayer];
    if (!parentWindow || !childLayer) return {
      parent, parentId, parentLayer: filterLayer, childLayer, coveredMs: 0,
      durationMs: parentWindow ? parentWindow.endMs - parentWindow.startMs : 0,
      coveragePercent: null, gaps: [],
    };
    const childIntervals = ranges.filter((range) => String(range.parent_range_id || '') === parentId
      && layerOf(range) === childLayer && isMajor(range)).map(rangeInterval)
      .filter((interval): interval is TimeInterval => interval !== null);
    const merged = mergeClippedIntervals(childIntervals, parentWindow);
    const coveredMs = merged.reduce((total, interval) => total + interval.endMs - interval.startMs, 0);
    const durationMs = parentWindow.endMs - parentWindow.startMs;
    return { parent, parentId, parentLayer: filterLayer, childLayer, coveredMs, durationMs,
      coveragePercent: Math.round((coveredMs / durationMs) * 100), gaps: uncoveredIntervals(parentWindow, merged) };
  }).sort((a, b) => (rangeInterval(a.parent)?.startMs || 0) - (rangeInterval(b.parent)?.startMs || 0));
}

export function deriveCoverageYearOptions(rows: HierarchyCoverageRow[]): number[] {
  const years = new Set<number>();
  const addIntervalYears = (interval: TimeInterval | null) => {
    if (!interval) return;
    const first = new Date(interval.startMs).getUTCFullYear();
    const last = new Date(interval.endMs).getUTCFullYear();
    if (!Number.isFinite(first) || !Number.isFinite(last)) return;
    for (let year = first; year <= last; year += 1) years.add(year);
  };
  rows.forEach((row) => {
    addIntervalYears(rangeInterval(row.parent));
    row.gaps.forEach(addIntervalYears);
  });
  return [...years].sort((a, b) => a - b);
}

export function normalizeCoverageYearRange(fromYear: number, toYear: number): CoverageYearRange {
  return fromYear <= toYear ? { fromYear, toYear } : { fromYear: toYear, toYear: fromYear };
}

export function filterCoverageRowsByYear(rows: HierarchyCoverageRow[], fromYear: number, toYear: number): HierarchyCoverageRow[] {
  const normalized = normalizeCoverageYearRange(fromYear, toYear);
  const windowStart = Date.UTC(normalized.fromYear, 0, 1);
  const windowEnd = Date.UTC(normalized.toYear + 1, 0, 1);
  return rows.filter((row) => {
    const interval = rangeInterval(row.parent);
    return interval !== null && interval.endMs >= windowStart && interval.startMs < windowEnd;
  });
}

export function compactDate(value: string | number): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}
