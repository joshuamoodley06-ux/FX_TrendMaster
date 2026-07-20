export type HierarchyLayer = 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO';
export type TimeInterval = { startMs: number; endMs: number };
export type CoverageGap = TimeInterval & { startIso: string; endIso: string };
export type CoverageMarketDataStatus = 'UNCHECKED' | 'AVAILABLE' | 'NO_DATA';
export type HierarchyCoverageRow = {
  parent: Record<string, unknown>; parentId: string; parentLayer: HierarchyLayer;
  childLayer: HierarchyLayer | null; coveredMs: number; durationMs: number;
  coveragePercent: number | null; gaps: CoverageGap[];
  marketDataStatus: CoverageMarketDataStatus;
};
export type CoverageYearRange = { fromYear: number; toYear: number };
export type CoverageCandle = { time: string };

const CHILD_LAYER: Record<HierarchyLayer, HierarchyLayer | null> = {
  WEEKLY: 'DAILY', DAILY: 'INTRADAY', INTRADAY: 'MICRO', MICRO: null,
};
const COVERAGE_CANDLE_TIMEFRAME: Record<HierarchyLayer, string | null> = {
  WEEKLY: 'D1', DAILY: 'H1', INTRADAY: 'M15', MICRO: null,
};
const CANDLE_DURATION_MS: Record<string, number> = {
  D1: 24 * 60 * 60 * 1000,
  H1: 60 * 60 * 1000,
  M15: 15 * 60 * 1000,
};

function parseTime(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const mt5 = raw.match(/^(\d{4})\.(\d{2})\.(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (mt5) {
    const [, year, month, day, hour = '0', minute = '0', second = '0'] = mt5;
    const parsed = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(parsed) ? parsed : null;
}
function layerOf(range: Record<string, unknown>): HierarchyLayer | null {
  const layer = String(range.structure_layer || range.layer || '').toUpperCase();
  return layer in CHILD_LAYER ? layer as HierarchyLayer : null;
}
function rangeIdOf(range: Record<string, unknown>): string { return String(range.range_id || range.id || ''); }
function isMajor(range: Record<string, unknown>): boolean { return String(range.range_scope || 'MAJOR').toUpperCase() !== 'MINOR'; }
function gapFromInterval(interval: TimeInterval): CoverageGap {
  return {
    ...interval,
    startIso: new Date(interval.startMs).toISOString(),
    endIso: new Date(interval.endMs).toISOString(),
  };
}
function intervalDuration(intervals: TimeInterval[]): number {
  return intervals.reduce((total, interval) => total + Math.max(0, interval.endMs - interval.startMs), 0);
}

export function coverageCandleTimeframe(layer: HierarchyLayer): string | null {
  return COVERAGE_CANDLE_TIMEFRAME[layer];
}

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

export function intersectIntervals(left: TimeInterval[], right: TimeInterval[]): TimeInterval[] {
  const intersections: TimeInterval[] = [];
  let leftIndex = 0;
  let rightIndex = 0;
  while (leftIndex < left.length && rightIndex < right.length) {
    const startMs = Math.max(left[leftIndex].startMs, right[rightIndex].startMs);
    const endMs = Math.min(left[leftIndex].endMs, right[rightIndex].endMs);
    if (endMs > startMs) intersections.push({ startMs, endMs });
    if (left[leftIndex].endMs <= right[rightIndex].endMs) leftIndex += 1;
    else rightIndex += 1;
  }
  return intersections;
}

export function uncoveredIntervals(window: TimeInterval, covered: TimeInterval[]): CoverageGap[] {
  if (window.endMs <= window.startMs) return [];
  const merged = mergeClippedIntervals(covered, window);
  const gaps: CoverageGap[] = [];
  let cursor = window.startMs;
  const pushGap = (startMs: number, endMs: number) => gaps.push(gapFromInterval({ startMs, endMs }));
  for (const interval of merged) {
    if (interval.startMs > cursor) pushGap(cursor, interval.startMs);
    cursor = Math.max(cursor, interval.endMs);
  }
  if (cursor < window.endMs) pushGap(cursor, window.endMs);
  return gaps;
}

export function candleAvailabilityIntervals(
  candles: CoverageCandle[],
  timeframe: string,
  window: TimeInterval,
): TimeInterval[] {
  const durationMs = CANDLE_DURATION_MS[String(timeframe || '').toUpperCase()];
  if (!durationMs) return [];
  const intervals = candles.map((candle) => parseTime(candle.time))
    .filter((time): time is number => time !== null)
    .map((time) => ({ startMs: time, endMs: time + durationMs }));
  return mergeClippedIntervals(intervals, window);
}

export function applyCandleAvailabilityToCoverageRow(
  row: HierarchyCoverageRow,
  candles: CoverageCandle[],
  timeframe: string,
): HierarchyCoverageRow {
  if (!row.gaps.length) return row;
  const parentWindow = rangeInterval(row.parent);
  if (!parentWindow) return row;
  const marketIntervals = candleAvailabilityIntervals(candles, timeframe, parentWindow);
  if (!marketIntervals.length) {
    const durationMs = row.coveredMs;
    return {
      ...row,
      durationMs,
      coveragePercent: durationMs > 0 ? 100 : null,
      gaps: [],
      marketDataStatus: 'NO_DATA',
    };
  }
  const supportedGaps = intersectIntervals(row.gaps, marketIntervals);
  const missingMs = intervalDuration(supportedGaps);
  const durationMs = row.coveredMs + missingMs;
  const coveragePercent = durationMs > 0
    ? Math.max(0, Math.min(100, Math.round((row.coveredMs / durationMs) * 100)))
    : null;
  return {
    ...row,
    durationMs,
    coveragePercent,
    gaps: supportedGaps.map(gapFromInterval),
    marketDataStatus: 'AVAILABLE',
  };
}

export function buildHierarchyCoverageRows(ranges: Record<string, unknown>[], filterLayer: HierarchyLayer): HierarchyCoverageRow[] {
  return ranges.filter((range) => layerOf(range) === filterLayer && isMajor(range)).map((parent) => {
    const parentId = rangeIdOf(parent);
    const parentWindow = rangeInterval(parent);
    const childLayer = CHILD_LAYER[filterLayer];
    if (!parentWindow || !childLayer) return {
      parent, parentId, parentLayer: filterLayer, childLayer, coveredMs: 0,
      durationMs: parentWindow ? parentWindow.endMs - parentWindow.startMs : 0,
      coveragePercent: null, gaps: [], marketDataStatus: 'UNCHECKED' as const,
    };
    const childIntervals = ranges.filter((range) => String(range.parent_range_id || '') === parentId
      && layerOf(range) === childLayer && isMajor(range)).map(rangeInterval)
      .filter((interval): interval is TimeInterval => interval !== null);
    const merged = mergeClippedIntervals(childIntervals, parentWindow);
    const coveredMs = intervalDuration(merged);
    const durationMs = parentWindow.endMs - parentWindow.startMs;
    return { parent, parentId, parentLayer: filterLayer, childLayer, coveredMs, durationMs,
      coveragePercent: Math.round((coveredMs / durationMs) * 100), gaps: uncoveredIntervals(parentWindow, merged),
      marketDataStatus: 'UNCHECKED' as const };
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
