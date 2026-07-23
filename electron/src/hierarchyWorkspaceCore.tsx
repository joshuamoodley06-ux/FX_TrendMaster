import React, { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  applyCandleAvailabilityToCoverageRow,
  buildHierarchyCoverageRows,
  coverageCandleTimeframe,
  compactDate,
  deriveCoverageYearOptions,
  filterCoverageRowsByYear,
  normalizeCoverageYearRange,
  rangeInterval,
  type HierarchyCoverageRow,
  type HierarchyLayer,
} from './hierarchyCoverage';
import { adaptMasterMapOutput, type MasterMapDocument, type MasterMapRangeNode } from './masterMapAdapter';
import { fetchLocalCandles, getElectronApiBridge } from './localResearchClient';
import './doctrineScriptPanel.css';

export type HierarchyWorkspaceMode = 'structure' | 'coverage' | 'python';
export type HierarchyRangeEnrichment = {
  chronology: string;
  bos: string;
  status: string;
};
export type WeeklyAnalysisApprovalState = 'PENDING' | 'APPROVED' | 'REJECTED';
export type CoverageCandleFetcher = (
  symbol: string,
  timeframe: string,
  range: { from?: string; to?: string; limit?: number },
) => Promise<{ ok: boolean; candles: { time: string }[]; error?: string }>;
export type WeeklyAnalysisActivationResult = {
  ok: boolean;
  source?: 'LIVE' | 'DISPOSABLE_ANALYSIS_COPY';
  liveDatabasePath?: string;
  analysisDatabasePath?: string;
  masterMap?: unknown;
  doctrineState?: unknown;
  scripts?: unknown[];
  workspaceVersion?: number;
  error?: string;
};
export type WeeklyAnalysisBridge = {
  getPaths: () => Promise<{ ok: boolean; databasePath?: string; error?: string }>;
  getWeeklyScript1State: (args: { databasePath: string; caseRef: string; symbol: string }) => Promise<WeeklyAnalysisActivationResult>;
  runWeeklyScript1: (args: { databasePath: string; caseRef: string; symbol: string }) => Promise<WeeklyAnalysisActivationResult>;
  reviewWeeklyScript1?: (args: {
    analysisDatabasePath: string;
    liveDatabasePath: string;
    runId: string;
    caseRef: string;
    symbol: string;
    canonicalRangeId: string;
    decision: 'APPROVED' | 'REJECTED';
  }) => Promise<WeeklyAnalysisActivationResult>;
  listDoctrineScripts?: (args: { analysisDatabasePath: string }) => Promise<{ ok: boolean; result?: unknown; error?: string }>;
  insertDoctrineScript?: (args: {
    analysisDatabasePath: string;
    displayName: string;
    scriptKey: string;
    versionLabel: string;
    adapterKey: string;
    executionOrder: number;
  }) => Promise<{ ok: boolean; result?: unknown; canceled?: boolean; error?: string }>;
  runDoctrinePipeline?: (args: {
    analysisDatabasePath: string;
    caseRef: string;
    symbol: string;
    versionId?: string;
  }) => Promise<{
    ok: boolean;
    result?: any;
    masterMap?: unknown;
    scripts?: unknown[];
    doctrineState?: unknown;
    error?: string;
  }>;
  reviewDoctrineSample?: (args: {
    analysisDatabasePath: string;
    runId: string;
    canonicalRangeId: string;
    decision: 'APPROVED' | 'REJECTED';
  }) => Promise<{ ok: boolean; result?: any; error?: string }>;
};

type Props = {
  ranges: Record<string, unknown>[];
  structure: ReactNode | ((enrichmentsByRangeId: ReadonlyMap<string, HierarchyRangeEnrichment>) => ReactNode);
  onNavigateRange: (range: Record<string, unknown>) => void;
  caseRef: string;
  symbol: string;
  weeklyAnalysisBridge?: WeeklyAnalysisBridge | null;
  coverageCandleFetcher?: CoverageCandleFetcher | null;
};

type OperationState = 'IDLE' | 'RESTORING' | 'RUNNING' | 'REVIEWING' | 'REFRESHING' | 'INSERTING';
type DoctrineSample = {
  canonicalRangeId: string;
  sampleOrder: number;
  decision: string;
  decidedAt: string | null;
  processingStatus: string;
  payload: Record<string, any>;
};
type PipelineView = {
  pipelineName: string;
  version: string;
  runId: string;
  approvalState: string;
  eligible: number;
  analysed: number;
  approvalCount: number;
  sampleCount: number;
  publicationStatus: string;
  validationSamples: DoctrineSample[];
};

