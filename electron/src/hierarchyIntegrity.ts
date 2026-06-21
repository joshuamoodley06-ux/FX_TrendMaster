/** Hierarchy integrity — child ranges must stay inside parent campaign window. */

import { isGuidedParentComplete, type GuidedMappingCursor } from './guidedMappingCursor';

export const CHILD_OUTSIDE_PARENT_CAMPAIGN_MESSAGE =
  'Child range exists outside parent campaign window.';

export const INACTIVE_PARENT_CHILD_MESSAGE =
  'Cannot map children under an inactive parent range.';

export const PARENT_CAMPAIGN_CLOSED_MESSAGE =
  'Parent campaign is complete. Continue to the next sibling parent.';

export const CHILD_TO_PARENT_LAYER: Record<string, string> = {
  DAILY: 'WEEKLY',
  INTRADAY: 'DAILY',
  MICRO: 'INTRADAY',
};

export type ChildSpanFields = {
  range_high_time?: string | null;
  range_low_time?: string | null;
  range_start_time?: string | null;
  range_end_time?: string | null;
  active_from_time?: string | null;
};

export type HierarchyIntegrityArgs = {
  childLayer: string;
  rangeScope: 'MAJOR' | 'MINOR';
  childSpan: ChildSpanFields;
  parentId: string | number | null | undefined;
  savedRanges: Record<string, unknown>[];
  autoChain?: boolean;
  chainDraftMode?: boolean;
  /** Parent range id of the active campaign (guided cursor or broken-range parent). */
  chainParentCampaignId?: string | number | null;
  guidedCursor?: GuidedMappingCursor | null;
};

export type HierarchyIntegrityResult = {
  ok: boolean;
  message?: string;
};

function normalizeLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

export function parentCampaignWindowMs(
  parent: Record<string, unknown>,
): { startMs: number; endMs: number } {
  const startMs = parseTimeMs(
    parent.range_start_time
    || parent.active_from_time
    || parent.range_high_time
    || parent.range_low_time,
  ) ?? 0;
  const endMs = parseTimeMs(
    parent.range_end_time
    || parent.range_low_time
    || parent.range_high_time
    || parent.range_start_time
    || parent.active_from_time,
  ) ?? startMs;
  return { startMs, endMs: Math.max(endMs, startMs) };
}

export function collectChildSpanTimesMs(childSpan: ChildSpanFields): number[] {
  return [
    childSpan.range_high_time,
    childSpan.range_low_time,
    childSpan.range_start_time,
    childSpan.range_end_time,
    childSpan.active_from_time,
  ]
    .map(parseTimeMs)
    .filter((x): x is number => x !== null);
}

export function childSpanExceedsParentCampaign(
  parent: Record<string, unknown>,
  childSpan: ChildSpanFields,
): boolean {
  const times = collectChildSpanTimesMs(childSpan);
  if (!times.length) return false;
  const { startMs, endMs } = parentCampaignWindowMs(parent);
  const childMin = Math.min(...times);
  const childMax = Math.max(...times);
  return childMin < startMs || childMax > endMs;
}

export function isParentActiveForChildMapping(parent: Record<string, unknown>): boolean {
  const status = String(parent.status || 'ACTIVE').toUpperCase();
  return !['BROKEN', 'ABANDONED', 'ARCHIVED', 'INACTIVE', 'REPLACED'].includes(status);
}

export function isParentCampaignClosedForChildWork(
  parent: Record<string, unknown>,
  guidedCursor?: GuidedMappingCursor | null,
): boolean {
  const parentId = String(parent.range_id || parent.id || '');
  if (
    guidedCursor?.active
    && guidedCursor.active_parent_range_id === parentId
    && (guidedCursor.cursor_status === 'PARENT_COMPLETE' || isGuidedParentComplete(guidedCursor))
  ) {
    return true;
  }
  return false;
}

export function isAutoChainSameParentCampaign(args: {
  autoChain?: boolean;
  chainDraftMode?: boolean;
  parentId: string | number | null | undefined;
  chainParentCampaignId?: string | number | null;
}): boolean {
  if (!args.autoChain || !args.chainDraftMode) return false;
  if (!args.parentId || !args.chainParentCampaignId) return false;
  return String(args.parentId) === String(args.chainParentCampaignId);
}

export function findParentRangeRow(
  parentId: string | number | null | undefined,
  savedRanges: Record<string, unknown>[],
): Record<string, unknown> | null {
  if (parentId === null || parentId === undefined || parentId === '') return null;
  return savedRanges.find(
    (r) => String(r.range_id || r.id) === String(parentId),
  ) || null;
}

export function validateHierarchyIntegrity(args: HierarchyIntegrityArgs): HierarchyIntegrityResult {
  const childLayer = normalizeLayer(args.childLayer);
  const expectedParentLayer = CHILD_TO_PARENT_LAYER[childLayer];

  if (!expectedParentLayer) return { ok: true };
  if (args.rangeScope !== 'MAJOR') return { ok: true };

  const parentId = args.parentId;
  if (!parentId) {
    return { ok: false, message: `A ${expectedParentLayer} parent is required for ${childLayer} MAJOR ranges.` };
  }

  const parent = findParentRangeRow(parentId, args.savedRanges);
  if (!parent) {
    return { ok: false, message: `Parent range #${parentId} not found in the current case.` };
  }

  if (normalizeLayer(parent.structure_layer || parent.layer) !== expectedParentLayer) {
    return {
      ok: false,
      message: `${childLayer} MAJOR must link to a ${expectedParentLayer} parent (got ${normalizeLayer(parent.structure_layer || parent.layer)}).`,
    };
  }

  if (!isParentActiveForChildMapping(parent)) {
    return { ok: false, message: INACTIVE_PARENT_CHILD_MESSAGE };
  }

  if (isParentCampaignClosedForChildWork(parent, args.guidedCursor)) {
    return { ok: false, message: PARENT_CAMPAIGN_CLOSED_MESSAGE };
  }

  // Campaign boundary crossing is handled by soft validation in campaignFlexibility.ts (Phase B).

  return { ok: true };
}

export function validateParentEligibleForChildMapping(
  parent: Record<string, unknown>,
  guidedCursor?: GuidedMappingCursor | null,
): HierarchyIntegrityResult {
  if (!isParentActiveForChildMapping(parent)) {
    return { ok: false, message: INACTIVE_PARENT_CHILD_MESSAGE };
  }
  if (isParentCampaignClosedForChildWork(parent, guidedCursor)) {
    return { ok: false, message: PARENT_CAMPAIGN_CLOSED_MESSAGE };
  }
  return { ok: true };
}
