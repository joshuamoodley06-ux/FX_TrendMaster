export type CanonicalChartOverlayLayer = 'WEEKLY' | 'DAILY';

export type CanonicalRangeOverlayInput = {
  range_id?: unknown;
  id?: unknown;
  canonical_range_id?: unknown;
  canonical_structure_layer?: unknown;
  canonicalStructureLayer?: unknown;
  structure_layer?: unknown;
  layer?: unknown;
  range_high_price?: unknown;
  range_high?: unknown;
  range_low_price?: unknown;
  range_low?: unknown;
  structural_range_start_time?: unknown;
  structural_range_end_time?: unknown;
  range_start_time?: unknown;
  range_end_time?: unknown;
  range_high_time?: unknown;
  range_low_time?: unknown;
  active_from_time?: unknown;
  inactive_from_time?: unknown;
  status?: unknown;
};

export type CanonicalChartOverlay = {
  rangeId: string;
  structureLayer: CanonicalChartOverlayLayer;
  rangeScope: 'MAJOR';
  status: string;
  customLabelPrefix: string;
  high: number;
  low: number;
  start: string | null;
  end: string | null;
  isActive: true;
};

function text(value: unknown): string | null {
  const result = String(value ?? '').trim();
  return result || null;
}

function firstText(values: unknown[]): string | null {
  for (const value of values) {
    const result = text(value);
    if (result) return result;
  }
  return null;
}

function canonicalLayer(range: CanonicalRangeOverlayInput): CanonicalChartOverlayLayer | null {
  const value = firstText([
    range.canonical_structure_layer,
    range.canonicalStructureLayer,
    range.structure_layer,
    range.layer,
  ])?.toUpperCase();
  return value === 'WEEKLY' || value === 'DAILY' ? value : null;
}

function canonicalId(range: CanonicalRangeOverlayInput): string | null {
  return firstText([
    range.range_id,
    range.id,
    range.canonical_range_id,
  ]);
}

function factualAnchorWindow(range: CanonicalRangeOverlayInput): { start: string | null; end: string | null } {
  const highTime = text(range.range_high_time);
  const lowTime = text(range.range_low_time);
  if (!highTime || !lowTime) return { start: null, end: null };
  const highMs = Date.parse(highTime);
  const lowMs = Date.parse(lowTime);
  if (!Number.isFinite(highMs) || !Number.isFinite(lowMs)) return { start: null, end: null };
  return highMs <= lowMs ? { start: highTime, end: lowTime } : { start: lowTime, end: highTime };
}

export function buildCanonicalChartOverlay(
  range: CanonicalRangeOverlayInput | null | undefined,
  existingRangeIds: Iterable<unknown> = [],
): CanonicalChartOverlay | null {
  if (!range) return null;
  const layer = canonicalLayer(range);
  const rangeId = canonicalId(range);
  const high = Number(range.range_high_price ?? range.range_high);
  const low = Number(range.range_low_price ?? range.range_low);
  if (!layer || !rangeId || !Number.isFinite(high) || !Number.isFinite(low) || high <= low) {
    return null;
  }

  const existing = new Set(
    Array.from(existingRangeIds)
      .map((value) => text(value))
      .filter((value): value is string => !!value),
  );
  if (existing.has(rangeId)) return null;

  const anchorWindow = factualAnchorWindow(range);
  return {
    rangeId,
    structureLayer: layer,
    rangeScope: 'MAJOR',
    status: String(range.status || 'ACTIVE').toUpperCase(),
    customLabelPrefix: `CANONICAL ${layer}`,
    high,
    low,
    ...anchorWindow,
    isActive: true,
  };
}