const LAYERS: HierarchyLayer[] = ['WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];
const WEEKLY_CHAIN = [
  'weekly_structure',
  'weekly_reclaim',
  'weekly_reclaim_depth',
  'weekly_movement_classification',
  'weekly_profile_classification',
];

function defaultWeeklyAnalysisBridge(): WeeklyAnalysisBridge | null {
  const globals = globalThis as typeof globalThis & {
    localResearch?: Pick<WeeklyAnalysisBridge,
      'getWeeklyScript1State' | 'runWeeklyScript1' | 'reviewWeeklyScript1'
      | 'listDoctrineScripts' | 'insertDoctrineScript' | 'runDoctrinePipeline' | 'reviewDoctrineSample'>;
    localMappingBridge?: Pick<WeeklyAnalysisBridge, 'getPaths'>;
  };
  if (!globals.localMappingBridge?.getPaths
    || !globals.localResearch?.getWeeklyScript1State
    || !globals.localResearch?.runWeeklyScript1
    || !globals.localResearch?.listDoctrineScripts
    || !globals.localResearch?.insertDoctrineScript
    || !globals.localResearch?.runDoctrinePipeline) return null;
  return {
    getPaths: globals.localMappingBridge.getPaths,
    getWeeklyScript1State: globals.localResearch.getWeeklyScript1State,
    runWeeklyScript1: globals.localResearch.runWeeklyScript1,
    reviewWeeklyScript1: globals.localResearch.reviewWeeklyScript1,
    listDoctrineScripts: globals.localResearch.listDoctrineScripts,
    insertDoctrineScript: globals.localResearch.insertDoctrineScript,
    runDoctrinePipeline: globals.localResearch.runDoctrinePipeline,
    reviewDoctrineSample: globals.localResearch.reviewDoctrineSample,
  };
}

function chronologyLabel(value: unknown): string {
  const normalized = String(value || '').toUpperCase();
  if (normalized === 'RL_TO_RH') return 'RL → RH';
  if (normalized === 'RH_TO_RL') return 'RH → RL';
  if (normalized === 'SAME_W1') return 'Same W1';
  return 'Chronology Pending';
}

function bosLabel(value: unknown): string {
  const normalized = String(value || '').toUpperCase();
  if (normalized === 'BOS_UP') return 'BOS Up';
  if (normalized === 'BOS_DOWN') return 'BOS Down';
  return 'BOS Pending';
}

function reclaimSuffix(value: unknown): string {
  const normalized = String(value || '').toUpperCase();
  if (normalized === 'RECLAIMED') return 'RECL';
  if (normalized === 'ABANDONED') return 'ABND';
  if (normalized === 'ABANDONED_THEN_RECLAIMED') return 'ABND→RECL';
  return '';
}

function profileBadge(value: unknown): string {
  const normalized = String(value || '').toUpperCase();
  if (normalized === 'S&R' || normalized === 'S&R>FP' || normalized === 'S&D') {
    return `◆ ${normalized}`;
  }
  return '';
}

function script1Labels(node: MasterMapRangeNode): HierarchyRangeEnrichment {
  const generic = node.analysisEnrichments.weekly_structure?.payload || {};
  const reclaim = node.analysisEnrichments.weekly_reclaim?.payload || {};
  const profile = node.analysisEnrichments.weekly_profile_classification?.payload || {};
  const chronology = generic.chronology ?? node.script1Chronology;
  const bos = generic.bos_direction ?? node.script1BosDirection;
  const suffix = reclaimSuffix(reclaim.reclaim_status);
  const badge = profileBadge(profile.profile_badge ?? profile.profile_classification);
  const bosWithReclaim = [bosLabel(bos), suffix, badge].filter(Boolean).join(' · ');
  const status = node.analysisEnrichments.weekly_structure
    ? 'Approved'
    : node.script1ReviewStatus === 'APPROVED' ? 'Approved'
      : node.script1ReviewStatus === 'NEEDS_REVIEW' ? 'Needs Review'
        : node.script1ReviewStatus === 'REJECTED' ? 'Rejected' : 'Pending';
  return { chronology: chronologyLabel(chronology), bos: bosWithReclaim, status };
}

function matchingRange(node: MasterMapRangeNode | null, ranges: Record<string, unknown>[]) {
  if (!node) return null;
  const sourceIds = new Set<string>();
  for (const ref of node.sourceRefs) {
    if (ref.rawId !== null && ref.rawId !== undefined) sourceIds.add(String(ref.rawId));
    const sourceRecordId = String(ref.sourceRecordId || '').trim();
    if (sourceRecordId) sourceIds.add(sourceRecordId);
  }
  return ranges.find((item) => sourceIds.has(String(item.range_id || item.id || ''))) || null;
}

function matchingCanonicalRange(
  canonicalRangeId: unknown,
  nodes: MasterMapRangeNode[],
  ranges: Record<string, unknown>[],
) {
  const identity = String(canonicalRangeId || '').trim();
  if (!identity) return null;
  const node = nodes.find((item) => item.canonicalRangeId === identity) || null;
  return matchingRange(node, ranges);
}

export function selectWeeklyValidationSample(nodes: MasterMapRangeNode[], limit = 5): MasterMapRangeNode[] {
  const selected: MasterMapRangeNode[] = [];
  const seen = new Set<string>();
  for (const node of nodes) {
    const key = `${node.script1Chronology || 'NONE'}|${node.script1BosDirection || 'NONE'}|${node.script1ProcessingStatus || 'NONE'}`;
    if (!seen.has(key)) {
      selected.push(node);
      seen.add(key);
    }
    if (selected.length >= limit) return selected;
  }
  for (const node of nodes) {
    if (!selected.includes(node)) selected.push(node);
    if (selected.length >= limit) break;
  }
  return selected;
}

function compactTime(value: unknown): string {
  const text = String(value || '').trim();
  return text ? text.slice(0, 10) : 'Pending';
}

function compactNumber(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Pending';
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4).replace(/\.0000$/, '').replace(/(\.\d*?)0+$/, '$1') : 'Pending';
}

