/** Phase B — soft campaign-boundary validation when saving child MAJOR ranges. */

import {
  CHILD_TO_PARENT_LAYER,
  childSpanExceedsParentCampaign,
  collectChildSpanTimesMs,
  findParentRangeRow,
  isAutoChainSameParentCampaign,
  parentCampaignWindowMs,
  type ChildSpanFields,
} from './hierarchyIntegrity';

export type CampaignFlexMeta = {
  extend_campaign: boolean;
  reassigned_from_parent_id?: string | null;
  alternate_parent_id?: string | null;
  confirmed_at: string;
};

export type CampaignBoundaryAssessment = {
  crosses: boolean;
  exceedsStart: boolean;
  exceedsEnd: boolean;
  currentParent: Record<string, unknown>;
  alternateParent: Record<string, unknown> | null;
  currentParentLabel: string;
  alternateParentLabel: string | null;
};

export type CampaignFlexConfirmResult = {
  proceed: boolean;
  parentId: string;
  meta: CampaignFlexMeta | null;
};

function normalizeLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function isMajorRange(range: Record<string, unknown>): boolean {
  return normalizeLayer(range.range_scope || 'MAJOR') !== 'MINOR';
}

export function formatParentCampaignLabel(parent: Record<string, unknown>): string {
  const id = parent.range_id ?? parent.id ?? '?';
  const layer = normalizeLayer(parent.structure_layer || parent.layer) || 'PARENT';
  const { startMs, endMs } = parentCampaignWindowMs(parent);
  const start = startMs ? new Date(startMs).toISOString().slice(0, 10) : '?';
  const end = endMs ? new Date(endMs).toISOString().slice(0, 10) : '?';
  return `${layer} #${id} (${start} → ${end})`;
}

function parentCampaignStartMs(parent: Record<string, unknown>): number {
  return parentCampaignWindowMs(parent).startMs;
}

function parentLayerCandidatesForChild(
  childLayer: string,
  savedRanges: Record<string, unknown>[],
): Record<string, unknown>[] {
  const parentLayer = CHILD_TO_PARENT_LAYER[normalizeLayer(childLayer)];
  if (!parentLayer) return [];
  return savedRanges.filter(
    (r) => normalizeLayer(r.structure_layer || r.layer) === parentLayer && isMajorRange(r),
  );
}

export function findAlternateParentCampaign(args: {
  currentParent: Record<string, unknown>;
  childSpan: ChildSpanFields;
  savedRanges: Record<string, unknown>[];
  childLayer: string;
}): Record<string, unknown> | null {
  const times = collectChildSpanTimesMs(args.childSpan);
  if (!times.length) return null;

  const { startMs, endMs } = parentCampaignWindowMs(args.currentParent);
  const overflowTimes = times.filter((t) => t < startMs || t > endMs);
  if (!overflowTimes.length) return null;

  const currentId = String(args.currentParent.range_id || args.currentParent.id || '');
  const candidates = parentLayerCandidatesForChild(args.childLayer, args.savedRanges)
    .filter((p) => String(p.range_id || p.id) !== currentId);

  const matches = candidates.filter((p) => {
    const window = parentCampaignWindowMs(p);
    return overflowTimes.every((t) => t >= window.startMs && t <= window.endMs);
  });
  if (!matches.length) return null;
  if (matches.length === 1) return matches[0];

  const sorted = [...parentLayerCandidatesForChild(args.childLayer, args.savedRanges)]
    .sort((a, b) => parentCampaignStartMs(a) - parentCampaignStartMs(b));
  const currentIdx = sorted.findIndex((p) => String(p.range_id || p.id) === currentId);
  const childMin = Math.min(...times);
  const childMax = Math.max(...times);
  const preferNext = childMax > endMs;
  const preferPrev = childMin < startMs;

  if (preferNext && currentIdx >= 0 && currentIdx < sorted.length - 1) {
    const next = sorted[currentIdx + 1];
    const hit = matches.find((m) => String(m.range_id || m.id) === String(next.range_id || next.id));
    if (hit) return hit;
  }
  if (preferPrev && currentIdx > 0) {
    const prev = sorted[currentIdx - 1];
    const hit = matches.find((m) => String(m.range_id || m.id) === String(prev.range_id || prev.id));
    if (hit) return hit;
  }
  return matches[0];
}

