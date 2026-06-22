import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import {
  activeRangeIdForLayer,
  buildMappingSessionState,
  clearMappingSession,
  loadMappingSession,
  saveMappingSession,
  type MappingSessionLayer,
  type MappingSessionState,
} from '../mappingSessionPersistence';
import type { ChildMappingPhase } from '../childMappingWorkflow';
import type { GuidedCursorStatus } from '../guidedMappingCursor';

export type MappingSessionStructureLayer = MappingSessionLayer;

export type MappingSessionOrchestration = 'idle' | 'pending_modal' | 'resuming';

export type MappingSessionSnapshot = {
  symbol: string;
  caseId?: number | null;
  rawCaseId?: string | null;
  caseRef?: string | null;
  year: string;
  structureLayer: MappingSessionStructureLayer;
  activeWeeklyRangeId?: string | null;
  activeDailyRangeId?: string | null;
  activeIntradayRangeId?: string | null;
  activeMicroRangeId?: string | null;
  selectedParentRangeId?: string | null;
  activeStructuralRangeId?: string | null;
  chartTimeframe: string;
  sourceTimeframe: string;
  rangeScope: 'MAJOR' | 'MINOR';
  researchWindowStart?: string | null;
  researchWindowEnd?: string | null;
  currentCandidateIndex?: number;
  childMappingActive?: boolean;
  childMappingDetectionRunId?: string | null;
  childMappingPhase?: ChildMappingPhase | null;
  guidedCursorActive?: boolean;
  guidedCampaignYear?: string | null;
  guidedParentRangeId?: string | null;
  guidedParentLayer?: string | null;
  guidedChildLayer?: string | null;
  guidedCursorTimeMs?: number | null;
  guidedParentStartMs?: number | null;
  guidedParentEndMs?: number | null;
  guidedParentRh?: number | null;
  guidedParentRl?: number | null;
  guidedCurrentChildRangeId?: string | null;
  guidedCurrentChildIndex?: number;
  guidedCursorStatus?: GuidedCursorStatus | null;
  guidedPendingBosDirection?: 'UP' | 'DOWN' | null;
  guidedPendingBosTime?: string | null;
  guidedPendingBosPrice?: number | null;
  guidedSavedChildIds?: string[];
};

export type MappingSessionScopeActions = {
  setStructureLayer: (layer: MappingSessionStructureLayer) => void;
  setRangeScope: (scope: 'MAJOR' | 'MINOR') => void;
  setSourceTimeframe: (tf: string) => void;
  setTimeframe: (tf: string) => void;
  setSelectedParentRangeId: (id: string) => void;
  setActiveStructuralRangeId: (id: string) => void;
  setExplorerYearFilter: (year: string) => void;
  setRawActiveCaseId?: (id: string) => void;
  onSymbolChange?: (symbol: string) => void;
};

export type MappingSessionRestoreActions = MappingSessionScopeActions & {
  selectSavedStructuralRange?: (range: any, opts?: { routeInspector?: boolean }) => void;
  savedStructuralRanges?: any[];
};

export type MappingSessionResumeResult = {
  message: string;
  staleParentId: string | null;
  staleActiveId: string | null;
  restoredActive: boolean;
  restoredParent: boolean;
  chartTimeframe: string;
};

export type ExecuteMappingSessionResumeArgs = {
  stored: MappingSessionState;
  scopeActions: MappingSessionScopeActions;
  hasCase: () => boolean;
  refreshSavedRanges: () => Promise<any[]>;
  refreshMapEvents: (timeframe: string) => Promise<void>;
  loadCandles: (timeframe: string) => Promise<void>;
  selectSavedStructuralRange: (range: any, opts?: { routeInspector?: boolean }) => void;
};

function normalizeLayer(value: unknown): MappingSessionLayer | null {
  const layer = String(value || '').trim().toUpperCase();
  if (layer === 'MACRO' || layer === 'WEEKLY' || layer === 'DAILY' || layer === 'INTRADAY' || layer === 'MICRO') {
    return layer;
  }
  return null;
}