function present(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Pending';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function sampleFacts(scriptKey: string, sample: DoctrineSample, node: MasterMapRangeNode | null): string[] {
  const payload = sample.payload || {};
  const base = [
    `Range ID: ${sample.canonicalRangeId}`,
    `Processing: ${present(sample.processingStatus)}`,
  ];
  if (scriptKey === 'weekly_structure') {
    return [...base,
      `Chronology: ${chronologyLabel(payload.chronology ?? node?.script1Chronology)}`,
      `Range defined: ${compactTime(payload.range_defined_at)}`,
      `Expected BOS: ${bosLabel(payload.expected_bos_direction)}`,
      `Detected BOS: ${bosLabel(payload.bos_direction ?? node?.script1BosDirection)}`,
      `BOS candle: ${compactTime(payload.bos_time)}`,
      `BOS price: ${compactNumber(payload.bos_price)}`,
      `Weeks to BOS: ${present(payload.weeks_to_bos)}`,
      `Candles scanned: ${present(payload.candles_scanned)}`,
    ];
  }
  if (scriptKey === 'weekly_reclaim') {
    const status = String(payload.reclaim_status || sample.processingStatus || 'PENDING').replaceAll('_', ' ');
    return [...base,
      `Result: ${present(payload.reclaim_abbreviation)} · ${status}`,
      `Source BOS: ${bosLabel(payload.source_bos_direction)}`,
      `BOS candle: ${compactTime(payload.source_bos_time)}`,
      `BOS candle close: ${compactNumber(payload.bos_candle_close)}`,
      `Broken boundary: ${compactNumber(payload.reclaim_boundary)}`,
      `Same-candle reclaim: ${present(payload.same_candle_reclaim)}`,
      `Reclaim candle: ${compactTime(payload.reclaim_time)}`,
      `Reclaim wick: ${compactNumber(payload.reclaim_wick_price)}`,
      `Weeks to reclaim: ${present(payload.weeks_to_reclaim)}`,
      `Next BOS range: ${present(payload.next_bos_range_id)}`,
      `Next BOS direction: ${bosLabel(payload.next_bos_direction)}`,
      `Next BOS candle: ${compactTime(payload.next_bos_time)}`,
      `Weeks to abandonment: ${present(payload.weeks_to_abandonment)}`,
      `Weeks ABND→RECL: ${present(payload.weeks_from_abandonment_to_reclaim)}`,
      `Candles scanned: ${present(payload.candles_scanned)}`,
    ];
  }
  if (scriptKey === 'weekly_reclaim_depth') {
    return [...base,
      `Result: ${String(payload.depth_status || 'PENDING').replaceAll('_', ' ')}`,
      `Source BOS: ${bosLabel(payload.source_bos_direction)}`,
      `BOS candle: ${compactTime(payload.source_bos_time)}`,
      `Reclaim result: ${present(payload.source_reclaim_abbreviation)} · ${present(payload.source_reclaim_status)}`,
      `Reclaim candle: ${compactTime(payload.source_reclaim_time)}`,
      `Weeks to reclaim: ${present(payload.source_weeks_to_reclaim)}`,
      `Range 1 ID: ${present(payload.source_range1_id)}`,
      `W1 RH: ${compactNumber(payload.range1_high)}`,
      `W1 RL: ${compactNumber(payload.range1_low)}`,
      `W1 size: ${compactNumber(payload.range1_size)}`,
      `Fib 0: ${compactNumber(payload.fib_zero_price)}`,
      `Fib 1: ${compactNumber(payload.fib_one_price)}`,
      `Range 2 ID: ${present(payload.range2_id)}`,
      `Range 2 completed: ${compactTime(payload.range2_completed_at ?? payload.range2_defined_at)}`,
      `Range 2 chronology: ${chronologyLabel(payload.range2_chronology)}`,
      `Anchor sequence: ${present(payload.range2_anchor_sequence)}`,
      `W2 opposite anchor: ${present(payload.range2_opposite_anchor_type)} ${compactNumber(payload.range2_opposite_anchor_price)}`,
      `W2 opposite candle: ${compactTime(payload.range2_opposite_anchor_time)}`,
      `W2 continuation anchor: ${present(payload.range2_continuation_anchor_type)} ${compactNumber(payload.range2_continuation_anchor_price)}`,
      `W2 continuation candle: ${compactTime(payload.range2_continuation_anchor_time)}`,
      `Trading depth price: ${compactNumber(payload.reclaim_depth_price)}`,
      `Trading Fib ratio: ${compactNumber(payload.reclaim_depth_ratio)}`,
      `Trading depth: ${compactNumber(payload.reclaim_depth_percent)}%`,
      `Raw depth price: ${compactNumber(payload.raw_reclaim_depth_price)}`,
      `Raw Fib ratio: ${compactNumber(payload.raw_reclaim_depth_ratio)}`,
      `Raw Fib depth: ${compactNumber(payload.raw_reclaim_depth_percent)}%`,
      `Distance beyond broken boundary: ${compactNumber(payload.boundary_distance_price)}`,
      `Boundary position: ${present(payload.boundary_position)}`,
      `Weeks BOS→depth anchor: ${present(payload.weeks_bos_to_depth_anchor)}`,
      `Weeks reclaim→depth anchor: ${present(payload.weeks_reclaim_to_depth_anchor)}`,
      `Weeks BOS→R2 complete: ${present(payload.weeks_bos_to_range2_completion ?? payload.weeks_bos_to_range2_definition)}`,
      `Weeks reclaim→R2 complete: ${present(payload.weeks_reclaim_to_range2_completion ?? payload.weeks_reclaim_to_range2_definition)}`,
      `Range 2 formation weeks: ${present(payload.range2_formation_weeks)}`,
      `Old opposite touched: ${present(payload.old_opposite_external_touched)}`,
      `Old opposite exceeded: ${present(payload.old_opposite_external_exceeded)}`,
    ];
  }
  if (scriptKey === 'weekly_profile_classification') {
    return [...base,
      `Profile: ${present(payload.profile_classification)}`,
      `Depth: ${compactNumber(payload.reclaim_depth_percent)}%`,
      `Reclaim: ${String(payload.reclaim_status || 'PENDING').replaceAll('_', ' ')}`,
      `Previous BOS: ${bosLabel(payload.source_bos_direction)}`,
      `Next BOS: ${bosLabel(payload.next_bos_direction)}`,
      `Classification basis: ${String(payload.classification_basis || 'PENDING').replaceAll('_', ' ')}`,
    ];
  }
  const entries = Object.entries(payload)
    .filter(([key, value]) => key !== 'reason_codes' && ['string', 'number', 'boolean'].includes(typeof value));
  return [...base, ...entries.map(([key, value]) => `${key.replaceAll('_', ' ')}: ${String(value)}`)];
}

function DoctrineValidationSample({
  scriptKey, samples, nodes, ranges, saving, reviewEnabled, onNavigateRange, onDecision,
}: {
  scriptKey: string;
  samples: DoctrineSample[];
  nodes: MasterMapRangeNode[];
  ranges: Record<string, unknown>[];
  saving: boolean;
  reviewEnabled: boolean;
  onNavigateRange: (range: Record<string, unknown>) => void;
  onDecision: (canonicalRangeId: string, decision: 'APPROVED' | 'REJECTED') => void;
}) {
  return <div className="weeklyScript1Rows doctrineValidationRows" aria-label="Doctrine validation sample">
    {samples.map((sample) => {
      const node = nodes.find((item) => item.canonicalRangeId === sample.canonicalRangeId) || null;
      const range1 = matchingRange(node, ranges);
      const range2 = scriptKey === 'weekly_reclaim_depth'
        ? matchingCanonicalRange(sample.payload?.range2_id, nodes, ranges)
        : null;
      const defaultRange = scriptKey === 'weekly_reclaim_depth' ? (range2 || range1) : range1;
      const facts = sampleFacts(scriptKey, sample, node);
      const reasons = Array.isArray(sample.payload?.reason_codes) ? sample.payload.reason_codes : [];
      return <div key={sample.canonicalRangeId} className="weeklyScript1Sample doctrineValidationSample"
        data-decision={sample.decision}>
        <button type="button" className="weeklyScript1Row doctrineValidationRow" disabled={!defaultRange}
          onClick={() => defaultRange && onNavigateRange(defaultRange)}>
          <b>WEEKLY</b>
          {facts.map((fact, index) => <span key={`${fact}-${index}`}>{fact}</span>)}
          <strong>{sample.decision}</strong>
        </button>
        {scriptKey === 'weekly_reclaim_depth' && <div className="weeklySampleActions doctrineRangeActions"
          aria-label="Depth range navigation">
          <button type="button" disabled={!range1} onClick={() => range1 && onNavigateRange(range1)}>
            View Range 1
          </button>
          <button type="button" disabled={!range2} onClick={() => range2 && onNavigateRange(range2)}>
            View Range 2
          </button>
          <span>{range2 ? 'Card focus: Range 2' : 'Range 2 mapping link unavailable'}</span>
        </div>}
        {!!reasons.length && <span className="doctrineSampleReason">Reasons: {reasons.join(' · ').replaceAll('_', ' ')}</span>}
        {reviewEnabled && sample.decision === 'PENDING' && <div className="weeklySampleActions">
          <button type="button" disabled={saving}
            onClick={() => onDecision(sample.canonicalRangeId, 'APPROVED')}>Approve</button>
          <button type="button" disabled={saving}
            onClick={() => onDecision(sample.canonicalRangeId, 'REJECTED')}>Reject</button>
        </div>}
      </div>;
    })}
  </div>;
}

