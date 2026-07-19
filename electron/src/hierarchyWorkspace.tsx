import React, { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  buildHierarchyCoverageRows,
  compactDate,
  deriveCoverageYearOptions,
  filterCoverageRowsByYear,
  normalizeCoverageYearRange,
  rangeInterval,
  type HierarchyCoverageRow,
  type HierarchyLayer,
} from './hierarchyCoverage';
import { adaptMasterMapOutput, type MasterMapDocument, type MasterMapRangeNode } from './masterMapAdapter';

export type HierarchyWorkspaceMode = 'structure' | 'coverage' | 'python';
export type WeeklyAnalysisApprovalState = 'PENDING' | 'APPROVED' | 'REJECTED';
export type WeeklyAnalysisActivationResult = {
  ok: boolean; source?: 'LIVE' | 'DISPOSABLE_ANALYSIS_COPY'; liveDatabasePath?: string;
  analysisDatabasePath?: string; masterMap?: unknown; doctrineState?: unknown; error?: string;
};
export type WeeklyAnalysisBridge = {
  getPaths: () => Promise<{ ok: boolean; databasePath?: string; error?: string }>;
  getWeeklyScript1State: (args: { databasePath: string; caseRef: string; symbol: string }) => Promise<WeeklyAnalysisActivationResult>;
  runWeeklyScript1: (args: { databasePath: string; caseRef: string; symbol: string }) => Promise<WeeklyAnalysisActivationResult>;
  reviewWeeklyScript1: (args: { analysisDatabasePath: string; liveDatabasePath: string; runId: string; caseRef: string; symbol: string; canonicalRangeId: string; decision: 'APPROVED' | 'REJECTED' }) => Promise<WeeklyAnalysisActivationResult>;
  listDoctrineScripts?: (args: { analysisDatabasePath: string }) => Promise<{ ok: boolean; result?: unknown; error?: string }>;
  insertDoctrineScript?: (args: { analysisDatabasePath: string; displayName: string; scriptKey: string; versionLabel: string; adapterKey: string; executionOrder: number }) => Promise<{ ok: boolean; result?: unknown; canceled?: boolean; error?: string }>;
  runDoctrinePipeline?: (args: { analysisDatabasePath: string; caseRef: string; symbol: string }) => Promise<{ ok: boolean; result?: unknown; error?: string }>;
};
type Props = { ranges: Record<string, unknown>[]; structure: ReactNode; onNavigateRange: (range: Record<string, unknown>) => void; caseRef: string; symbol: string; weeklyAnalysisBridge?: WeeklyAnalysisBridge | null };
const LAYERS: HierarchyLayer[] = ['WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];

function defaultWeeklyAnalysisBridge(): WeeklyAnalysisBridge | null {
  const globals = globalThis as typeof globalThis & {
    localResearch?: Pick<WeeklyAnalysisBridge, 'getWeeklyScript1State' | 'runWeeklyScript1' | 'reviewWeeklyScript1' | 'listDoctrineScripts' | 'insertDoctrineScript' | 'runDoctrinePipeline'>;
    localMappingBridge?: Pick<WeeklyAnalysisBridge, 'getPaths'>;
  };
  if (!globals.localMappingBridge?.getPaths || !globals.localResearch?.getWeeklyScript1State || !globals.localResearch?.runWeeklyScript1 || !globals.localResearch?.reviewWeeklyScript1 || !globals.localResearch?.listDoctrineScripts || !globals.localResearch?.insertDoctrineScript) return null;
  return {
    getPaths: globals.localMappingBridge.getPaths,
    getWeeklyScript1State: globals.localResearch.getWeeklyScript1State,
    runWeeklyScript1: globals.localResearch.runWeeklyScript1,
    reviewWeeklyScript1: globals.localResearch.reviewWeeklyScript1,
    listDoctrineScripts: globals.localResearch.listDoctrineScripts,
    insertDoctrineScript: globals.localResearch.insertDoctrineScript,
    runDoctrinePipeline: globals.localResearch.runDoctrinePipeline,
  };
}

function script1Labels(node: MasterMapRangeNode) {
  const chronology = node.script1Chronology === 'RL_TO_RH' ? 'RL → RH'
    : node.script1Chronology === 'RH_TO_RL' ? 'RH → RL' : 'Pending';
  const bos = node.script1BosDirection === 'BOS_UP' ? 'BOS ▲'
    : node.script1BosDirection === 'BOS_DOWN' ? 'BOS ▼' : 'Pending';
  const status = node.script1ReviewStatus === 'APPROVED' ? 'Approved'
    : node.script1ReviewStatus === 'NEEDS_REVIEW' ? 'Needs Review'
    : node.script1ReviewStatus === 'REJECTED' ? 'Rejected' : 'Pending';
  return { chronology, bos, status };
}

function matchingRange(node: MasterMapRangeNode, ranges: Record<string, unknown>[]) {
  const sourceIds = new Set(node.sourceRefs.map((ref) => String(ref.sourceRecordId)));
  return ranges.find((item) => sourceIds.has(String(item.range_id || item.id || ''))) || null;
}

export function selectWeeklyValidationSample(nodes: MasterMapRangeNode[], limit = 5): MasterMapRangeNode[] {
  const selected: MasterMapRangeNode[] = [];
  const seen = new Set<string>();
  for (const node of nodes) {
    const key = `${node.script1Chronology || 'NONE'}|${node.script1BosDirection || 'NONE'}|${node.script1ProcessingStatus || 'NONE'}`;
    if (!seen.has(key)) { selected.push(node); seen.add(key); }
    if (selected.length >= limit) return selected;
  }
  for (const node of nodes) {
    if (!selected.includes(node)) selected.push(node);
    if (selected.length >= limit) break;
  }
  return selected;
}

function enrichStructureTree(node: ReactNode, enrichments: Map<string, { chronology: string; bos: string }>): ReactNode {
  if (Array.isArray(node)) return node.map((child) => enrichStructureTree(child, enrichments));
  if (!React.isValidElement(node)) return node;
  const props = node.props as Record<string, unknown>;
  const rangeId = String(props['data-range-id'] || '');
  const children = React.Children.toArray(props.children as ReactNode).map((child) => enrichStructureTree(child, enrichments));
  const enrichment = enrichments.get(rangeId);
  if (enrichment) children.push(<span key="script1-enrichment" className="weeklyScript1InlineEnrichment">{enrichment.chronology} · {enrichment.bos}</span>);
  return React.cloneElement(node, undefined, ...children);
}

function WeeklyValidationSample({ nodes, ranges, decisions, saving, onNavigateRange, onDecision }: {
  nodes: MasterMapRangeNode[]; ranges: Record<string, unknown>[];
  decisions: Map<string, string>; saving: boolean;
  onNavigateRange: (range: Record<string, unknown>) => void;
  onDecision: (canonicalRangeId: string, decision: 'APPROVED' | 'REJECTED') => void;
}) {
  return <div className="weeklyScript1Rows" aria-label="Weekly analysis validation sample">
    {nodes.map((node) => {
      const labels = script1Labels(node);
      const range = matchingRange(node, ranges);
      const decision = decisions.get(node.canonicalRangeId) || 'PENDING';
      return <div key={node.canonicalRangeId} className="weeklyScript1Sample">
        <button type="button" className="weeklyScript1Row" disabled={!range} onClick={() => range && onNavigateRange(range)}>
          <b>WEEKLY</b><span>{labels.chronology}</span><span>{labels.bos}</span><strong>{decision}</strong>
        </button>
        {decision === 'PENDING' && <div className="weeklySampleActions">
          <button type="button" disabled={saving} onClick={() => onDecision(node.canonicalRangeId, 'APPROVED')}>Approve</button>
          <button type="button" disabled={saving} onClick={() => onDecision(node.canonicalRangeId, 'REJECTED')}>Reject</button>
        </div>}
      </div>;
    })}
  </div>;
}

function CoverageRow({ row, onNavigate }: { row: HierarchyCoverageRow; onNavigate: (range: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false);
  const parentWindow = rangeInterval(row.parent);
  return <div className="hierarchyCoverageRow" data-parent-range-id={row.parentId}>
    <div className="hierarchyCoverageLine">
      <button type="button" className="hierarchyCoverageExpand" onClick={() => setOpen((value) => !value)} aria-expanded={open}>{open ? '▼' : '▶'}</button>
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
      {row.childLayer !== null && !row.gaps.length && <span>Full {row.childLayer.toLowerCase()} coverage.</span>}
      {row.gaps.map((gap) => <button key={`${gap.startMs}-${gap.endMs}`} type="button" onClick={() => onNavigate({ ...row.parent, range_start_time: gap.startIso, range_end_time: gap.endIso })}>
        {compactDate(gap.startMs)} <span aria-hidden="true">&lt;-----&gt;</span> {compactDate(gap.endMs)}
      </button>)}
    </div>}
  </div>;
}

export function HierarchyWorkspace({ ranges, structure, onNavigateRange, caseRef, symbol, weeklyAnalysisBridge }: Props) {
  const [mode, setMode] = useState<HierarchyWorkspaceMode>('structure');
  const [layer, setLayer] = useState<HierarchyLayer>('WEEKLY');
  const rows = useMemo(() => buildHierarchyCoverageRows(ranges, layer), [ranges, layer]);
  const yearOptions = useMemo(() => deriveCoverageYearOptions(rows), [rows]);
  const yearOptionsKey = yearOptions.join(',');
  const [fromYear, setFromYear] = useState<number | null>(null);
  const [toYear, setToYear] = useState<number | null>(null);
  const [analysisState, setAnalysisState] = useState<'dormant' | 'running' | 'active' | 'error'>('dormant');
  const [analysisDocument, setAnalysisDocument] = useState<MasterMapDocument | null>(null);
  const [analysisDatabasePath, setAnalysisDatabasePath] = useState('');
  const [liveDatabasePath, setLiveDatabasePath] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [doctrineState, setDoctrineState] = useState<any>(null);
  const [storedScripts, setStoredScripts] = useState<any[]>([]);
  const [insertOpen, setInsertOpen] = useState(false);
  const [insertName, setInsertName] = useState('Weekly Script');
  const [insertKey, setInsertKey] = useState('weekly_structure');
  const [insertVersion, setInsertVersion] = useState('1');
  const [pipelineSummary, setPipelineSummary] = useState<any>(null);
  const previousLayer = useRef<HierarchyLayer>(layer);

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
      if (!bridge || !caseRef || !symbol) return;
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
          setAnalysisState('active');
        }
      } catch { /* absence of prior analysis remains dormant */ }
    };
    void restore();
    return () => { cancelled = true; };
  }, [caseRef, symbol, weeklyAnalysisBridge]);

  useEffect(() => {
    const first = yearOptions[0] ?? null;
    const last = yearOptions[yearOptions.length - 1] ?? null;
    const layerChanged = previousLayer.current !== layer;
    previousLayer.current = layer;
    setFromYear((current) => layerChanged || current === null ? first : Math.max(first ?? current, Math.min(current, last ?? current)));
    setToYear((current) => layerChanged || current === null ? last : Math.max(first ?? current, Math.min(current, last ?? current)));
  }, [layer, yearOptionsKey]);

  const filteredRows = useMemo(() => {
    if (fromYear === null || toYear === null) return rows;
    return filterCoverageRowsByYear(rows, fromYear, toYear);
  }, [rows, fromYear, toYear]);
  const updateYears = (nextFrom: number, nextTo: number) => {
    const normalized = normalizeCoverageYearRange(nextFrom, nextTo);
    setFromYear(normalized.fromYear);
    setToYear(normalized.toYear);
  };
  const activateWeeklyAnalysis = async () => {
    const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
    if (!bridge) {
      setAnalysisState('error'); setAnalysisError('Weekly analysis bridge is unavailable. Open this workspace in Electron.'); return;
    }
    setAnalysisState('running'); setAnalysisError('');
    try {
      if (!caseRef) throw new Error('Select a case before running Weekly analysis.');
      if (!symbol) throw new Error('Weekly analysis requires the selected instrument.');
      const paths = await bridge.getPaths();
      const databasePath = String(paths.databasePath || '').trim();
      if (!paths.ok || !databasePath) throw new Error(paths.error || 'Explicit Range Library database path is unavailable.');
      const result = await bridge.runWeeklyScript1({ databasePath, caseRef, symbol });
      if (!result.ok || result.source !== 'DISPOSABLE_ANALYSIS_COPY' || !result.masterMap || !result.analysisDatabasePath) {
        throw new Error(result.error || 'Weekly analysis did not return a disposable-copy Master Map.');
      }
      setAnalysisDocument(adaptMasterMapOutput(result.masterMap));
      setAnalysisDatabasePath(result.analysisDatabasePath);
      setLiveDatabasePath(databasePath);
      setDoctrineState(result.doctrineState || null);
      setAnalysisState('active');
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const safeMessage = /candle/i.test(detail)
        ? 'Weekly analysis could not start because the candle source database was not resolved.'
        : /case/i.test(detail) ? detail : 'Weekly analysis could not start. Check the Electron logs for details.';
      setAnalysisState('error'); setAnalysisError(safeMessage);
    }
  };
  const caseAnalysisNodes = useMemo(() => analysisDocument?.trustedRoot.children.filter(
    (node) => node.layer === 'WEEKLY' && node.sourceRefs.some((ref) => ref.caseRef === caseRef),
  ) || [], [analysisDocument, caseRef]);
  const legacyPipeline = analysisDocument?.weeklyAnalysis || null;
  const doctrineRunState = doctrineState?.run ? doctrineState : doctrineState?.runs?.[0] || null;
  const doctrineRun = doctrineRunState?.run || null;
  const doctrineSamples = doctrineRunState?.samples || [];
  const pipeline = doctrineRun ? {
    pipelineName: 'Weekly analysis', version: doctrineState?.version_label || '1', runId: doctrineRun.run_id,
    approvalState: doctrineRun.approval_status, eligible: doctrineRun.eligible_count, analysed: doctrineRun.analysed_count,
    approvalCount: doctrineRun.approval_count, sampleCount: doctrineRun.sample_count,
    publicationStatus: doctrineRun.publication_status,
    validationSamples: doctrineSamples.map((sample: any) => ({ canonicalRangeId: sample.canonical_range_id,
      sampleOrder: sample.sample_order, decision: sample.decision, decidedAt: sample.decided_at })),
  } : legacyPipeline;
  const validationSample = useMemo(() => {
    if (!pipeline || pipeline.approvalState !== 'PENDING') return [];
    const ids = new Set(pipeline.validationSamples.map((sample) => sample.canonicalRangeId));
    return caseAnalysisNodes.filter((node) => ids.has(node.canonicalRangeId)).sort((a, b) =>
      (pipeline.validationSamples.find((sample) => sample.canonicalRangeId === a.canonicalRangeId)?.sampleOrder || 0)
      - (pipeline.validationSamples.find((sample) => sample.canonicalRangeId === b.canonicalRangeId)?.sampleOrder || 0));
  }, [caseAnalysisNodes, pipeline]);
  const sampleDecisions = useMemo(() => new Map(
    (pipeline?.validationSamples || []).map((sample) => [sample.canonicalRangeId, sample.decision]),
  ), [pipeline]);
  const approvedNodes = pipeline?.approvalState === 'APPROVED'
    ? caseAnalysisNodes.filter((node) => node.script1ReviewStatus === 'APPROVED') : [];
  const approvedByRangeId = useMemo(() => {
    const result = new Map<string, { chronology: string; bos: string }>();
    for (const node of approvedNodes) {
      const range = matchingRange(node, ranges);
      const id = String(range?.range_id || range?.id || '');
      if (id) result.set(id, script1Labels(node));
    }
    return result;
  }, [approvedNodes, ranges]);
  const saveReview = async (canonicalRangeId: string, decision: 'APPROVED' | 'REJECTED') => {
    const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
    if (!bridge || !pipeline?.runId || !analysisDatabasePath) return;
    setReviewSaving(true); setReviewError('');
    try {
      const result = await bridge.reviewWeeklyScript1({ analysisDatabasePath, liveDatabasePath,
        runId: pipeline.runId, caseRef, symbol, canonicalRangeId, decision });
      if (!result.ok || !result.masterMap) throw new Error(result.error || 'Review update failed.');
      setAnalysisDocument(adaptMasterMapOutput(result.masterMap));
      setDoctrineState(result.doctrineState || doctrineState);
    } catch {
      setReviewError('The review could not be saved safely. The existing hierarchy is unchanged.');
    } finally { setReviewSaving(false); }
  };
  const loadStoredScripts = async () => {
    const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
    if (!bridge?.listDoctrineScripts || !analysisDatabasePath) return;
    const result = await bridge.listDoctrineScripts({ analysisDatabasePath });
    if (result.ok && Array.isArray(result.result)) setStoredScripts(result.result);
  };
  const insertStoredScript = async () => {
    const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
    if (!bridge?.insertDoctrineScript || !analysisDatabasePath) return;
    const result = await bridge.insertDoctrineScript({ analysisDatabasePath, displayName: insertName,
      scriptKey: insertKey, versionLabel: insertVersion, adapterKey: 'weekly_chronology_bos_v1', executionOrder: 100 });
    if (result.ok) { setInsertOpen(false); await loadStoredScripts(); }
  };
  const rerunActivePipeline = async () => {
    const bridge = weeklyAnalysisBridge === undefined ? defaultWeeklyAnalysisBridge() : weeklyAnalysisBridge;
    if (!bridge?.runDoctrinePipeline || !analysisDatabasePath) return;
    const result = await bridge.runDoctrinePipeline({ analysisDatabasePath, caseRef, symbol });
    if (result.ok) setPipelineSummary(result.result || null);
  };

  return <section className="hierarchyWorkspace" data-mode={mode} aria-label="Hierarchy workspace">
    <div className="hierarchyWorkspaceModes" role="tablist" aria-label="Hierarchy modes">
      {(['structure', 'coverage', 'python'] as HierarchyWorkspaceMode[]).map((item) => <button key={item} type="button" role="tab" aria-selected={mode === item} className={mode === item ? 'active' : ''} onClick={() => setMode(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}
    </div>
    {mode === 'structure' && <div className="hierarchyWorkspaceBody structureMode">
      {enrichStructureTree(structure, approvedByRangeId)}
    </div>}
    {mode === 'coverage' && <div className="hierarchyWorkspaceBody coverageMode">
      <div className="hierarchyCoverageFilters" role="group" aria-label="Coverage layer">{LAYERS.map((item) => <button key={item} type="button" className={layer === item ? 'active' : ''} aria-pressed={layer === item} onClick={() => setLayer(item)}>{item[0] + item.slice(1).toLowerCase()}</button>)}</div>
      {!!yearOptions.length && fromYear !== null && toYear !== null && <div className="hierarchyCoverageYears" aria-label="Coverage year range">
        <label>From year<select aria-label="From year" value={fromYear} onChange={(event) => updateYears(Number(event.target.value), toYear)}>{yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        <span aria-hidden="true">→</span>
        <label>To year<select aria-label="To year" value={toYear} onChange={(event) => updateYears(fromYear, Number(event.target.value))}>{yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
      </div>}
      <div className="hierarchyCoverageScroll">{!filteredRows.length && <span className="caseLedgerEmpty">No {layer.toLowerCase()} ranges in this year range.</span>}{filteredRows.map((row) => <CoverageRow key={row.parentId} row={row} onNavigate={onNavigateRange} />)}</div>
    </div>}
    {mode === 'python' && <div className="hierarchyWorkspaceBody pythonMode">
      <div className="doctrineScriptControls">
        <button type="button" disabled={!analysisDatabasePath} onClick={() => setInsertOpen((value) => !value)}>Insert Script</button>
        <button type="button" disabled={!analysisDatabasePath} onClick={() => void loadStoredScripts()}>Stored Scripts</button>
        <button type="button" disabled={!analysisDatabasePath || pipeline?.approvalState !== 'APPROVED'} onClick={() => void rerunActivePipeline()}>Run Active Pipeline</button>
      </div>
      {pipelineSummary && <span role="status">{pipelineSummary.skipped_unchanged ?? 0} unchanged skipped · {pipelineSummary.processed ?? 0} processed</span>}
      {insertOpen && <div className="doctrineInsertForm" aria-label="Insert doctrine script">
        <label>Name<input value={insertName} onChange={(event) => setInsertName(event.target.value)} /></label>
        <label>Script key<input value={insertKey} onChange={(event) => setInsertKey(event.target.value)} /></label>
        <label>Version<input value={insertVersion} onChange={(event) => setInsertVersion(event.target.value)} /></label>
        <label>Adapter<select value="weekly_chronology_bos_v1" disabled><option>weekly_chronology_bos_v1</option></select></label>
        <button type="button" disabled={!insertName.trim() || !insertKey.trim() || !insertVersion.trim()} onClick={() => void insertStoredScript()}>Choose package…</button>
      </div>}
      {!!storedScripts.length && <div className="doctrineStoredScripts" aria-label="Stored doctrine scripts">{storedScripts.map((script) =>
        <span key={script.script_id}><b>{script.display_name}</b> · {script.version_label} · {script.status}{script.status === 'APPROVED' ? ' · ACTIVE' : ''}</span>)}</div>}
      <div className="weeklyScript1Header">
        <div><b>Weekly Script 1</b><span className={`weeklyScript1State ${analysisState}`}>{analysisState === 'active' ? 'Active · Current' : analysisState}</span></div>
        <button type="button" onClick={() => void activateWeeklyAnalysis()} disabled={analysisState === 'running' || (!!pipeline && pipeline.approvalState !== 'PENDING')}>{analysisState === 'running' ? 'Running…' : pipeline?.approvalState === 'APPROVED' ? 'Analysis Approved' : pipeline?.approvalState === 'REJECTED' ? 'Analysis Rejected' : 'Run Weekly Analysis'}</button>
      </div>
      <span className={`weeklyScript1Source ${analysisState === 'active' ? 'disposable' : 'live'}`}>{analysisState === 'active' ? 'DISPOSABLE ANALYSIS COPY' : 'LIVE'}</span>
      {analysisState === 'dormant' && <span role="status">Analysis dormant until manually activated.</span>}
      {analysisState === 'running' && <span role="status">Creating safe copy and running Weekly Script 1…</span>}
      {analysisState === 'error' && <div role="alert" className="weeklyScript1Error"><b>Weekly analysis failed safely</b><span>{analysisError}</span><span>Existing hierarchy remains available.</span></div>}
      {analysisState === 'active' && analysisDocument && <>
        <span className="weeklyScript1Db" title={analysisDatabasePath}>{analysisDatabasePath}</span>
        <div className="weeklyPipelineSummary" aria-label="Weekly analysis run summary">
          <b>{pipeline?.pipelineName || 'Weekly analysis'}</b>
          <span>Version {pipeline?.version || 'unknown'} · {pipeline?.approvalState || 'PENDING'}</span>
          <span>{pipeline?.eligible ?? caseAnalysisNodes.length} eligible · {pipeline?.analysed ?? caseAnalysisNodes.length} analysed</span>
          <span>{pipeline?.approvalCount ?? 0}/{pipeline?.sampleCount ?? 0} samples approved · {pipeline?.publicationStatus || 'UNPUBLISHED'}</span>
        </div>
        <b className="weeklySampleTitle">Validation sample ({validationSample.length})</b>
        <WeeklyValidationSample nodes={validationSample} ranges={ranges} decisions={sampleDecisions} saving={reviewSaving}
          onNavigateRange={onNavigateRange} onDecision={(id, decision) => void saveReview(id, decision)} />
        {!validationSample.length && <div className="weeklyScript1Empty">{pipeline?.approvalState === 'APPROVED'
          ? 'This analysis version is approved and published in the main hierarchy.'
          : pipeline?.approvalState === 'REJECTED' ? 'This analysis version was rejected and remains unpublished.'
          : 'No eligible Weekly results are available for validation.'}</div>}
        {reviewError && <span role="alert">{reviewError}</span>}
      </>}
    </div>}
  </section>;
}
