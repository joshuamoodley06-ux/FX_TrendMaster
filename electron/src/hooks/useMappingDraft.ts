import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  buildExtendedParentDraft,
  buildRelinkedChildDraft,
  detectBoundaryOverflow,
  findRelinkCandidateTimeframes,
  normalizeChartTf,
  withDraftBoundary,
} from '../mappingDraftBoundary';
import type { MappingDraft, MappingDraftPointInput, MappingPoint, MappingPointKind } from '../types';

export type UseMappingDraftArgs = {
  symbol: string;
  timeframe: string;
  caseId?: string | null;
  parentTimeframe?: string | null;
  childTimeframe?: string | null;
};

export type UseMappingDraftResult = {
  draft: MappingDraft;
  activeTimeframe: string;
  savePoint: (input: MappingDraftPointInput) => MappingPoint;
  removePoint: (pointId: string) => void;
  clearPoints: () => void;
  clearPointsForTimeframe: (tf: string) => void;
  replaceDraft: (next: MappingDraft) => void;
  pointCount: number;
  pointCountForTimeframe: (tf: string) => number;
  draftsByTimeframe: Record<string, MappingDraft>;
  childDraft: MappingDraft | null;
  parentDraft: MappingDraft | null;
  childEndTime: string | null;
  parentEndTime: string | null;
  linkedParentTimeframe: string | null;
  isOverflowing: boolean;
  relinkCandidates: string[];
  extendParentToChildBoundary: () => boolean;
  relinkChildToParent: (parentTf: string) => boolean;
  undoLastPoint: () => MappingPoint | null;
  canUndoPoint: boolean;
};

const STORAGE_KEY = 'fx_tm_mapping_drafts_v1';

function createId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function normalizeTf(tf?: string): string {
  return normalizeChartTf(tf || 'D1');
}

function containerKey(symbol: string, caseId?: string | null): string {
  return `${String(symbol || 'XAUUSD').toUpperCase()}|${String(caseId ?? '')}`;
}

export function createEmptyMappingDraft(args: UseMappingDraftArgs): MappingDraft {
  const now = new Date().toISOString();
  return {
    id: createId('mapping_draft'),
    symbol: String(args.symbol || 'XAUUSD').toUpperCase(),
    timeframe: normalizeTf(args.timeframe),
    caseId: args.caseId ?? null,
    points: [],
    startTime: null,
    endTime: null,
    linkedParentTimeframe: args.parentTimeframe ? normalizeTf(args.parentTimeframe) : null,
    updatedAt: now,
  };
}

function normalizeKind(kind?: MappingPointKind): MappingPointKind {
  if (kind === 'zone' || kind === 'anchor') return kind;
  return 'pivot';
}

function readStoredDrafts(key: string): Record<string, MappingDraft> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Record<string, MappingDraft>>;
    return parsed[key] || {};
  } catch {
    return {};
  }
}

function writeStoredDrafts(key: string, drafts: Record<string, MappingDraft>) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Record<string, Record<string, MappingDraft>> : {};
    parsed[key] = drafts;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
  } catch {
    /* ignore quota / private mode */
  }
}