function CoverageRow({ row, onNavigate }: {
  row: HierarchyCoverageRow;
  onNavigate: (range: Record<string, unknown>) => void;
}) {
  const [open, setOpen] = useState(false);
  const parentWindow = rangeInterval(row.parent);
  return <div className="hierarchyCoverageRow" data-parent-range-id={row.parentId}>
    <div className="hierarchyCoverageLine">
      <button type="button" className="hierarchyCoverageExpand"
        onClick={() => setOpen((value) => !value)} aria-expanded={open}>{open ? '▼' : '▶'}</button>
      <button type="button" className="hierarchyCoverageJump" onClick={() => onNavigate(row.parent)}>
        <span className="hierarchyCoveragePrimary">
          <b>{row.parentLayer}</b><span aria-hidden="true">|</span>
          <span>{parentWindow ? `${compactDate(parentWindow.startMs)} → ${compactDate(parentWindow.endMs)}` : 'Date unavailable'}</span>
          <span aria-hidden="true">|</span>
        </span>
        <strong>{row.coveragePercent === null ? '—' : `${row.coveragePercent}%`}</strong>
      </button>
    </div>
    {open && <div className="hierarchyCoverageGaps">
      {row.childLayer === null && <span>Micro has no configured child layer.</span>}
      {row.childLayer !== null && row.marketDataStatus === 'NO_DATA' && !row.gaps.length
        && <span>No local OHLC in this parent window; excluded from the gap queue.</span>}
      {row.childLayer !== null && row.marketDataStatus !== 'NO_DATA' && !row.gaps.length
        && <span>Full {row.childLayer.toLowerCase()} coverage.</span>}
      {row.gaps.map((gap) => <button key={`${gap.startMs}-${gap.endMs}`} type="button"
        onClick={() => onNavigate({ ...row.parent, range_start_time: gap.startIso, range_end_time: gap.endIso })}>
        {compactDate(gap.startMs)} <span aria-hidden="true">&lt;-----&gt;</span> {compactDate(gap.endMs)}
      </button>)}
    </div>}
  </div>;
}

function legacyPipelineView(document: MasterMapDocument | null): PipelineView | null {
  const legacy = document?.weeklyAnalysis;
  if (!legacy) return null;
  return {
    pipelineName: legacy.pipelineName,
    version: legacy.version,
    runId: legacy.runId,
    approvalState: legacy.approvalState,
    eligible: legacy.eligible,
    analysed: legacy.analysed,
    approvalCount: legacy.approvalCount,
    sampleCount: legacy.sampleCount,
    publicationStatus: legacy.publicationStatus,
    validationSamples: legacy.validationSamples.map((sample) => ({
      canonicalRangeId: sample.canonicalRangeId,
      sampleOrder: sample.sampleOrder,
      decision: sample.decision,
      decidedAt: sample.decidedAt,
      processingStatus: '',
      payload: {},
    })),
  };
}

function pipelineFromState(
  state: any,
  scriptName: string,
  caseRef: string,
  symbol: string,
  selectedVersionId: string | null,
  fallback: PipelineView | null,
): PipelineView | null {
  if (!state) return fallback;
  const runs = Array.isArray(state.runs) ? state.runs : [];
  const allMatching = runs.filter((entry: any) => entry?.run?.case_ref === caseRef
    && String(entry?.run?.symbol || '').toUpperCase() === String(symbol || '').toUpperCase());
  const matching = selectedVersionId
    ? allMatching.filter((entry: any) => String(entry?.run?.version_id || '') === selectedVersionId)
    : allMatching;
  const direct = state?.run?.case_ref === caseRef
    && String(state?.run?.symbol || '').toUpperCase() === String(symbol || '').toUpperCase()
    && (!selectedVersionId || String(state?.run?.version_id || '') === selectedVersionId)
    ? state : null;
  const candidate = matching.find((entry: any) => entry?.run?.approval_status === 'PENDING') || null;
  const active = matching.find((entry: any) => entry?.run?.approval_status === 'APPROVED'
    && entry?.run?.publication_status === 'PUBLISHED'
    && (!state.current_approved_version_id || entry?.run?.version_id === state.current_approved_version_id)) || null;
  const chosen = direct || candidate || active || matching[0] || null;
  const versions = Array.isArray(state.versions) ? state.versions : [];
  if (!chosen?.run) {
    const selectedIsCurrent = !!state.current_approved_version_id
      && (!selectedVersionId || String(state.current_approved_version_id) === selectedVersionId);
    if (state.status === 'APPROVED' && selectedIsCurrent) {
      const approved = versions.find((version: any) => version.version_id === state.current_approved_version_id);
      return {
        pipelineName: scriptName,
        version: approved?.version_label || '1',
        runId: '',
        approvalState: 'APPROVED',
        eligible: 0,
        analysed: 0,
        approvalCount: 0,
        sampleCount: 0,
        publicationStatus: 'READY_FOR_CASE',
        validationSamples: [],
      };
    }
    return fallback;
  }
  const run = chosen.run;
  const samples = Array.isArray(chosen.samples) ? chosen.samples : [];
  return {
    pipelineName: scriptName,
    version: versions.find((version: any) => version.version_id === run.version_id)?.version_label || '1',
    runId: run.run_id,
    approvalState: run.approval_status,
    eligible: run.eligible_count,
    analysed: run.analysed_count,
    approvalCount: run.approval_count,
    sampleCount: run.sample_count,
    publicationStatus: run.publication_status,
    validationSamples: samples.map((sample: any) => ({
      canonicalRangeId: sample.canonical_range_id,
      sampleOrder: sample.sample_order,
      decision: sample.decision,
      decidedAt: sample.decided_at || null,
      processingStatus: sample.processing_status || '',
      payload: sample.payload && typeof sample.payload === 'object' ? sample.payload : {},
    })),
  };
}