export function isMappingSessionOrchestrating(
  orchestrationRef: RefObject<MappingSessionOrchestration>,
): boolean {
  return orchestrationRef.current !== 'idle';
}

export function readMappingSessionForSymbol(symbol: string): MappingSessionState | null {
  const stored = loadMappingSession();
  if (!stored) return null;
  if (String(stored.symbol).toUpperCase() !== String(symbol).toUpperCase()) return null;
  return stored;
}

export function findSavedRangeById(ranges: any[], id: string | null | undefined): any | null {
  if (!id) return null;
  const needle = String(id);
  return ranges.find((row: any) => String(row.range_id || row.id) === needle) || null;
}

export function validateMappingSessionRangeIds(
  stored: MappingSessionState,
  ranges: any[],
): {
  parentId: string | null;
  activeId: string | null;
  staleParentId: string | null;
  staleActiveId: string | null;
  parentRow: any | null;
  activeRow: any | null;
} {
  const parentRaw = stored.current_parent_range_id ? String(stored.current_parent_range_id) : null;
  const layerActiveId = activeRangeIdForLayer(stored, stored.active_layer);
  const activeRaw = stored.active_structural_range_id
    ? String(stored.active_structural_range_id)
    : (layerActiveId ? String(layerActiveId) : null);

  const parentRow = findSavedRangeById(ranges, parentRaw);
  const activeRow = findSavedRangeById(ranges, activeRaw);

  return {
    parentId: parentRow ? String(parentRaw) : null,
    activeId: activeRow ? String(activeRaw) : null,
    staleParentId: parentRaw && !parentRow ? parentRaw : null,
    staleActiveId: activeRaw && !activeRow ? activeRaw : null,
    parentRow,
    activeRow,
  };
}

export function snapshotToMappingSession(snapshot: MappingSessionSnapshot): MappingSessionState {
  return buildMappingSessionState({
    symbol: snapshot.symbol,
    caseId: snapshot.caseId ?? null,
    rawCaseId: snapshot.rawCaseId ?? null,
    caseRef: snapshot.caseRef ?? null,
    year: snapshot.year,
    activeLayer: snapshot.structureLayer as MappingSessionLayer,
    activeWeeklyRangeId: snapshot.activeWeeklyRangeId ?? null,
    activeDailyRangeId: snapshot.activeDailyRangeId ?? null,
    activeIntradayRangeId: snapshot.activeIntradayRangeId ?? null,
    activeMicroRangeId: snapshot.activeMicroRangeId ?? null,
    currentParentRangeId: snapshot.selectedParentRangeId ?? null,
    activeStructuralRangeId: snapshot.activeStructuralRangeId ?? null,
    chartTimeframe: snapshot.chartTimeframe,
    sourceTimeframe: snapshot.sourceTimeframe,
    rangeScope: snapshot.rangeScope,
    researchWindowStart: snapshot.researchWindowStart ?? null,
    researchWindowEnd: snapshot.researchWindowEnd ?? null,
    currentCandidateIndex: snapshot.currentCandidateIndex ?? 0,
    childMappingActive: snapshot.childMappingActive === true,
    childMappingDetectionRunId: snapshot.childMappingDetectionRunId ?? null,
    childMappingPhase: snapshot.childMappingPhase ?? null,
    guidedCursorActive: snapshot.guidedCursorActive === true,
    guidedCampaignYear: snapshot.guidedCampaignYear ?? null,
    guidedParentRangeId: snapshot.guidedParentRangeId ?? null,
    guidedParentLayer: snapshot.guidedParentLayer ?? null,
    guidedChildLayer: snapshot.guidedChildLayer ?? null,
    guidedCursorTimeMs: snapshot.guidedCursorTimeMs ?? null,
    guidedParentStartMs: snapshot.guidedParentStartMs ?? null,
    guidedParentEndMs: snapshot.guidedParentEndMs ?? null,
    guidedParentRh: snapshot.guidedParentRh ?? null,
    guidedParentRl: snapshot.guidedParentRl ?? null,
    guidedCurrentChildRangeId: snapshot.guidedCurrentChildRangeId ?? null,
    guidedCurrentChildIndex: snapshot.guidedCurrentChildIndex ?? 0,
    guidedCursorStatus: snapshot.guidedCursorStatus ?? null,
    guidedPendingBosDirection: snapshot.guidedPendingBosDirection ?? null,
    guidedPendingBosTime: snapshot.guidedPendingBosTime ?? null,
    guidedPendingBosPrice: snapshot.guidedPendingBosPrice ?? null,
    guidedSavedChildIds: snapshot.guidedSavedChildIds ?? [],
  });
}

