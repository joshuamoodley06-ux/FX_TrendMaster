/** Read-only normalization into the shared structural chart-navigation contract. */

import { normalizeNavLayer } from './hierarchyRangeNavigation';

export type StructuralJumpSource = 'HIERARCHY' | 'GAP' | 'REVIEW';

export type StructuralSourceRef = {
  rawId?: string;
  caseRef?: string;
  sourceRecordId?: string;
  payloadSha256?: string;
};

export type StructuralSourceRecordProvenance = {
  caseRefs: string[];
  sourceRecordIds: string[];
  sourceRefs: StructuralSourceRef[];
  reviewKey?: string;
  itemType?: string;
};

export type StructuralVisibleWindow = {
  start: string;
  end: string;
};

export type StructuralJumpTarget = {
  symbol: string;
  structureLayer: string;
  sourceTimeframe: string;
  canonicalRangeId: string;
  eventId?: string;
  rangeHighTime: string;
  rangeLowTime: string;
  activeFromTime: string;
  inactiveOrBreakTime?: string;
  preferredAnchorTime: string;
  visibleWindow?: StructuralVisibleWindow;
  sourceRecordProvenance: StructuralSourceRecordProvenance;
  reason: StructuralJumpSource;
};

export type StructuralTargetOptions = {
  fallbackSymbol?: string;
  fallbackTimeframe?: string;
  preferredAnchorTime?: unknown;
  visibleStart?: unknown;
  visibleEnd?: unknown;
  eventId?: unknown;
};

type LooseRecord = Record<string, unknown>;

const LAYER_DEFAULT_TF: Record<string, string> = {
  MACRO: 'MN1',
  WEEKLY: 'W1',
  DAILY: 'D1',
  INTRADAY: 'H1',
  MICRO: 'M15',
};

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as LooseRecord
    : {};
}

function firstValue(record: LooseRecord, keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value !== null && value !== undefined && String(value).trim() !== '') return value;
  }
  return undefined;
}

function text(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  const result = String(value).trim();
  return result || undefined;
}

function iso(value: unknown): string | undefined {
  const raw = text(value);
  if (!raw) return undefined;
  const ms = new Date(raw).getTime();
  return Number.isFinite(ms) ? new Date(ms).toISOString() : undefined;
}

function unique(values: Array<string | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => !!value))).sort();
}

function parseJsonArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string') return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function normalizeSourceRef(value: unknown): StructuralSourceRef | null {
  const row = asRecord(value);
  const rawId = text(firstValue(row, ['raw_id', 'rawId']));
  const caseRef = text(firstValue(row, ['case_ref', 'caseRef', 'raw_case_id', 'case_id']));
  const sourceRecordId = text(firstValue(row, ['source_record_id', 'sourceRecordId', 'range_id', 'event_id']));
  const payloadSha256 = text(firstValue(row, ['payload_sha256', 'payloadSha256']));
  if (!rawId && !caseRef && !sourceRecordId && !payloadSha256) return null;
  return { rawId, caseRef, sourceRecordId, payloadSha256 };
}

function provenanceFrom(...values: unknown[]): StructuralSourceRecordProvenance {
  const records = values.map(asRecord);
  const sourceRefs = records
    .flatMap((row) => parseJsonArray(firstValue(row, ['source_refs', 'sourceRefs', 'source_refs_json'])))
    .map(normalizeSourceRef)
    .filter((value): value is StructuralSourceRef => value !== null);

  const caseRefs = unique([
    ...sourceRefs.map((ref) => ref.caseRef),
    ...records.flatMap((row) => parseJsonArray(firstValue(row, ['case_refs', 'caseRefs'])).map(text)),
    ...records.map((row) => text(firstValue(row, ['case_ref', 'caseRef', 'raw_case_id', 'case_id']))),
  ]);
  const sourceRecordIds = unique([
    ...sourceRefs.map((ref) => ref.sourceRecordId),
    ...records.flatMap((row) => parseJsonArray(firstValue(row, ['source_record_ids', 'sourceRecordIds'])).map(text)),
    ...records.map((row) => text(firstValue(row, ['source_record_id', 'sourceRecordId']))),
  ]);

  return {
    caseRefs,
    sourceRecordIds,
    sourceRefs,
    reviewKey: records.map((row) => text(firstValue(row, ['review_key', 'reviewKey']))).find(Boolean),
    itemType: records.map((row) => text(firstValue(row, ['item_type', 'itemType']))).find(Boolean),
  };
}