export function assessCampaignBoundaryCrossing(args: {
  childLayer: string;
  rangeScope: 'MAJOR' | 'MINOR';
  childSpan: ChildSpanFields;
  parentId: string | number | null | undefined;
  savedRanges: Record<string, unknown>[];
  autoChain?: boolean;
  chainDraftMode?: boolean;
  chainParentCampaignId?: string | number | null;
}): CampaignBoundaryAssessment | null {
  if (args.rangeScope !== 'MAJOR') return null;
  const childLayer = normalizeLayer(args.childLayer);
  if (!CHILD_TO_PARENT_LAYER[childLayer]) return null;

  const autoChainExempt = isAutoChainSameParentCampaign({
    autoChain: args.autoChain,
    chainDraftMode: args.chainDraftMode,
    parentId: args.parentId,
    chainParentCampaignId: args.chainParentCampaignId,
  });
  if (autoChainExempt) return null;

  const parent = findParentRangeRow(args.parentId, args.savedRanges);
  if (!parent) return null;
  if (!childSpanExceedsParentCampaign(parent, args.childSpan)) return null;

  const times = collectChildSpanTimesMs(args.childSpan);
  const { startMs, endMs } = parentCampaignWindowMs(parent);
  const childMin = Math.min(...times);
  const childMax = Math.max(...times);
  const alternateParent = findAlternateParentCampaign({
    currentParent: parent,
    childSpan: args.childSpan,
    savedRanges: args.savedRanges,
    childLayer,
  });

  return {
    crosses: true,
    exceedsStart: childMin < startMs,
    exceedsEnd: childMax > endMs,
    currentParent: parent,
    alternateParent,
    currentParentLabel: formatParentCampaignLabel(parent),
    alternateParentLabel: alternateParent ? formatParentCampaignLabel(alternateParent) : null,
  };
}

/** Browser confirm flow — matches existing window.confirm patterns in main.tsx. */
export function confirmCampaignFlexibility(
  assessment: CampaignBoundaryAssessment,
): CampaignFlexConfirmResult | null {
  const currentId = String(assessment.currentParent.range_id || assessment.currentParent.id || '');
  const confirmedAt = new Date().toISOString();

  if (assessment.alternateParent && assessment.alternateParentLabel) {
    const reassign = window.confirm(
      `Range crosses campaign boundaries.\n\n`
      + `Reassign to ${assessment.alternateParentLabel}?\n\n`
      + `OK = Reassign to alternate parent\n`
      + `Cancel = choose Keep in ${assessment.currentParentLabel}`,
    );
    if (reassign) {
      const altId = String(assessment.alternateParent.range_id || assessment.alternateParent.id || '');
      return {
        proceed: true,
        parentId: altId,
        meta: {
          extend_campaign: false,
          reassigned_from_parent_id: currentId,
          alternate_parent_id: altId,
          confirmed_at: confirmedAt,
        },
      };
    }
    const keep = window.confirm(
      `Keep in ${assessment.currentParentLabel} and extend campaign boundary?\n\n`
      + `OK = Extend and save under current parent\n`
      + `Cancel = abort save`,
    );
    if (!keep) return null;
    return {
      proceed: true,
      parentId: currentId,
      meta: {
        extend_campaign: true,
        reassigned_from_parent_id: null,
        alternate_parent_id: String(assessment.alternateParent.range_id || assessment.alternateParent.id || ''),
        confirmed_at: confirmedAt,
      },
    };
  }

  const extend = window.confirm(
    `Child range extends outside ${assessment.currentParentLabel}.\n\n`
    + `Extend campaign and save anyway?\n\n`
    + `OK = Extend and save\n`
    + `Cancel = abort save`,
  );
  if (!extend) return null;
  return {
    proceed: true,
    parentId: currentId,
    meta: {
      extend_campaign: true,
      confirmed_at: confirmedAt,
    },
  };
}

export function mergeCampaignFlexMeta(
  existing: Record<string, unknown> | null | undefined,
  flex: CampaignFlexMeta | null,
): Record<string, unknown> {
  const base = existing && typeof existing === 'object' ? { ...existing } : {};
  if (!flex) return base;
  return { ...base, campaign_flexibility: flex };
}
