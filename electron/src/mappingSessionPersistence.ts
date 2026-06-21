/** Local persistence for structural mapping session (Electron only). */

import type { ChildMappingPhase } from './childMappingWorkflow';
import type { GuidedCursorStatus } from './guidedMappingCursor';

export const MAPPING_SESSION_STORAGE_KEY = 'fx_tm_mapping_session_v1';

export type MappingSessionLayer = 'MACRO' | 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO';

export type MappingSessionState = {
  version: 1;
  updated_at_ms: number;
  symbol: string;
  case_id?: number | null;
  raw_case_id?: string | null;
  case_ref?: string | null;

  year: string;
  active_layer: MappingSessionLayer;

  active_weekly_range_id: string | null;
  active_daily_range_id: string | null;
  active_intraday_range_id: string | null;
  active_micro_range_id: string | null;

  current_parent_range_id: string | null;
  current_parent_daily_id: string | null;
  current_parent_intraday_id: string | null;
  active_structural_range_id: string | null;

  chart_timeframe: string;
  source_timeframe: string;
  range_scope: 'MAJOR' | 'MINOR';

  research_window_start: string | null;
  research_window_end: string | null;

  current_candidate_index: number;

  child_mapping_active: boolean;
  child_mapping_detection_run_id: string | null;
  child_mapping_phase: ChildMappingPhase | null;

  guided_cursor_active: boolean;
  guided_campaign_year: string | null;
  guided_parent_range_id: string | null;
  guided_parent_layer: string | null;
  guided_child_layer: string | null;
  guided_cursor_time_ms: number | null;
  guided_parent_start_ms: number | null;
  guided_parent_end_ms: number | null;
  guided_parent_rh: number | null;
  guided_parent_rl: number | null;
  guided_current_child_range_id: string | null;
  guided_current_child_index: number;
  guided_cursor_status: GuidedCursorStatus | null;
  guided_pending_bos_direction: 'UP' | 'DOWN' | null;
  guided_pending_bos_time: string | null;
  guided_pending_bos_price: number | null;
  guided_saved_child_ids: string[];
};