function defaultTimeframe(layer: string, record: LooseRecord, fallback?: string): string {
  const explicit = text(firstValue(record, ['source_timeframe', 'sourceTimeframe', 'chart_timeframe', 'chartTimeframe', 'timeframe']))?.toUpperCase();
  return explicit || LAYER_DEFAULT_TF[layer] || String(fallback || 'D1').toUpperCase();
}

function orderedWindow(startValue: unknown, endValue: unknown): StructuralVisibleWindow | undefined {
  const start = iso(startValue);
  const end = iso(endValue);
  if (!start && !end) return undefined;
  const left = start || end!;
  const right = end || start!;
  return left <= right ? { start: left, end: right } : { start: right, end: left };
}

function derivedWindow(record: LooseRecord, options: StructuralTargetOptions, times: string[]): StructuralVisibleWindow | undefined {
  const explicit = orderedWindow(
    options.visibleStart ?? firstValue(record, ['visible_start_time', 'visibleStartTime', 'range_start_time', 'rangeStartTime']),
    options.visibleEnd ?? firstValue(record, ['visible_end_time', 'visibleEndTime', 'range_end_time', 'rangeEndTime']),
  );
  if (explicit) return explicit;
  const sorted = unique(times).sort();
  return sorted.length ? { start: sorted[0], end: sorted[sorted.length - 1] } : undefined;
}

export function normalizeStructuralRangeTarget(
  input: unknown,
  reason: StructuralJumpSource = 'HIERARCHY',
  options: StructuralTargetOptions = {},
): StructuralJumpTarget | null {
  const record = asRecord(input);
  const payload = asRecord(firstValue(record, ['canonical_payload', 'canonicalPayload', 'range', 'canonical_range', 'canonicalRange']));
  const merged = { ...payload, ...record };
  const layer = normalizeNavLayer(firstValue(merged, ['structure_layer', 'structureLayer', 'layer']));
  const canonicalRangeId = text(firstValue(merged, ['canonical_range_id', 'canonicalRangeId', 'range_id', 'rangeId', 'id']));
  const symbol = text(firstValue(merged, ['symbol'])) || text(options.fallbackSymbol);
  if (!layer || !canonicalRangeId || !symbol) return null;

  const rangeHighTime = iso(firstValue(merged, ['range_high_time', 'rangeHighTime', 'rh_time', 'high_time']));
  const rangeLowTime = iso(firstValue(merged, ['range_low_time', 'rangeLowTime', 'rl_time', 'low_time']));
  if (!rangeHighTime || !rangeLowTime) return null;
  const anchorTimes = [rangeHighTime, rangeLowTime].sort();
  const activeFromTime = iso(firstValue(merged, ['active_from_time', 'activeFromTime', 'range_start_time', 'rangeStartTime']))
    || anchorTimes[anchorTimes.length - 1];
  if (!activeFromTime) return null;
  const inactiveOrBreakTime = iso(firstValue(merged, [
    'inactive_from_time', 'inactiveFromTime', 'break_time', 'breakTime', 'event_time_utc', 'event_time',
  ]));
  const eventId = text(options.eventId ?? firstValue(merged, ['canonical_event_id', 'canonicalEventId', 'event_id', 'eventId']));
  const preferredAnchorTime = iso(
    options.preferredAnchorTime
      ?? firstValue(merged, ['preferred_anchor_time', 'preferredAnchorTime', 'event_time_utc', 'event_time'])
      ?? activeFromTime,
  ) || activeFromTime;
  const visibleWindow = derivedWindow(merged, options, [
    rangeHighTime, rangeLowTime, activeFromTime, inactiveOrBreakTime, preferredAnchorTime,
  ].filter((value): value is string => !!value));

  return {
    symbol: symbol.toUpperCase(),
    structureLayer: layer,
    sourceTimeframe: defaultTimeframe(layer, merged, options.fallbackTimeframe),
    canonicalRangeId,
    eventId,
    rangeHighTime,
    rangeLowTime,
    activeFromTime,
    inactiveOrBreakTime,
    preferredAnchorTime,
    visibleWindow,
    sourceRecordProvenance: provenanceFrom(record, payload),
    reason,
  };
}

