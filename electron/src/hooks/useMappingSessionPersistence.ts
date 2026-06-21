import { useCallback, useEffect, useRef, useState } from 'react';
import {
  activeRangeIdForLayer,
  buildMappingSessionState,
  clearMappingSession,
  loadMappingSession,
  saveMappingSession,
  type MappingSessionLayer,
  type MappingSessionState,
} from '../mappingSessionPersistence';

export type MappingSessionStructureLayer = MappingSessionLayer;

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
};

export type MappingSessionRestoreActions = {
  setStructureLayer: (layer: MappingSessionStructureLayer) => void;
  setRangeScope: (scope: 'MAJOR' | 'MINOR') => void;
  setSourceTimeframe: (tf: string) => void;
  setTimeframe: (tf: string) => void;
  setSelectedParentRangeId: (id: string) => void;
  setActiveStructuralRangeId: (id: string) => void;
  setExplorerYearFilter: (year: string) => void;
  setRawActiveCaseId?: (id: string) => void;
  onSymbolChange?: (symbol: string) => void;
  selectSavedStructuralRange?: (range: any, opts?: { routeInspector?: boolean }) => void;
  savedStructuralRanges?: any[];
};

function normalizeLayer(value: unknown): MappingSessionLayer | null {
  const layer = String(value || '').trim().toUpperCase();
  if (layer === 'MACRO' || layer === 'WEEKLY' || layer === 'DAILY' || layer === 'INTRADAY' || layer === 'MICRO') {
    return layer;
  }
  return null;
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
  });
}

export function applyMappingSessionRestore(
  stored: MappingSessionState,
  actions: MappingSessionRestoreActions,
): void {
  if (stored.symbol && actions.onSymbolChange) {
    actions.onSymbolChange(String(stored.symbol).toUpperCase());
  }
  actions.setStructureLayer(stored.active_layer);
  actions.setRangeScope(stored.range_scope);
  actions.setSourceTimeframe(stored.source_timeframe);
  actions.setTimeframe(stored.chart_timeframe);
  if (stored.year) actions.setExplorerYearFilter(stored.year);
  if (stored.raw_case_id && actions.setRawActiveCaseId) {
    actions.setRawActiveCaseId(String(stored.raw_case_id));
  }
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

export function useMappingSessionPersistence(
  snapshot: MappingSessionSnapshot,
  actions: MappingSessionRestoreActions,
  options?: { enabled?: boolean; bootDelayMs?: number },
) {
  const enabled = options?.enabled !== false;
  const [pendingResume, setPendingResume] = useState<MappingSessionState | null>(null);
  const bootCheckedRef = useRef(false);
  const lastSavedRef = useRef('');

  useEffect(() => {
    if (!enabled || bootCheckedRef.current) return;
    bootCheckedRef.current = true;
    const stored = loadMappingSession();
    if (!stored) return;
    if (String(stored.symbol).toUpperCase() !== String(snapshot.symbol).toUpperCase()) {
      return;
    }
    const timer = window.setTimeout(() => setPendingResume(stored), options?.bootDelayMs ?? 350);
    return () => window.clearTimeout(timer);
  }, [enabled, snapshot.symbol, options?.bootDelayMs]);

  useEffect(() => {
    if (!enabled) return;
    const next = snapshotToMappingSession(snapshot);
    const serial = JSON.stringify(next);
    if (serial === lastSavedRef.current) return;
    lastSavedRef.current = serial;
    saveMappingSession(next);
  }, [enabled, snapshot]);

  const resumeSession = useCallback(() => {
    if (!pendingResume) return;
    applyMappingSessionRestore(pendingResume, actions);
    setPendingResume(null);
  }, [pendingResume, actions]);

  const startNewSession = useCallback(() => {
    clearMappingSession();
    setPendingResume(null);
    lastSavedRef.current = '';
  }, []);

  const dismissResume = useCallback(() => {
    setPendingResume(null);
  }, []);

  return {
    pendingResume,
    resumeSession,
    startNewSession,
    dismissResume,
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
