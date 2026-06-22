/** Auto BOS Save — prompt to map next same-layer range after formal BOS (no auto-create). */

export type BosNextRangePromptStatus =
  | 'NO_PROMPT'
  | 'PROMPT'
  | 'ALREADY_EXISTS'
  | 'UNCERTAIN';

export type BosNextRangeMatchKind =
  | 'new_range_id'
  | 'old_range_id'
  | 'created_by_event_id'
  | 'none'
  | 'ambiguous';

export type BosNextRangePromptResult = {
  status: BosNextRangePromptStatus;
  message: string;
  promptMessage?: string;
  existingNextRangeId?: string | null;
  bosEventId?: string | number | null;
  brokenRangeId?: string;
  structureLayer?: string;
};

function normalizeLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function normalizeId(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  return String(value);
}

function eventIdsMatch(a: unknown, b: unknown): boolean {
  if (a === null || a === undefined || b === null || b === undefined) return false;
  const sa = String(a);
  const sb = String(b);
  if (sa === sb) return true;
  const na = Number(a);
  const nb = Number(b);
  return Number.isFinite(na) && Number.isFinite(nb) && na === nb;
}

export function promptTextForStructureLayer(layer: string): string {
  const key = normalizeLayer(layer);
  const labels: Record<string, string> = {
    WEEKLY: 'Weekly',
    DAILY: 'Daily',
    INTRADAY: 'Intraday',
    MICRO: 'Micro',
    MACRO: 'Macro',
  };
  const label = labels[key] || key.charAt(0) + key.slice(1).toLowerCase();
  return `Set new ${label} range?`;
}

export function findNextChainedRange(
  brokenRangeId: string,
  bosEventId: string | number | null | undefined,
  ranges: Record<string, unknown>[],
  structureLayer?: string,
): { range: Record<string, unknown> | null; matchKind: BosNextRangeMatchKind } {
  const brokenId = normalizeId(brokenRangeId);
  if (!brokenId) return { range: null, matchKind: 'none' };

  const broken = ranges.find((r) => normalizeId(r.range_id || r.id) === brokenId);
  const layer = structureLayer ? normalizeLayer(structureLayer) : '';

  if (broken?.new_range_id != null && String(broken.new_range_id) !== '') {
    const next = ranges.find((r) => normalizeId(r.range_id || r.id) === normalizeId(broken.new_range_id));
    if (next) return { range: next, matchKind: 'new_range_id' };
  }

  const byOldRange = ranges.filter((r) => normalizeId(r.old_range_id) === brokenId);
  const sameLayerByOld = layer
    ? byOldRange.filter((r) => normalizeLayer(r.structure_layer || r.layer) === layer)
    : byOldRange;
  if (sameLayerByOld.length === 1) return { range: sameLayerByOld[0], matchKind: 'old_range_id' };
  if (sameLayerByOld.length > 1) return { range: null, matchKind: 'ambiguous' };

  if (bosEventId != null && String(bosEventId) !== '') {
    const byEvent = ranges.filter((r) => eventIdsMatch(r.created_by_event_id, bosEventId));
    const sameLayerByEvent = layer
      ? byEvent.filter((r) => normalizeLayer(r.structure_layer || r.layer) === layer)
      : byEvent;
    if (sameLayerByEvent.length === 1) return { range: sameLayerByEvent[0], matchKind: 'created_by_event_id' };
    if (sameLayerByEvent.length > 1) return { range: null, matchKind: 'ambiguous' };
  }

  return { range: null, matchKind: 'none' };
}

export function evaluateBosNextRangePrompt(args: {
  brokenRange: Record<string, unknown>;
  ranges: Record<string, unknown>[];
  bosEventId?: string | number | null;
  /** When false, skip parent requirement (legacy top-level chain). Default true. */
  requireParentContext?: boolean;
}): BosNextRangePromptResult {
  const brokenRangeId = normalizeId(args.brokenRange.range_id || args.brokenRange.id);
  const structureLayer = normalizeLayer(args.brokenRange.structure_layer || args.brokenRange.layer);
  const parentId = args.brokenRange.parent_range_id;
  const hasParent = parentId != null && String(parentId) !== '';
  const requireParent = args.requireParentContext !== false;

  if (!brokenRangeId || !structureLayer) {
    return { status: 'NO_PROMPT', message: '', brokenRangeId };
  }

  const bosEventId = args.bosEventId ?? args.brokenRange.broken_by_event_id ?? null;
  const next = findNextChainedRange(brokenRangeId, bosEventId, args.ranges, structureLayer);

  if (next.matchKind === 'ambiguous') {
    return {
      status: 'UNCERTAIN',
      message: `Multiple ${structureLayer} ranges may follow #${brokenRangeId}. Verify chain links before creating another.`,
      brokenRangeId,
      bosEventId,
      structureLayer,
    };
  }

  if (next.range) {
    const existingNextRangeId = normalizeId(next.range.range_id || next.range.id);
    return {
      status: 'ALREADY_EXISTS',
      message: `Next ${structureLayer} range #${existingNextRangeId} is already linked to broken #${brokenRangeId}.`,
      existingNextRangeId,
      brokenRangeId,
      bosEventId,
      structureLayer,
    };
  }

  if (requireParent && !hasParent) {
    return {
      status: 'NO_PROMPT',
      message: '',
      brokenRangeId,
      bosEventId,
      structureLayer,
    };
  }

  return {
    status: 'PROMPT',
    message: `${structureLayer} range #${brokenRangeId} is broken — ready to map the next ${structureLayer} range.`,
    promptMessage: promptTextForStructureLayer(structureLayer),
    brokenRangeId,
    bosEventId,
    structureLayer,
  };
}

export function bosNextRangePromptKey(result: Pick<BosNextRangePromptResult, 'brokenRangeId' | 'bosEventId'>): string {
  return `${normalizeId(result.brokenRangeId)}:${normalizeId(result.bosEventId ?? 'unknown')}`;
}
