/** Auto-hierarchy child mapping — Weekly → Daily → Intraday (UI workflow only). */

import type { MappingGap } from './mappingWorkflow';
import {
  listDetectorRunLocalResearch,
  runHistoricalRangeScanLocal,
  type LocalResearchRunResult,
} from './localResearchClient';
import type { RangeAuditSample } from './reviewCandidateClient';
import { scanSummaryFromResult, suggestionIdFromSample } from './localResearchWorkflow';

export type ChildMappingPhase = 'idle' | 'scanning' | 'reviewing' | 'done';

export type ParentResearchWindow = {
  start: string;
  end: string;
  dateFrom: string;
  dateTo: string;
};

export type ChildMappingSession = {
  parentRangeId: string;
  parentLayer: string;
  childLayer: string;
  childSourceTf: string;
  parentRange: Record<string, unknown>;
  researchWindow: ParentResearchWindow;
  detectionRunId: string | null;
  candidateIndex: number;
  candidates: RangeAuditSample[];
  phase: ChildMappingPhase;
};

const CHILD_LAYER_BY_PARENT: Record<string, string> = {
  MACRO: 'WEEKLY',
  WEEKLY: 'DAILY',
  DAILY: 'INTRADAY',
};

const CHILD_SOURCE_TF: Record<string, string> = {
  WEEKLY: 'W1',
  DAILY: 'D1',
  INTRADAY: 'H1',
  MICRO: 'M15',
};

/** Default chart TF when opening child mapping (may differ from source on INTRADAY). */
const CHILD_CHART_TF: Record<string, string> = {
  WEEKLY: 'W1',
  DAILY: 'D1',
  INTRADAY: 'H1',
  MICRO: 'M15',
};

function normalizeLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function isoDay(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const raw = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10);
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  if (!Number.isFinite(ms)) return '';
  return new Date(ms).toISOString().slice(0, 10);
}

export function expectedChildLayerForParent(parentLayer: string): string | null {
  return CHILD_LAYER_BY_PARENT[normalizeLayer(parentLayer)] || null;
}

export function defaultSourceTfForChildLayer(childLayer: string): string {
  return CHILD_SOURCE_TF[normalizeLayer(childLayer)] || 'D1';
}

export function defaultChartTfForChildLayer(childLayer: string): string {
  return CHILD_CHART_TF[normalizeLayer(childLayer)] || defaultSourceTfForChildLayer(childLayer);
}

export function parentResearchWindowFromRange(parentRange: Record<string, unknown>): ParentResearchWindow {
  const startRaw = parentRange.range_start_time
    || parentRange.active_from_time
    || parentRange.range_high_time
    || parentRange.range_low_time
    || '';
  const endRaw = parentRange.range_end_time
    || parentRange.range_low_time
    || parentRange.range_high_time
    || startRaw;
  const start = String(startRaw);
  const end = String(endRaw);
  const dateFrom = isoDay(start) || isoDay(end);
  const dateTo = isoDay(end) || dateFrom;
  return { start, end, dateFrom, dateTo };
}

export function buildChildMappingSession(parentRange: Record<string, unknown>): ChildMappingSession | null {
  const parentRangeId = String(parentRange.range_id || parentRange.id || '').trim();
  const parentLayer = normalizeLayer(parentRange.structure_layer || parentRange.layer);
  const childLayer = expectedChildLayerForParent(parentLayer);
  if (!parentRangeId || !childLayer) return null;
  return {
    parentRangeId,
    parentLayer,
    childLayer,
    childSourceTf: defaultSourceTfForChildLayer(childLayer),
    parentRange,
    researchWindow: parentResearchWindowFromRange(parentRange),
    detectionRunId: null,
    candidateIndex: 0,
    candidates: [],
    phase: 'scanning',
  };
}

export function mappingGapFromParent(parentRange: Record<string, unknown>): MappingGap | null {
  const parentRangeId = String(parentRange.range_id || parentRange.id || '').trim();
  const parentLayer = normalizeLayer(parentRange.structure_layer || parentRange.layer);
  const childLayer = expectedChildLayerForParent(parentLayer);
  if (!parentRangeId || !childLayer) return null;
  return {
    parentId: parentRangeId,
    parentRange,
    parentLayer,
    expectedChildLayer: childLayer,
    label: `${parentLayer} MAJOR #${parentRangeId} → map ${childLayer} MAJOR`,
  };
}