export function useMappingDraft(args: UseMappingDraftArgs): UseMappingDraftResult {
  const activeTimeframe = normalizeTf(args.timeframe);
  const parentTimeframe = args.parentTimeframe ? normalizeTf(args.parentTimeframe) : null;
  const childTimeframe = normalizeTf(args.childTimeframe || args.timeframe);
  const storeKey = containerKey(args.symbol, args.caseId);
  const [draftsByTimeframe, setDraftsByTimeframe] = useState<Record<string, MappingDraft>>({});

  useEffect(() => {
    setDraftsByTimeframe(readStoredDrafts(storeKey));
  }, [storeKey]);

  useEffect(() => {
    writeStoredDrafts(storeKey, draftsByTimeframe);
  }, [storeKey, draftsByTimeframe]);

  const draft = useMemo(() => {
    const existing = draftsByTimeframe[activeTimeframe];
    if (existing) return withDraftBoundary(existing);
    return createEmptyMappingDraft({ ...args, timeframe: activeTimeframe });
  }, [draftsByTimeframe, activeTimeframe, args.symbol, args.caseId, args.parentTimeframe]);

  const childDraft = useMemo(() => {
    const row = draftsByTimeframe[childTimeframe];
    return row ? withDraftBoundary(row) : null;
  }, [draftsByTimeframe, childTimeframe]);

  const parentDraft = useMemo(() => {
    if (!parentTimeframe) return null;
    const row = draftsByTimeframe[parentTimeframe];
    return row ? withDraftBoundary(row) : null;
  }, [draftsByTimeframe, parentTimeframe]);

  const childEndTime = childDraft?.endTime ?? null;
  const parentEndTime = parentDraft?.endTime ?? null;
  const linkedParentTimeframe = childDraft?.linkedParentTimeframe ?? parentTimeframe;

  const isOverflowing = useMemo(
    () => detectBoundaryOverflow(childDraft, parentDraft),
    [childDraft, parentDraft],
  );

  const relinkCandidates = useMemo(
    () => findRelinkCandidateTimeframes(draftsByTimeframe, childTimeframe, childEndTime),
    [draftsByTimeframe, childTimeframe, childEndTime],
  );

  const upsertDraft = useCallback((updater: (prev: MappingDraft) => MappingDraft) => {
    setDraftsByTimeframe((prev) => {
      const current = prev[activeTimeframe] ?? createEmptyMappingDraft({ ...args, timeframe: activeTimeframe });
      return { ...prev, [activeTimeframe]: withDraftBoundary(updater(current)) };
    });
  }, [activeTimeframe, args.symbol, args.caseId, args.parentTimeframe]);

  const savePoint = useCallback((input: MappingDraftPointInput): MappingPoint => {
    const kind = normalizeKind(input.kind);
    const point: MappingPoint = {
      id: createId('mapping_point'),
      time: String(input.time || ''),
      price: Number(Number(input.price).toFixed(2)),
      kind,
      label: input.label?.trim() || undefined,
      createdAt: new Date().toISOString(),
    };
    upsertDraft((prev) => ({
      ...prev,
      timeframe: activeTimeframe,
      linkedParentTimeframe: prev.linkedParentTimeframe ?? parentTimeframe,
      points: [...prev.points, point],
      updatedAt: new Date().toISOString(),
    }));
    return point;
  }, [activeTimeframe, parentTimeframe, upsertDraft]);

  const removePoint = useCallback((pointId: string) => {
    upsertDraft((prev) => ({
      ...prev,
      points: prev.points.filter((p) => p.id !== pointId),
      updatedAt: new Date().toISOString(),
    }));
  }, [upsertDraft]);

  const undoLastPoint = useCallback((): MappingPoint | null => {
    let removed: MappingPoint | null = null;
    upsertDraft((prev) => {
      if (!prev.points.length) return prev;
      removed = prev.points[prev.points.length - 1];
      return {
        ...prev,
        points: prev.points.slice(0, -1),
        updatedAt: new Date().toISOString(),
      };
    });
    return removed;
  }, [upsertDraft]);

  const clearPoints = useCallback(() => {
    upsertDraft((prev) => ({
      ...prev,
      points: [],
      updatedAt: new Date().toISOString(),
    }));
  }, [upsertDraft]);

  const clearPointsForTimeframe = useCallback((tf: string) => {
    const key = normalizeTf(tf);
    setDraftsByTimeframe((prev) => {
      const current = prev[key];
      if (!current) return prev;
      return {
        ...prev,
        [key]: withDraftBoundary({ ...current, points: [], updatedAt: new Date().toISOString() }),
      };
    });
  }, []);

  const replaceDraft = useCallback((next: MappingDraft) => {
    const key = normalizeTf(next.timeframe);
    setDraftsByTimeframe((prev) => ({ ...prev, [key]: withDraftBoundary(next) }));
  }, []);

  const extendParentToChildBoundary = useCallback((): boolean => {
    if (!parentTimeframe || !childDraft?.endTime) return false;
    setDraftsByTimeframe((prev) => {
      const child = withDraftBoundary(prev[childTimeframe] ?? createEmptyMappingDraft({ ...args, timeframe: childTimeframe }));
      const parentBase = prev[parentTimeframe] ?? createEmptyMappingDraft({ ...args, timeframe: parentTimeframe });
      const extendedParent = buildExtendedParentDraft(parentBase, child);
      const relinkedChild = buildRelinkedChildDraft(child, parentTimeframe);
      return {
        ...prev,
        [parentTimeframe]: extendedParent,
        [childTimeframe]: relinkedChild,
      };
    });
    return true;
  }, [args, childDraft?.endTime, childTimeframe, parentTimeframe]);

  const relinkChildToParent = useCallback((targetParentTf: string): boolean => {
    const parentTf = normalizeTf(targetParentTf);
    if (!childDraft?.endTime) return false;
    const candidate = draftsByTimeframe[parentTf];
    if (!candidate?.endTime) return false;
    if (new Date(candidate.endTime).getTime() < new Date(childDraft.endTime).getTime()) return false;
    setDraftsByTimeframe((prev) => {
      const child = withDraftBoundary(prev[childTimeframe] ?? createEmptyMappingDraft({ ...args, timeframe: childTimeframe }));
      return {
        ...prev,
        [childTimeframe]: buildRelinkedChildDraft(child, parentTf),
      };
    });
    return true;
  }, [args, childDraft?.endTime, childTimeframe, draftsByTimeframe]);

  const pointCount = useMemo(() => draft.points.length, [draft.points.length]);

  const pointCountForTimeframe = useCallback(
    (tf: string) => draftsByTimeframe[normalizeTf(tf)]?.points.length ?? 0,
    [draftsByTimeframe],
  );

  return {
    draft,
    activeTimeframe,
    savePoint,
    removePoint,
    undoLastPoint,
    canUndoPoint: draft.points.length > 0,
    clearPoints,
    clearPointsForTimeframe,
    replaceDraft,
    pointCount,
    pointCountForTimeframe,
    draftsByTimeframe,
    childDraft,
    parentDraft,
    childEndTime,
    parentEndTime,
    linkedParentTimeframe,
    isOverflowing,
    relinkCandidates,
    extendParentToChildBoundary,
    relinkChildToParent,
  };
}