export function normalizeStructuralEventTarget(
  eventInput: unknown,
  rangeInput: unknown,
  reason: StructuralJumpSource = 'HIERARCHY',
  options: StructuralTargetOptions = {},
): StructuralJumpTarget | null {
  const event = asRecord(eventInput);
  const eventTime = firstValue(event, ['event_time_utc', 'eventTimeUtc', 'event_time', 'eventTime', 'candle_time']);
  const eventId = firstValue(event, ['canonical_event_id', 'canonicalEventId', 'event_id', 'eventId', 'id']);
  const target = normalizeStructuralRangeTarget(rangeInput, reason, {
    ...options,
    eventId,
    preferredAnchorTime: options.preferredAnchorTime ?? eventTime,
  });
  if (!target) return null;
  return {
    ...target,
    sourceRecordProvenance: mergeProvenance(target.sourceRecordProvenance, provenanceFrom(event)),
  };
}

export type StructuralGapLike = {
  parentId?: unknown;
  parentRange?: unknown;
  parentLayer?: unknown;
  expectedChildLayer?: unknown;
  coverage?: unknown;
};

export function normalizeGapTarget(
  gapInput: StructuralGapLike | unknown,
  options: StructuralTargetOptions = {},
): StructuralJumpTarget | null {
  const gap = asRecord(gapInput);
  const parentRange = asRecord(firstValue(gap, ['parentRange', 'parent_range']));
  const coverage = asRecord(firstValue(gap, ['coverage']));
  const gapStart = firstValue(coverage, ['first_gap_start', 'firstGapStart']);
  const gapEnd = firstValue(coverage, ['first_gap_end', 'firstGapEnd']);
  const childLayer = normalizeNavLayer(firstValue(gap, ['expectedChildLayer', 'expected_child_layer']));
  const enrichedParent = {
    ...parentRange,
    canonical_range_id: firstValue(parentRange, ['canonical_range_id', 'canonicalRangeId', 'range_id', 'rangeId', 'id'])
      ?? firstValue(gap, ['parentId', 'parent_id']),
    ...(childLayer ? {
      structure_layer: childLayer,
      source_timeframe: LAYER_DEFAULT_TF[childLayer],
    } : {}),
  };
  return normalizeStructuralRangeTarget(enrichedParent, 'GAP', {
    ...options,
    preferredAnchorTime: options.preferredAnchorTime ?? gapStart,
    visibleStart: options.visibleStart ?? gapStart,
    visibleEnd: options.visibleEnd ?? gapEnd,
  });
}

export function normalizeReviewTarget(
  reviewInput: unknown,
  options: StructuralTargetOptions & { canonicalRange?: unknown } = {},
): StructuralJumpTarget | null {
  const review = asRecord(reviewInput);
  const embeddedRange = firstValue(review, ['canonical_range', 'canonicalRange', 'range', 'range_node', 'rangeNode']);
  const range = options.canonicalRange ?? embeddedRange ?? reviewInput;
  const canonicalIds = parseJsonArray(firstValue(review, ['canonical_ids', 'canonicalIds'])).map(text).filter(Boolean) as string[];
  const enrichedRange = {
    ...asRecord(range),
    canonical_range_id: firstValue(asRecord(range), ['canonical_range_id', 'canonicalRangeId', 'range_id', 'rangeId', 'id'])
      ?? canonicalIds[0],
  };
  const target = normalizeStructuralRangeTarget(enrichedRange, 'REVIEW', {
    ...options,
    preferredAnchorTime: options.preferredAnchorTime ?? firstValue(review, [
      'preferred_anchor_time', 'preferredAnchorTime', 'jump_time', 'jumpTime',
      'replay_until_time', 'replayUntilTime', 'event_time_utc', 'eventTimeUtc',
    ]),
    visibleStart: options.visibleStart ?? firstValue(review, [
      'visible_start_time', 'visibleStartTime', 'first_time', 'firstTime', 'range_start_time', 'rangeStartTime',
    ]),
    visibleEnd: options.visibleEnd ?? firstValue(review, [
      'visible_end_time', 'visibleEndTime', 'replay_until_time', 'replayUntilTime',
      'last_time', 'lastTime', 'range_end_time', 'rangeEndTime',
    ]),
  });
  if (!target) return null;
  return {
    ...target,
    sourceRecordProvenance: mergeProvenance(target.sourceRecordProvenance, provenanceFrom(review)),
  };
}

function mergeProvenance(
  left: StructuralSourceRecordProvenance,
  right: StructuralSourceRecordProvenance,
): StructuralSourceRecordProvenance {
  const sourceRefs = [...left.sourceRefs, ...right.sourceRefs];
  return {
    caseRefs: unique([...left.caseRefs, ...right.caseRefs]),
    sourceRecordIds: unique([...left.sourceRecordIds, ...right.sourceRecordIds]),
    sourceRefs,
    reviewKey: right.reviewKey || left.reviewKey,
    itemType: right.itemType || left.itemType,
  };
}