export type BuildMappingSessionArgs = {
  symbol: string;
  caseId?: number | null;
  rawCaseId?: string | null;
  caseRef?: string | null;
  year: string;
  activeLayer: MappingSessionLayer;
  activeWeeklyRangeId?: string | null;
  activeDailyRangeId?: string | null;
  activeIntradayRangeId?: string | null;
  activeMicroRangeId?: string | null;
  currentParentRangeId?: string | null;
  currentParentDailyId?: string | null;
  currentParentIntradayId?: string | null;
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

const LAYER_RANGE_FIELD: Record<MappingSessionLayer, keyof Pick<
  MappingSessionState,
  'active_weekly_range_id' | 'active_daily_range_id' | 'active_intraday_range_id' | 'active_micro_range_id'
> | 'active_weekly_range_id'> = {
  MACRO: 'active_weekly_range_id',
  WEEKLY: 'active_weekly_range_id',
  DAILY: 'active_daily_range_id',
  INTRADAY: 'active_intraday_range_id',
  MICRO: 'active_micro_range_id',
};

function normalizeId(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  return String(value);
}

export function yearFromWindow(start?: string | null, end?: string | null, fallback = 'all'): string {
  const raw = start || end || '';
  const match = String(raw).match(/^(\d{4})/);
  return match ? match[1] : fallback;
}

export function buildMappingSessionState(args: BuildMappingSessionArgs): MappingSessionState {
  return {
    version: 1,
    updated_at_ms: Date.now(),
    symbol: args.symbol,
    case_id: args.caseId ?? null,
    raw_case_id: args.rawCaseId ?? null,
    case_ref: args.caseRef ?? null,
    year: args.year,
    active_layer: args.activeLayer,
    active_weekly_range_id: normalizeId(args.activeWeeklyRangeId),
    active_daily_range_id: normalizeId(args.activeDailyRangeId),
    active_intraday_range_id: normalizeId(args.activeIntradayRangeId),
    active_micro_range_id: normalizeId(args.activeMicroRangeId),
    current_parent_range_id: normalizeId(args.currentParentRangeId),
    current_parent_daily_id: normalizeId(args.currentParentDailyId),
    current_parent_intraday_id: normalizeId(args.currentParentIntradayId),
    active_structural_range_id: normalizeId(args.activeStructuralRangeId),
    chart_timeframe: String(args.chartTimeframe || 'D1').toUpperCase(),
    source_timeframe: String(args.sourceTimeframe || 'D1').toUpperCase(),
    range_scope: args.rangeScope === 'MINOR' ? 'MINOR' : 'MAJOR',
    research_window_start: args.researchWindowStart ? String(args.researchWindowStart) : null,
    research_window_end: args.researchWindowEnd ? String(args.researchWindowEnd) : null,
    current_candidate_index: Number.isFinite(args.currentCandidateIndex)
      ? Math.max(0, Number(args.currentCandidateIndex))
      : 0,
    child_mapping_active: args.childMappingActive === true,
    child_mapping_detection_run_id: args.childMappingDetectionRunId
      ? String(args.childMappingDetectionRunId)
      : null,
    child_mapping_phase: args.childMappingPhase ?? null,
    guided_cursor_active: args.guidedCursorActive === true,
    guided_campaign_year: args.guidedCampaignYear ? String(args.guidedCampaignYear) : null,
    guided_parent_range_id: normalizeId(args.guidedParentRangeId),
    guided_parent_layer: args.guidedParentLayer ? String(args.guidedParentLayer) : null,
    guided_child_layer: args.guidedChildLayer ? String(args.guidedChildLayer) : null,
    guided_cursor_time_ms: Number.isFinite(args.guidedCursorTimeMs) ? Number(args.guidedCursorTimeMs) : null,
    guided_parent_start_ms: Number.isFinite(args.guidedParentStartMs) ? Number(args.guidedParentStartMs) : null,
    guided_parent_end_ms: Number.isFinite(args.guidedParentEndMs) ? Number(args.guidedParentEndMs) : null,
    guided_parent_rh: Number.isFinite(args.guidedParentRh) ? Number(args.guidedParentRh) : null,
    guided_parent_rl: Number.isFinite(args.guidedParentRl) ? Number(args.guidedParentRl) : null,
    guided_current_child_range_id: normalizeId(args.guidedCurrentChildRangeId),
    guided_current_child_index: Number.isFinite(args.guidedCurrentChildIndex)
      ? Math.max(0, Number(args.guidedCurrentChildIndex))
      : 0,
    guided_cursor_status: args.guidedCursorStatus ?? null,
    guided_pending_bos_direction: args.guidedPendingBosDirection ?? null,
    guided_pending_bos_time: args.guidedPendingBosTime ? String(args.guidedPendingBosTime) : null,
    guided_pending_bos_price: Number.isFinite(args.guidedPendingBosPrice) ? Number(args.guidedPendingBosPrice) : null,
    guided_saved_child_ids: Array.isArray(args.guidedSavedChildIds) ? args.guidedSavedChildIds.map(String) : [],
  };
}

export function loadMappingSession(): MappingSessionState | null {
  try {
    const raw = localStorage.getItem(MAPPING_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MappingSessionState;
    if (!parsed || parsed.version !== 1 || !parsed.symbol || !parsed.active_layer) return null;
    if (parsed.current_parent_daily_id === undefined) {
      parsed.current_parent_daily_id = null;
    }
    if (parsed.current_parent_intraday_id === undefined) {
      parsed.current_parent_intraday_id = null;
    }
    if (parsed.guided_cursor_active === undefined) parsed.guided_cursor_active = false;
    if (parsed.guided_campaign_year === undefined) parsed.guided_campaign_year = null;
    if (parsed.guided_parent_range_id === undefined) parsed.guided_parent_range_id = null;
    if (parsed.guided_parent_layer === undefined) parsed.guided_parent_layer = null;
    if (parsed.guided_child_layer === undefined) parsed.guided_child_layer = null;
    if (parsed.guided_cursor_time_ms === undefined) parsed.guided_cursor_time_ms = null;
    if (parsed.guided_parent_start_ms === undefined) parsed.guided_parent_start_ms = null;
    if (parsed.guided_parent_end_ms === undefined) parsed.guided_parent_end_ms = null;
    if (parsed.guided_parent_rh === undefined) parsed.guided_parent_rh = null;
    if (parsed.guided_parent_rl === undefined) parsed.guided_parent_rl = null;
    if (parsed.guided_current_child_range_id === undefined) parsed.guided_current_child_range_id = null;
    if (parsed.guided_current_child_index === undefined) parsed.guided_current_child_index = 0;
    if (parsed.guided_cursor_status === undefined) parsed.guided_cursor_status = null;
    if (parsed.guided_pending_bos_direction === undefined) parsed.guided_pending_bos_direction = null;
    if (parsed.guided_pending_bos_time === undefined) parsed.guided_pending_bos_time = null;
    if (parsed.guided_pending_bos_price === undefined) parsed.guided_pending_bos_price = null;
    if (parsed.guided_saved_child_ids === undefined) parsed.guided_saved_child_ids = [];
    return parsed;
  } catch {
    return null;
  }
}

export function saveMappingSession(state: MappingSessionState): void {
  try {
    localStorage.setItem(MAPPING_SESSION_STORAGE_KEY, JSON.stringify({
      ...state,
      version: 1,
      updated_at_ms: Date.now(),
    }));
  } catch {
    // ignore quota errors
  }
}

export function clearMappingSession(): void {
  try {
    localStorage.removeItem(MAPPING_SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
}

export function hasMappingSession(): boolean {
  return loadMappingSession() !== null;
}

export function activeRangeIdForLayer(
  state: MappingSessionState,
  layer?: MappingSessionLayer,
): string | null {
  const key = LAYER_RANGE_FIELD[layer || state.active_layer];
  return normalizeId(state[key]);
}

export function withActiveRangeForLayer(
  state: MappingSessionState,
  layer: MappingSessionLayer,
  rangeId: string | null,
): MappingSessionState {
  const key = LAYER_RANGE_FIELD[layer];
  return { ...state, [key]: normalizeId(rangeId) };
}

export function formatMappingSessionStatusLine(state: MappingSessionState | null): string | null {
  if (!state) return null;
  const parts = [
    'Mapping Session',
    state.year || '—',
    state.active_layer,
  ];
  if (state.active_weekly_range_id) parts.push(`Weekly #${state.active_weekly_range_id}`);
  if (state.active_daily_range_id) parts.push(`Daily #${state.active_daily_range_id}`);
  if (state.active_intraday_range_id) parts.push(`Intraday #${state.active_intraday_range_id}`);
  if (state.active_micro_range_id) parts.push(`Micro #${state.active_micro_range_id}`);
  if (state.guided_cursor_active && state.guided_parent_layer && state.guided_parent_range_id) {
    parts.push(`Guided ${state.guided_child_layer || '?'} @ ${state.guided_parent_layer} #${state.guided_parent_range_id}`);
  }
  if (state.child_mapping_active && state.current_parent_intraday_id && !state.active_micro_range_id) {
    parts.push(`Intraday parent #${state.current_parent_intraday_id}`);
  } else if (state.child_mapping_active && state.current_parent_daily_id && !state.active_intraday_range_id) {
    parts.push(`Daily parent #${state.current_parent_daily_id}`);
  } else if (state.child_mapping_active && state.current_parent_range_id && !state.active_daily_range_id) {
    parts.push(`Parent #${state.current_parent_range_id}`);
  }
  return parts.join(' · ');
}

/** Parent range id for restoring an active child-mapping workflow. */
export function childMappingParentIdForResume(stored: MappingSessionState): string | null {
  if (!stored.child_mapping_active) return null;
  if (stored.active_layer === 'MICRO') {
    return stored.current_parent_intraday_id
      || stored.active_intraday_range_id
      || stored.current_parent_range_id;
  }
  if (stored.active_layer === 'INTRADAY') {
    return stored.current_parent_daily_id
      || stored.active_daily_range_id
      || stored.current_parent_range_id;
  }
  if (stored.active_layer === 'DAILY') {
    return stored.active_weekly_range_id || stored.current_parent_range_id;
  }
  return stored.current_parent_range_id;
}

export function sessionTargetsRange(
  state: MappingSessionState,
  rangeId: string,
  rangeLayer: MappingSessionLayer,
): MappingSessionState {
  const id = normalizeId(rangeId);
  let next = { ...state, active_layer: rangeLayer, active_structural_range_id: id };
  next = withActiveRangeForLayer(next, rangeLayer, id);
  if (rangeLayer === 'DAILY') {
    next.current_parent_range_id = next.active_weekly_range_id;
    next.current_parent_daily_id = null;
    next.current_parent_intraday_id = null;
  } else if (rangeLayer === 'INTRADAY') {
    next.current_parent_range_id = next.active_daily_range_id;
    next.current_parent_daily_id = next.active_daily_range_id;
    next.current_parent_intraday_id = null;
  } else if (rangeLayer === 'MICRO') {
    next.current_parent_range_id = next.active_intraday_range_id;
    next.current_parent_intraday_id = next.active_intraday_range_id;
    next.current_parent_daily_id = null;
  } else if (rangeLayer === 'WEEKLY') {
    next.current_parent_range_id = null;
    next.current_parent_daily_id = null;
    next.current_parent_intraday_id = null;
  }
  return next;
}