/** Scope restore without parent/active/year/chart TF when deferChartTimeframe is true. */
export function applyMappingSessionScopeRestore(
  stored: MappingSessionState,
  actions: MappingSessionScopeActions,
  opts?: { deferChartTimeframe?: boolean },
): void {
  if (stored.symbol && actions.onSymbolChange) {
    actions.onSymbolChange(String(stored.symbol).toUpperCase());
  }
  actions.setStructureLayer(stored.active_layer);
  actions.setRangeScope(stored.range_scope);
  actions.setSourceTimeframe(stored.source_timeframe);
  if (!opts?.deferChartTimeframe) {
    actions.setTimeframe(stored.chart_timeframe);
  }
  if (stored.raw_case_id && actions.setRawActiveCaseId) {
    actions.setRawActiveCaseId(String(stored.raw_case_id));
  }
}

/** @deprecated Use applyMappingSessionScopeRestore + executeMappingSessionResume instead. */
export function applyMappingSessionRestore(
  stored: MappingSessionState,
  actions: MappingSessionRestoreActions,
): void {
  applyMappingSessionScopeRestore(stored, actions);
  if (stored.year) actions.setExplorerYearFilter(stored.year);
  if (stored.current_parent_range_id) {
    actions.setSelectedParentRangeId(String(stored.current_parent_range_id));
  }
  const activeId = stored.active_structural_range_id || activeRangeIdForLayer(stored, stored.active_layer);
  if (activeId && actions.selectSavedStructuralRange && actions.savedStructuralRanges?.length) {
    const row = actions.savedStructuralRanges.find(
      (r: any) => String(r.range_id || r.id) === String(activeId),
    );
    if (row) {
      actions.selectSavedStructuralRange(row, { routeInspector: false });
      return;
    }
  }
  if (activeId) actions.setActiveStructuralRangeId(String(activeId));
}

export function buildMappingSessionResumeMessage(
  stored: MappingSessionState,
  validation: ReturnType<typeof validateMappingSessionRangeIds>,
): string {
  const parts = [
    `Resumed mapping session · ${stored.active_layer} · ${stored.chart_timeframe}`,
  ];
  if (validation.staleActiveId) {
    parts.push(`Active range #${validation.staleActiveId} is no longer in the case — cleared.`);
  }
  if (validation.staleParentId) {
    parts.push(`Parent range #${validation.staleParentId} is no longer in the case — cleared.`);
  }
  return parts.join(' · ');
}

export async function executeMappingSessionResume(
  args: ExecuteMappingSessionResumeArgs,
): Promise<MappingSessionResumeResult> {
  const { stored, scopeActions } = args;
  const chartTimeframe = String(stored.chart_timeframe || 'D1').toUpperCase();

  applyMappingSessionScopeRestore(stored, scopeActions, { deferChartTimeframe: true });

  let ranges: any[] = [];
  if (args.hasCase()) {
    try {
      ranges = await args.refreshSavedRanges();
    } catch {
      ranges = [];
    }
  }

  const validation = validateMappingSessionRangeIds(stored, ranges);

  if (validation.activeRow) {
    args.selectSavedStructuralRange(validation.activeRow, { routeInspector: false });
  } else {
    scopeActions.setActiveStructuralRangeId('');
    if (validation.parentRow) {
      scopeActions.setSelectedParentRangeId(String(validation.parentId));
    } else {
      scopeActions.setSelectedParentRangeId('');
    }
  }

  scopeActions.setTimeframe(chartTimeframe);
  await args.loadCandles(chartTimeframe);

  if (args.hasCase()) {
    try {
      await args.refreshMapEvents(chartTimeframe);
    } catch {
      /* non-blocking */
    }
  }

  scopeActions.setExplorerYearFilter(stored.year ? String(stored.year) : 'all');

  return {
    message: buildMappingSessionResumeMessage(stored, validation),
    staleParentId: validation.staleParentId,
    staleActiveId: validation.staleActiveId,
    restoredActive: !!validation.activeRow,
    restoredParent: !!(validation.activeRow?.parent_range_id || validation.parentRow),
    chartTimeframe,
  };
}