export function HierarchyWorkspace({
  ranges, structure, onNavigateRange, caseRef, symbol, weeklyAnalysisBridge, coverageCandleFetcher,
}: Props) {
  const [mode, setMode] = useState<HierarchyWorkspaceMode>('structure');
  const [layer, setLayer] = useState<HierarchyLayer>('WEEKLY');
  const rows = useMemo(() => buildHierarchyCoverageRows(ranges, layer), [ranges, layer]);
  const yearOptions = useMemo(() => deriveCoverageYearOptions(rows), [rows]);
  const yearOptionsKey = yearOptions.join(',');
  const [fromYear, setFromYear] = useState<number | null>(null);
  const [toYear, setToYear] = useState<number | null>(null);
  const [analysisState, setAnalysisState] = useState<'dormant' | 'active' | 'error'>('dormant');
  const [operationState, setOperationState] = useState<OperationState>('IDLE');
  const [analysisDocument, setAnalysisDocument] = useState<MasterMapDocument | null>(null);
  const [analysisDatabasePath, setAnalysisDatabasePath] = useState('');
  const [liveDatabasePath, setLiveDatabasePath] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [doctrineState, setDoctrineState] = useState<any>(null);
  const [storedScripts, setStoredScripts] = useState<any[]>([]);
  const [selectedScriptKey, setSelectedScriptKey] = useState('weekly_structure');
  const [insertOpen, setInsertOpen] = useState(false);
  const [insertName, setInsertName] = useState('Weekly Script');
  const [insertKey, setInsertKey] = useState('weekly_structure');
  const [insertVersion, setInsertVersion] = useState('2');
  const [insertAdapter, setInsertAdapter] = useState('weekly_chronology_bos_v2');
  const [pipelineSummary, setPipelineSummary] = useState<any>(null);
  const previousLayer = useRef<HierarchyLayer>(layer);
  const bridge = useMemo(
    () => weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge,
    [weeklyAnalysisBridge],
  );

  const sortedScripts = useMemo(() => [...storedScripts].sort((a, b) =>
    Number(a.execution_order || 0) - Number(b.execution_order || 0)
    || String(a.script_key || '').localeCompare(String(b.script_key || ''))), [storedScripts]);
  const selectedScript = sortedScripts.find((script) => script.script_key === selectedScriptKey) || null;
  const selectedState = selectedScript?.doctrine_state
    || (selectedScriptKey === 'weekly_structure' ? doctrineState : null);

  useEffect(() => {
    if (!sortedScripts.length) return;
    if (!sortedScripts.some((script) => script.script_key === selectedScriptKey)) {
      setSelectedScriptKey(String(sortedScripts[0].script_key));
    }
  }, [selectedScriptKey, sortedScripts]);

  const applyScripts = (value: unknown) => {
    if (Array.isArray(value)) setStoredScripts(value);
  };

  const loadScripts = async (databasePath: string) => {
    if (!bridge?.listDoctrineScripts || !databasePath) return [];
    const listed = await bridge.listDoctrineScripts({ analysisDatabasePath: databasePath });
    const scripts = listed.ok && Array.isArray(listed.result) ? listed.result : [];
    setStoredScripts(scripts);
    return scripts;
  };

  const applyPipelineResult = async (result: any, databasePath = analysisDatabasePath) => {
    if (result?.masterMap) setAnalysisDocument(adaptMasterMapOutput(result.masterMap));
    if (result?.doctrineState) setDoctrineState(result.doctrineState);
    if (Array.isArray(result?.scripts)) applyScripts(result.scripts);
    else if (databasePath) await loadScripts(databasePath);
    if (result?.result) setPipelineSummary(result.result);
    setAnalysisState('active');
  };

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      if (!bridge || !caseRef || !symbol) return;
      setOperationState('RESTORING');
      try {
        const paths = await bridge.getPaths();
        const databasePath = String(paths.databasePath || '').trim();
        if (!paths.ok || !databasePath) return;
        const result = await bridge.getWeeklyScript1State({ databasePath, caseRef, symbol });
        if (!cancelled && result.ok && result.masterMap && result.analysisDatabasePath) {
          setAnalysisDocument(adaptMasterMapOutput(result.masterMap));
          setAnalysisDatabasePath(result.analysisDatabasePath);
          setLiveDatabasePath(databasePath);
          setDoctrineState(result.doctrineState || null);
          if (Array.isArray(result.scripts)) setStoredScripts(result.scripts);
          else await loadScripts(result.analysisDatabasePath);
          setAnalysisState('active');
        }
      } catch {
        if (!cancelled) {
          setAnalysisState('error');
          setAnalysisError('The XAUUSD analysis workspace could not be restored safely.');
        }
      } finally {
        if (!cancelled) setOperationState('IDLE');
      }
    };
    void restore();
    return () => { cancelled = true; };
  }, [bridge, caseRef, symbol]);

  useEffect(() => {
    const first = yearOptions[0] ?? null;
    const last = yearOptions[yearOptions.length - 1] ?? null;
    const layerChanged = previousLayer.current !== layer;
    previousLayer.current = layer;
    setFromYear((current) => layerChanged || current === null
      ? first
      : Math.max(first ?? current, Math.min(current, last ?? current)));
    setToYear((current) => layerChanged || current === null
      ? last
      : Math.max(first ?? current, Math.min(current, last ?? current)));
  }, [layer, yearOptionsKey]);

  const filteredRows = useMemo(() => {
    if (fromYear === null || toYear === null) return rows;
    return filterCoverageRowsByYear(rows, fromYear, toYear);
  }, [rows, fromYear, toYear]);
  const effectiveCoverageCandleFetcher = coverageCandleFetcher === undefined
    ? (getElectronApiBridge()?.candles?.fetch ? fetchLocalCandles : null)
    : coverageCandleFetcher;
  const coverageScopeKey = useMemo(() => [symbol, layer, ...filteredRows.map((row) => (
    `${row.parentId}:${row.gaps.map((gap) => `${gap.startMs}-${gap.endMs}`).join(',')}`
  ))].join('|'), [filteredRows, layer, symbol]);
  const [coverageResult, setCoverageResult] = useState<{ key: string; rows: HierarchyCoverageRow[] } | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [coverageWarning, setCoverageWarning] = useState('');
  const displayedCoverageRows = effectiveCoverageCandleFetcher
    ? coverageResult?.key === coverageScopeKey ? coverageResult.rows : []
    : filteredRows;

  useEffect(() => {
    if (mode !== 'coverage' || !effectiveCoverageCandleFetcher) return;
    let cancelled = false;
    const qualify = async () => {
      setCoverageLoading(true);
      setCoverageWarning('');
      const timeframe = coverageCandleTimeframe(layer);
      if (!timeframe || !filteredRows.length) {
        if (!cancelled) {
          setCoverageResult({ key: coverageScopeKey, rows: filteredRows });
          setCoverageLoading(false);
        }
        return;
      }
      const nextRows: HierarchyCoverageRow[] = [];
      let fetchFailed = false;
      for (const row of filteredRows) {
        if (!row.gaps.length) {
          nextRows.push(row);
          continue;
        }
        const parentWindow = rangeInterval(row.parent);
        if (!parentWindow) {
          nextRows.push(row);
          continue;
        }
        try {
          const result = await effectiveCoverageCandleFetcher(symbol, timeframe, {
            from: new Date(parentWindow.startMs).toISOString(),
            to: new Date(parentWindow.endMs).toISOString(),
            limit: 10_000,
          });
          if (cancelled) return;
          if (!result.ok) {
            fetchFailed = true;
            nextRows.push(row);
          } else {
            nextRows.push(applyCandleAvailabilityToCoverageRow(row, result.candles || [], timeframe));
          }
        } catch {
          fetchFailed = true;
          nextRows.push(row);
        }
      }
      if (!cancelled) {
        setCoverageResult({ key: coverageScopeKey, rows: nextRows });
        setCoverageWarning(fetchFailed
          ? 'Local OHLC could not be checked for every range. Unverified gaps remain visible.'
          : '');
        setCoverageLoading(false);
      }
    };
    void qualify();
    return () => { cancelled = true; };
  }, [coverageScopeKey, effectiveCoverageCandleFetcher, filteredRows, layer, mode, symbol]);

  const updateYears = (nextFrom: number, nextTo: number) => {
    const normalized = normalizeCoverageYearRange(nextFrom, nextTo);
    setFromYear(normalized.fromYear);
    setToYear(normalized.toYear);
  };

  const activateWeeklyAnalysis = async () => {
    if (!bridge) {
      setAnalysisState('error');
      setAnalysisError('Weekly analysis bridge is unavailable. Open this workspace in Electron.');
      return;
    }
    setOperationState('RUNNING');
    setAnalysisError('');
    try {
      if (!caseRef) throw new Error('Select a case before running Weekly analysis.');
      if (!symbol) throw new Error('Weekly analysis requires the selected instrument.');
      const paths = await bridge.getPaths();
      const databasePath = String(paths.databasePath || '').trim();
      if (!paths.ok || !databasePath) throw new Error(paths.error || 'Explicit Range Library database path is unavailable.');
      const result = await bridge.runWeeklyScript1({ databasePath, caseRef, symbol });
      if (!result.ok || result.source !== 'DISPOSABLE_ANALYSIS_COPY'
        || !result.masterMap || !result.analysisDatabasePath) {
        throw new Error(result.error || 'Weekly analysis did not return the XAUUSD analysis workspace.');
      }
      setAnalysisDatabasePath(result.analysisDatabasePath);
      setLiveDatabasePath(databasePath);
      setSelectedScriptKey('weekly_structure');
      await applyPipelineResult(result, result.analysisDatabasePath);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const safeMessage = /candle/i.test(detail)
        ? 'Weekly analysis could not start because the candle source database was not resolved.'
        : /case/i.test(detail) ? detail : 'Weekly analysis could not start. Check the Electron logs for details.';
      setAnalysisState('error');
      setAnalysisError(safeMessage);
    } finally {
      setOperationState('IDLE');
    }
  };

  const caseAnalysisNodes = useMemo(() => analysisDocument?.trustedRoot.children.filter(
    (node) => node.layer === 'WEEKLY' && node.sourceRefs.some((ref) => ref.caseRef === caseRef),
  ) || [], [analysisDocument, caseRef]);

  const selectedVersionId = String(selectedScript?.version_id || '') || null;
  const legacy = selectedScript?.adapter_key === 'doctrine_package_v1'
    ? null
    : selectedScriptKey === 'weekly_structure' ? legacyPipelineView(analysisDocument) : null;
  const pipeline = pipelineFromState(
    selectedState,
    String(selectedScript?.display_name || 'Weekly analysis'),
    caseRef,
    symbol,
    selectedVersionId,
    legacy,
  );

  const approvedByRangeId = useMemo(() => {
    const result = new Map<string, HierarchyRangeEnrichment>();
    for (const node of caseAnalysisNodes) {
      if (!node.analysisEnrichments.weekly_structure) continue;
      const labels = script1Labels(node);
      for (const sourceRef of node.sourceRefs) {
        if (sourceRef.caseRef && sourceRef.caseRef !== caseRef) continue;
        const ids = new Set<string>();
        if (sourceRef.rawId !== null && sourceRef.rawId !== undefined) ids.add(String(sourceRef.rawId));
        const sourceRecordId = String(sourceRef.sourceRecordId || '').trim();
        if (sourceRecordId) ids.add(sourceRecordId);
        for (const id of ids) result.set(id, labels);
      }
    }
    return result;
  }, [caseAnalysisNodes, caseRef]);

  const saveReview = async (canonicalRangeId: string, decision: 'APPROVED' | 'REJECTED') => {
    if (!bridge || !pipeline?.runId || !analysisDatabasePath) return;
    setOperationState('REVIEWING');
    setReviewError('');
    try {
      if (bridge.reviewDoctrineSample && bridge.runDoctrinePipeline) {
        const reviewed = await bridge.reviewDoctrineSample({
          analysisDatabasePath,
          runId: pipeline.runId,
          canonicalRangeId,
          decision,
        });
        if (!reviewed.ok) throw new Error(reviewed.error || 'Review update failed.');
        const refreshed = await bridge.runDoctrinePipeline({ analysisDatabasePath, caseRef, symbol });
        if (!refreshed.ok) throw new Error(refreshed.error || 'Review refresh failed.');
        await applyPipelineResult(refreshed);
      } else if (selectedScriptKey === 'weekly_structure' && bridge.reviewWeeklyScript1) {
        const result = await bridge.reviewWeeklyScript1({
          analysisDatabasePath,
          liveDatabasePath,
          runId: pipeline.runId,
          caseRef,
          symbol,
          canonicalRangeId,
          decision,
        });
        if (!result.ok || !result.masterMap) throw new Error(result.error || 'Review update failed.');
        await applyPipelineResult(result);
      } else {
        throw new Error('Generic doctrine review bridge is unavailable.');
      }
    } catch {
      setReviewError('The review could not be saved safely. The existing hierarchy is unchanged.');
    } finally {
      setOperationState('IDLE');
    }
  };

  const loadStoredScripts = async () => {
    if (!analysisDatabasePath) return;
    setOperationState('REFRESHING');
    try { await loadScripts(analysisDatabasePath); }
    finally { setOperationState('IDLE'); }
  };

  const insertStoredScript = async () => {
    if (!bridge?.insertDoctrineScript || !analysisDatabasePath) return;
    setOperationState('INSERTING');
    setAnalysisError('');
    try {
      const result = await bridge.insertDoctrineScript({
        analysisDatabasePath,
        displayName: insertName,
        scriptKey: insertKey,
        versionLabel: insertVersion,
        adapterKey: insertAdapter,
        executionOrder: 100,
      });
      if (!result.ok) {
        if (!result.canceled) throw new Error(result.error || 'Doctrine package insertion failed.');
        return;
      }
      setInsertOpen(false);
      const versionId = String((result.result as any)?.version_id || '').trim();
      const scriptKey = String((result.result as any)?.script_key || insertKey).trim();
      if (versionId && bridge.runDoctrinePipeline && caseRef && symbol) {
        setSelectedScriptKey(scriptKey);
        const run = await bridge.runDoctrinePipeline({ analysisDatabasePath, caseRef, symbol, versionId });
        if (!run.ok) throw new Error(run.error || 'Inserted doctrine version could not run.');
        await applyPipelineResult(run);
      } else {
        await loadScripts(analysisDatabasePath);
      }
    } catch {
      setAnalysisError('The doctrine package could not be inserted and run safely.');
      setAnalysisState('error');
    } finally {
      setOperationState('IDLE');
    }
  };

  const runSelectedCandidate = async () => {
    if (!bridge?.runDoctrinePipeline || !analysisDatabasePath || !selectedScript?.version_id) return;
    setOperationState('RUNNING');
    setAnalysisError('');
    try {
      const result = await bridge.runDoctrinePipeline({
        analysisDatabasePath,
        caseRef,
        symbol,
        versionId: String(selectedScript.version_id),
      });
      if (!result.ok) throw new Error(result.error || 'Selected doctrine script failed.');
      await applyPipelineResult(result);
    } catch {
      setAnalysisError('The selected doctrine script could not run safely.');
      setAnalysisState('error');
    } finally {
      setOperationState('IDLE');
    }
  };

  const rerunActivePipeline = async () => {
    if (!bridge?.runDoctrinePipeline || !analysisDatabasePath) return;
    setOperationState('RUNNING');
    try {
      const result = await bridge.runDoctrinePipeline({ analysisDatabasePath, caseRef, symbol });
      if (!result.ok) throw new Error(result.error || 'Active pipeline failed.');
      await applyPipelineResult(result);
    } catch {
      setAnalysisError('The approved pipeline could not refresh the selected case safely.');
      setAnalysisState('error');
    } finally {
      setOperationState('IDLE');
    }
  };

  const busy = operationState !== 'IDLE';
  const approvalState = String(pipeline?.approvalState || selectedScript?.latest_version_status || 'PENDING').toUpperCase();
  const hasCaseRun = !!pipeline?.runId;
  const hasApprovedScripts = sortedScripts.some((script) => !!script.doctrine_state?.current_approved_version_id);
  const installedKeys = new Set(sortedScripts.map((script) => String(script.script_key)));
  const fullWeeklyChainInstalled = WEEKLY_CHAIN.every((key) => installedKeys.has(key));
  const selectedIndex = sortedScripts.findIndex((script) => script.script_key === selectedScriptKey);
  const dependenciesReady = selectedIndex <= 0 || sortedScripts.slice(0, selectedIndex)
    .every((script) => script.package_dependency_ready ?? !!script.current_approved_version_id);
  const selectedPending = String(selectedScript?.latest_version_status || '').toUpperCase() === 'PENDING_APPROVAL';

  return <section className="hierarchyWorkspace" data-mode={mode} aria-label="Hierarchy workspace">
    <div className="hierarchyWorkspaceModes" role="tablist" aria-label="Hierarchy modes">
      {(['structure', 'coverage', 'python'] as HierarchyWorkspaceMode[]).map((item) =>
        <button key={item} type="button" role="tab" aria-selected={mode === item}
          className={mode === item ? 'active' : ''} onClick={() => setMode(item)}>
          {item[0].toUpperCase() + item.slice(1)}
        </button>)}
    </div>

    {mode === 'structure' && <div className="hierarchyWorkspaceBody structureMode">
      {typeof structure === 'function' ? structure(approvedByRangeId) : structure}
    </div>}

    {mode === 'coverage' && <div className="hierarchyWorkspaceBody coverageMode">
      <div className="hierarchyCoverageFilters" role="group" aria-label="Coverage layer">
        {LAYERS.map((item) => <button key={item} type="button" className={layer === item ? 'active' : ''}
          aria-pressed={layer === item} onClick={() => setLayer(item)}>
          {item[0] + item.slice(1).toLowerCase()}
        </button>)}
      </div>
      {!!yearOptions.length && fromYear !== null && toYear !== null
        && <div className="hierarchyCoverageYears" aria-label="Coverage year range">
          <label>From year<select aria-label="From year" value={fromYear}
            onChange={(event) => updateYears(Number(event.target.value), toYear)}>
            {yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}
          </select></label>
          <span aria-hidden="true">→</span>
          <label>To year<select aria-label="To year" value={toYear}
            onChange={(event) => updateYears(fromYear, Number(event.target.value))}>
            {yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}
          </select></label>
        </div>}
      {coverageLoading && <span role="status">Checking local OHLC before listing mapping gaps…</span>}
      {coverageWarning && <span role="alert">{coverageWarning}</span>}
      <div className="hierarchyCoverageScroll">
        {!coverageLoading && !displayedCoverageRows.length
          && <span className="caseLedgerEmpty">No {layer.toLowerCase()} ranges in this year range.</span>}
        {displayedCoverageRows.map((row) => <CoverageRow key={row.parentId} row={row} onNavigate={onNavigateRange} />)}
      </div>
    </div>}

    {mode === 'python' && <div className="hierarchyWorkspaceBody pythonMode doctrinePanel">
      <div className="doctrineScriptControls">
        <button type="button" disabled={!analysisDatabasePath || busy}
          onClick={() => setInsertOpen((value) => !value)}>Insert Script</button>
        <button type="button" disabled={!analysisDatabasePath || busy}
          onClick={() => void loadStoredScripts()}>Stored Scripts</button>
        <button type="button" disabled={!analysisDatabasePath || !hasApprovedScripts || busy}
          onClick={() => void rerunActivePipeline()}>
          {operationState === 'RUNNING' ? 'Running Pipeline…' : 'Run Active Pipeline'}
        </button>
      </div>

      {pipelineSummary && <span role="status">
        {pipelineSummary.active_scripts ?? 0} active · {pipelineSummary.skipped_unchanged ?? 0} unchanged skipped · {pipelineSummary.processed ?? 0} processed
      </span>}

      {insertOpen && <div className="doctrineInsertForm" aria-label="Insert doctrine script">
        <label>Name<input value={insertName} onChange={(event) => setInsertName(event.target.value)} /></label>
        <label>Script key<input value={insertKey} onChange={(event) => setInsertKey(event.target.value)} /></label>
        <label>Version<input value={insertVersion} onChange={(event) => setInsertVersion(event.target.value)} /></label>
        <label>Adapter<select value={insertAdapter} onChange={(event) => setInsertAdapter(event.target.value)}>
          <option value="weekly_chronology_bos_v2">Sequential Weekly BOS v2</option>
          <option value="weekly_chronology_bos_v1">Weekly BOS v1</option>
        </select></label>
        <button type="button" disabled={!insertName.trim() || !insertKey.trim() || !insertVersion.trim() || busy}
          onClick={() => void insertStoredScript()}>Choose package…</button>
      </div>}

      <div className="weeklyScript1Header doctrineWorkspaceHeader">
        <div>
          <b>Weekly Python Memory</b>
          <span className={`weeklyScript1State ${analysisState}`}>
            {analysisState === 'active' ? 'Active · Current' : analysisState}
          </span>
        </div>
        {!fullWeeklyChainInstalled
          ? <button type="button" onClick={() => void activateWeeklyAnalysis()} disabled={busy}>
            {operationState === 'RUNNING' ? 'Installing…' : 'Install 5-Script Chain'}
          </button>
          : <span className="weeklyScript1ApprovalBadge approved">5-script chain installed</span>}
      </div>

      <span className={`weeklyScript1Source ${analysisState === 'active' ? 'disposable' : 'live'}`}>
        {analysisState === 'active' ? 'XAUUSD ANALYSIS WORKSPACE V2' : 'LIVE'}
      </span>
      {operationState === 'RESTORING' && <span role="status">Restoring XAUUSD script memory…</span>}
      {operationState === 'RUNNING' && <span role="status">Running selected structure logic…</span>}
      {operationState === 'REVIEWING' && <span role="status">Saving validation decision…</span>}
      {analysisState === 'dormant' && operationState === 'IDLE'
        && <span role="status">Install the Weekly script chain to begin analysis.</span>}
      {analysisState === 'error' && <div role="alert" className="weeklyScript1Error">
        <b>Weekly analysis failed safely</b><span>{analysisError}</span><span>Existing hierarchy remains available.</span>
      </div>}

      {!!sortedScripts.length && <div className="doctrineStoredScripts" aria-label="Stored doctrine scripts">
        {sortedScripts.map((script) => {
          const selected = script.script_key === selectedScriptKey;
          const latest = String(script.latest_version_status || script.status || 'PENDING').replaceAll('_', ' ');
          const priorActive = !!script.doctrine_state?.current_approved_version_id;
          const memoryLabel = script.package_dependency_ready
            ? 'ACTIVE MEMORY'
            : priorActive ? 'CANDIDATE · PRIOR ACTIVE' : 'NOT ACTIVE';
          return <button key={script.script_id} type="button" data-script-key={script.script_key}
            className={selected ? 'selected' : ''} onClick={() => setSelectedScriptKey(String(script.script_key))}>
            <b>{script.display_name}</b>
            <span>Order {script.execution_order} · v{script.version_label} · {latest}</span>
            <strong>{memoryLabel}</strong>
          </button>;
        })}
      </div>}

      {analysisState === 'active' && analysisDocument && selectedScript && <>
        <span className="weeklyScript1Db" title={analysisDatabasePath}>{analysisDatabasePath}</span>
        <div className="weeklyPipelineSummary doctrineSelectedSummary" aria-label="Selected doctrine script summary">
          <b>{selectedScript.display_name}</b>
          <span>Version {pipeline?.version || selectedScript.version_label || 'unknown'} · {approvalState}</span>
          {hasCaseRun
            ? <>
              <span>{pipeline?.eligible ?? 0} eligible · {pipeline?.analysed ?? 0} analysed</span>
              <span>{pipeline?.approvalCount ?? 0}/{pipeline?.sampleCount ?? 0} samples approved · {pipeline?.publicationStatus || 'UNPUBLISHED'}</span>
            </>
            : <span>{selectedPending ? 'Candidate has not run for this case.' : 'Approved memory ready for this case.'}</span>}
          {selectedPending && selectedState?.current_approved_version_id
            && <span>Previous approved version remains active until this candidate reaches 5/5.</span>}
          {selectedPending && <button type="button" disabled={busy || !dependenciesReady}
            onClick={() => void runSelectedCandidate()}>
            {hasCaseRun ? 'Rerun Candidate' : 'Run Candidate'}
          </button>}
          {!dependenciesReady && <span className="doctrineDependencyWarning">Approve the latest previous script first.</span>}
        </div>

        {hasCaseRun ? <>
          <b className="weeklySampleTitle">
            {approvalState === 'APPROVED' ? 'Approved sample' : 'Validation sample'} ({pipeline?.validationSamples.length || 0})
          </b>
          <DoctrineValidationSample scriptKey={selectedScriptKey}
            samples={pipeline?.validationSamples || []} nodes={caseAnalysisNodes} ranges={ranges}
            saving={operationState === 'REVIEWING'} reviewEnabled={approvalState === 'PENDING'}
            onNavigateRange={onNavigateRange} onDecision={(id, decision) => void saveReview(id, decision)} />
          {!pipeline?.validationSamples.length && <div className="weeklyScript1Empty">
            {approvalState === 'REJECTED'
              ? 'This script version was rejected and remains unpublished.'
              : 'No review samples are available for this run.'}
          </div>}
        </> : <div className="weeklyScript1Empty">
          {selectedPending
            ? dependenciesReady ? 'Run this candidate to create five review samples.' : 'Approve the latest previous script before running this candidate.'
            : 'Approved script memory loaded. Run Active Pipeline to refresh this case.'}
        </div>}
        {reviewError && <span role="alert">{reviewError}</span>}
      </>}
    </div>}
  </section>;
}