/** Navigation helper: OPEN_CHILD_MAPPING(parent_range_id) setup payload. */
export function openChildMappingSetup(parentRange: Record<string, unknown>): {
  session: ChildMappingSession;
  gap: MappingGap;
  chartTimeframe: string;
} | null {
  const session = buildChildMappingSession(parentRange);
  const gap = mappingGapFromParent(parentRange);
  if (!session || !gap) return null;
  return {
    session,
    gap,
    chartTimeframe: defaultChartTfForChildLayer(session.childLayer),
  };
}

export function samplesFromListRunResult(result: LocalResearchRunResult): RangeAuditSample[] {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return [];
  const samples = (result.parsed as { samples?: RangeAuditSample[] }).samples;
  return Array.isArray(samples) ? samples : [];
}

export async function runChildHistoricalScan(args: {
  symbol: string;
  childLayer: string;
  childSourceTf: string;
  dateFrom: string;
  dateTo: string;
  databasePath?: string;
}): Promise<LocalResearchRunResult> {
  return runHistoricalRangeScanLocal({
    symbol: args.symbol,
    timeframe: args.childSourceTf,
    layer: args.childLayer,
    dateFrom: args.dateFrom,
    dateTo: args.dateTo,
    databasePath: args.databasePath,
  });
}

export async function loadChildScanCandidates(args: {
  symbol: string;
  childLayer: string;
  childSourceTf: string;
  detectionRunId: string;
  databasePath?: string;
  limit?: number;
}): Promise<{ result: LocalResearchRunResult; samples: RangeAuditSample[] }> {
  const result = await listDetectorRunLocalResearch({
    symbol: args.symbol,
    structureLayer: args.childLayer,
    sourceTimeframe: args.childSourceTf,
    detectionRunId: args.detectionRunId,
    databasePath: args.databasePath,
    candidateKind: 'RANGE_CANDIDATE',
  });
  return { result, samples: samplesFromListRunResult(result) };
}

export function scanSummaryMessage(
  summary: ReturnType<typeof scanSummaryFromResult>,
  childLayer: string,
): string {
  if (!summary) return `Daily scan finished — review or create ${childLayer} ranges manually.`;
  if (summary.rangesFound <= 0) {
    return `No ${childLayer} candidates in parent window — use Manual Create to map structure anyway.`;
  }
  return `Found ${summary.rangesFound} ${childLayer} candidate${summary.rangesFound === 1 ? '' : 's'} in parent window.`;
}

export function advanceChildCandidateIndex(session: ChildMappingSession): ChildMappingSession {
  const nextIndex = session.candidateIndex + 1;
  if (nextIndex >= session.candidates.length) {
    return { ...session, candidateIndex: session.candidates.length, phase: 'done' };
  }
  return { ...session, candidateIndex: nextIndex, phase: 'reviewing' };
}

export function currentChildCandidate(session: ChildMappingSession): RangeAuditSample | null {
  return session.candidates[session.candidateIndex] || null;
}

export function candidateLabel(sample: RangeAuditSample | null): string {
  if (!sample) return '—';
  const rh = sample.rh ?? sample.range_high_price;
  const rl = sample.rl ?? sample.range_low_price;
  const week = sample.replay_until_time || sample.candle_time || '—';
  return `${week} · RH ${rh ?? '—'} / RL ${rl ?? '—'}`;
}

export function candidateSuggestionId(sample: RangeAuditSample | null): string | null {
  return suggestionIdFromSample(sample);
}

export async function restoreChildMappingSession(args: {
  parentRange: Record<string, unknown>;
  detectionRunId: string | null;
  candidateIndex: number;
  phase?: ChildMappingPhase | null;
  symbol: string;
  databasePath?: string;
}): Promise<ChildMappingSession | null> {
  const base = buildChildMappingSession(args.parentRange);
  if (!base) return null;

  if (!args.detectionRunId) {
    return {
      ...base,
      detectionRunId: null,
      candidates: [],
      candidateIndex: 0,
      phase: args.phase === 'scanning' ? 'scanning' : 'reviewing',
    };
  }

  const loaded = await loadChildScanCandidates({
    symbol: args.symbol,
    childLayer: base.childLayer,
    childSourceTf: base.childSourceTf,
    detectionRunId: args.detectionRunId,
    databasePath: args.databasePath,
  });
  const candidates = loaded.samples;
  const safeIndex = candidates.length
    ? Math.min(Math.max(0, args.candidateIndex), candidates.length - 1)
    : 0;
  const phase: ChildMappingPhase = candidates.length
    ? (args.phase === 'done' ? 'done' : 'reviewing')
    : (args.phase === 'scanning' ? 'scanning' : 'done');

  return {
    ...base,
    detectionRunId: args.detectionRunId,
    candidates,
    candidateIndex: safeIndex,
    phase,
  };
}