export function useMappingSessionPersistence(
  snapshot: MappingSessionSnapshot,
  options?: { bootDelayMs?: number },
) {
  const [pendingResume, setPendingResume] = useState<MappingSessionState | null>(null);
  const orchestrationRef = useRef<MappingSessionOrchestration>('idle');
  const bootCheckedRef = useRef(false);
  const lastSavedRef = useRef('');
  const persistBlockedRef = useRef(false);

  useEffect(() => {
    if (bootCheckedRef.current) return;
    const timer = window.setTimeout(() => {
      bootCheckedRef.current = true;
      const stored = readMappingSessionForSymbol(snapshot.symbol);
      if (!stored) {
        persistBlockedRef.current = false;
        orchestrationRef.current = 'idle';
        return;
      }
      persistBlockedRef.current = true;
      orchestrationRef.current = 'pending_modal';
      setPendingResume(stored);
    }, options?.bootDelayMs ?? 300);
    return () => window.clearTimeout(timer);
  }, [snapshot.symbol, options?.bootDelayMs]);

  useEffect(() => {
    if (persistBlockedRef.current || pendingResume) return;
    const next = snapshotToMappingSession(snapshot);
    const serial = JSON.stringify(next);
    if (serial === lastSavedRef.current) return;
    lastSavedRef.current = serial;
    saveMappingSession(next);
  }, [snapshot, pendingResume]);

  const beginResumeFlow = useCallback(() => {
    orchestrationRef.current = 'resuming';
  }, []);

  const completeResumeFlow = useCallback(() => {
    persistBlockedRef.current = false;
    orchestrationRef.current = 'idle';
    setPendingResume(null);
  }, []);

  const startNewSession = useCallback(() => {
    clearMappingSession();
    persistBlockedRef.current = false;
    orchestrationRef.current = 'idle';
    setPendingResume(null);
    lastSavedRef.current = '';
  }, []);

  return {
    pendingResume,
    orchestrationRef,
    beginResumeFlow,
    completeResumeFlow,
    startNewSession,
    isPersistBlocked: pendingResume !== null,
  };
}

export function deriveLayerActiveIdsFromRanges(
  ranges: any[],
  activeStructuralRangeId: string,
): Pick<
  MappingSessionSnapshot,
  'activeWeeklyRangeId' | 'activeDailyRangeId' | 'activeIntradayRangeId' | 'activeMicroRangeId'
> {
  const out = {
    activeWeeklyRangeId: null as string | null,
    activeDailyRangeId: null as string | null,
    activeIntradayRangeId: null as string | null,
    activeMicroRangeId: null as string | null,
  };
  const assign = (layer: MappingSessionLayer | null, id: string) => {
    if (!layer || !id) return;
    if (layer === 'MACRO' || layer === 'WEEKLY') out.activeWeeklyRangeId = id;
    if (layer === 'DAILY') out.activeDailyRangeId = id;
    if (layer === 'INTRADAY') out.activeIntradayRangeId = id;
    if (layer === 'MICRO') out.activeMicroRangeId = id;
  };

  let currentId = String(activeStructuralRangeId || '').trim();
  const seen = new Set<string>();
  while (currentId && !seen.has(currentId)) {
    seen.add(currentId);
    const row = ranges.find((r: any) => String(r.range_id || r.id) === currentId);
    if (!row) break;
    assign(normalizeLayer(row.structure_layer || row.layer), currentId);
    const parentId = row.parent_range_id;
    currentId = parentId !== undefined && parentId !== null && String(parentId).trim() !== ''
      ? String(parentId)
      : '';
  }
  return out;
}
