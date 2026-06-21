import type { MappingDraft, MappingPoint } from './types';

const CHART_TF_RANK: Record<string, number> = {
  MN1: 0,
  W1: 1,
  D1: 2,
  H4: 3,
  H1: 4,
  M15: 5,
  M5: 6,
};

export function normalizeChartTf(tf?: string | null): string {
  return String(tf || '').toUpperCase();
}

export function timeMs(value?: string | null): number | null {
  if (!value) return null;
  const ms = Date.parse(String(value));
  return Number.isFinite(ms) ? ms : null;
}

export function minIso(a?: string | null, b?: string | null): string | null {
  const aMs = timeMs(a);
  const bMs = timeMs(b);
  if (aMs == null) return b ?? null;
  if (bMs == null) return a ?? null;
  return aMs <= bMs ? String(a) : String(b);
}

export function maxIso(a?: string | null, b?: string | null): string | null {
  const aMs = timeMs(a);
  const bMs = timeMs(b);
  if (aMs == null) return b ?? null;
  if (bMs == null) return a ?? null;
  return aMs >= bMs ? String(a) : String(b);
}

export function isHigherChartTimeframe(parentTf: string, childTf: string): boolean {
  const p = CHART_TF_RANK[normalizeChartTf(parentTf)] ?? 99;
  const c = CHART_TF_RANK[normalizeChartTf(childTf)] ?? 99;
  return p < c;
}

export function computeDraftBoundary(points: MappingPoint[]): { startTime: string | null; endTime: string | null } {
  const times = points
    .map((p) => timeMs(p.time))
    .filter((ms): ms is number => ms != null);
  if (!times.length) return { startTime: null, endTime: null };
  const min = Math.min(...times);
  const max = Math.max(...times);
  return {
    startTime: new Date(min).toISOString(),
    endTime: new Date(max).toISOString(),
  };
}

export function withDraftBoundary(draft: MappingDraft): MappingDraft {
  const computed = computeDraftBoundary(draft.points);
  return {
    ...draft,
    startTime: minIso(computed.startTime, draft.startTime),
    endTime: maxIso(computed.endTime, draft.endTime),
  };
}

/** Child draft end extends past active parent draft end. */
export function detectBoundaryOverflow(
  childDraft?: MappingDraft | null,
  parentDraft?: MappingDraft | null,
): boolean {
  const childEnd = timeMs(childDraft?.endTime);
  if (childEnd == null) return false;
  if (!parentDraft) return false;
  const parentEnd = timeMs(parentDraft.endTime);
  if (parentEnd == null) return true;
  return childEnd > parentEnd;
}

export function findRelinkCandidateTimeframes(
  draftsByTimeframe: Record<string, MappingDraft>,
  childTimeframe: string,
  childEndTime?: string | null,
): string[] {
  const childTf = normalizeChartTf(childTimeframe);
  const childEnd = timeMs(childEndTime);
  if (childEnd == null) return [];
  return Object.entries(draftsByTimeframe)
    .filter(([tf, draft]) => {
      if (normalizeChartTf(tf) === childTf) return false;
      if (!isHigherChartTimeframe(tf, childTf)) return false;
      const end = timeMs(draft.endTime);
      return end != null && end >= childEnd;
    })
    .map(([tf]) => normalizeChartTf(tf))
    .sort((a, b) => (CHART_TF_RANK[a] ?? 99) - (CHART_TF_RANK[b] ?? 99));
}

export function buildExtendedParentDraft(
  parentDraft: MappingDraft,
  childDraft: MappingDraft,
): MappingDraft {
  const child = withDraftBoundary(childDraft);
  const parent = withDraftBoundary(parentDraft);
  if (!child.endTime) return parent;
  return {
    ...parent,
    startTime: minIso(parent.startTime, child.startTime),
    endTime: maxIso(parent.endTime, child.endTime),
    updatedAt: new Date().toISOString(),
  };
}

export function buildRelinkedChildDraft(
  childDraft: MappingDraft,
  parentTimeframe: string,
): MappingDraft {
  return {
    ...withDraftBoundary(childDraft),
    linkedParentTimeframe: normalizeChartTf(parentTimeframe),
    updatedAt: new Date().toISOString(),
  };
}
