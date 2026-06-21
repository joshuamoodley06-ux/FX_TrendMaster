import React, { useCallback, useMemo, useState } from 'react';
import {
  auditSamplesToFocusedOverlays,
  auditSampleToViewTarget,
  type RangeAuditSample,
  type RangeAuditViewTarget,
  type ResearchChartOverlay,
} from './reviewCandidateClient';
import { getLocalResearchBridge, type LocalResearchDatabaseStatus, type LocalResearchRunResult } from './localResearchClient';
import { LocalResearchControls } from './localResearchControls';
import { LocalResearchDatabasePanel } from './localResearchDatabasePanel';
import {
  WEEKLY_RESEARCH_AUDIT_TARGET,
  activateWeeklySeed,
  auditSamplesFromResult,
  checkWeeklySeed,
  createManualWeeklySeed,
  friendlyError,
  listWeeklySeedRanges,
  loadWeeklyAuditSamples,
  loadWeeklyScanCandidates,
  promotedCountFromResult,
  recordWeeklyAuditVerdict,
  runWeeklyHistoricalScan,
  runWeeklyPromote,
  diagnoseWeeklyScan,
  scanDiagnoseFromResult,
  scanSummaryFromResult,
  suggestionIdFromSample,
  weeklySeedCheckFromResult,
  weeklySeedRangesFromResult,
  type WeeklyResearchPhase,
  type WeeklyResearchSummary,
  type WeeklyScanSummary,
} from './localResearchWorkflow';
import { retracementPctDisplay } from './analystPresets';
import type { WeeklySeedRangeRow, WeeklyScanDiagnose } from './localResearchClient';
import { buildWeeklyResearchSession } from './weeklyResearchSession';

export type VisibleWeeklySeed = {
  rangeHigh: number;
  rangeLow: number;
  rangeHighTime?: string;
  rangeLowTime?: string;
};

type Props = {
  symbol: string;
  onViewOnChart?: (target: RangeAuditViewTarget, opts?: { enterFullscreen?: boolean }) => void;
  onResearchOverlaysChange?: (overlays: ResearchChartOverlay[]) => void;
  onScanComplete?: (session: import('./weeklyResearchSession').WeeklyResearchSession) => void;
  setMessage?: (msg: string) => void;
  getVisibleWeeklySeed?: () => VisibleWeeklySeed | null;
};

function showSampleOnChart(
  sample: RangeAuditSample | null | undefined,
  onViewOnChart?: (target: RangeAuditViewTarget, opts?: { enterFullscreen?: boolean }) => void,
  opts?: { enterFullscreen?: boolean },
) {
  const target = sample ? auditSampleToViewTarget(sample) : null;
  if (target && onViewOnChart) onViewOnChart(target, opts);
}

function formatErrorDetails(result: LocalResearchRunResult): string {
  return [result.error, result.stderr, result.stdout].filter((part) => part?.trim()).join('\n\n');
}

function chipStatusLabel(
  phase: WeeklyResearchPhase,
  busy: boolean,
  auditPosition: number,
): string {
  if (phase === 'error') return 'Research failed';
  if (phase === 'seed_setup') return 'Seed required';
  if (phase === 'scanning' || phase === 'promoting' || busy) return 'Running';
  if (phase === 'audit') return `Audit ${auditPosition} of ${WEEKLY_RESEARCH_AUDIT_TARGET}`;
  if (phase === 'promote_prompt') return 'Review results';
  if (phase === 'summary') return 'Complete';
  return 'Ready';
}

function formatLifecycleCounts(counts: Record<string, number> | undefined): string | null {
  if (!counts || Object.keys(counts).length === 0) return null;
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([state, n]) => `${state} (${n})`)
    .join(' · ');
}

function formatRetracementLine(sample: RangeAuditSample | null | undefined): string | null {
  if (!sample) return null;
  const pct = sample.retracement_percent
    ?? (typeof sample.meta_json?.retracement_percent === 'number' ? sample.meta_json.retracement_percent : null);
  const cls = sample.retracement_class
    ?? (typeof sample.meta_json?.retracement_class === 'string' ? sample.meta_json.retracement_class : null);
  const price = sample.retracement_price
    ?? (typeof sample.meta_json?.retracement_price === 'number' ? sample.meta_json.retracement_price : null);
  if (pct == null && !cls) return null;
  const pctText = retracementPctDisplay(pct ?? undefined);
  const priceText = price != null ? ` @ ${Number(price).toFixed(2)}` : '';
  return `Retracement ${cls || '—'} · ${pctText}${priceText}`;
}

function zeroRangeScanMessage(
  summary: WeeklyScanSummary,
  diagnose: WeeklyScanDiagnose | null,
): string {
  if (summary.candlesScanned <= 0) {
    return 'No weekly candles were scanned. Pull from VPS or choose a database file with W1 history first.';
  }
  const seedRh = diagnose?.seed?.range_high_price;
  const seedRl = diagnose?.seed?.range_low_price;
  const seedLine = diagnose?.hasSeed && seedRh != null && seedRl != null
    ? `Active seed RH ${seedRh} · RL ${seedRl}. `
    : !diagnose?.hasSeed
      ? 'No ACTIVE W1 seed in map_ranges. '
      : '';
  const seedSpan = seedRh != null && seedRl != null ? Number(seedRh) - Number(seedRl) : null;
  const seedWarning = seedSpan != null && seedSpan > 400
    ? 'This seed box is very wide — save the visible Jan 2025 weekly RH/RL from the chart if you expected a tighter range. '
    : '';
  const hint = diagnose?.hint
    || 'Baseline replay scan uses RANGE_V2 per-week replay (Review Candidate path). Requires active seed context for doctrine_v2.';
  const candidateLine = summary.rangesFound > 0
    ? `${summary.rangesFound} promotable candidate${summary.rangesFound === 1 ? '' : 's'}`
    : '0 promotable candidates';
  return `${seedLine}${seedWarning}Scanned ${summary.candlesScanned} weekly steps — ${summary.noValidRange} marked no-valid-range, ${candidateLine}. ${hint}`;
}

export function WeeklyResearchPanel({ symbol, onViewOnChart, onResearchOverlaysChange, onScanComplete, setMessage, getVisibleWeeklySeed }: Props) {
  const bridge = getLocalResearchBridge();
  const [expanded, setExpanded] = useState(false);
  const [phase, setPhase] = useState<WeeklyResearchPhase>('idle');
  const [statusLine, setStatusLine] = useState('Baseline replay detector — same path as Review Candidate.');
  const [scanSummary, setScanSummary] = useState<WeeklyScanSummary | null>(null);
  const [promotedCount, setPromotedCount] = useState(0);
  const [auditSamples, setAuditSamples] = useState<RangeAuditSample[]>([]);
  const [auditIndex, setAuditIndex] = useState(0);
  const [passCount, setPassCount] = useState(0);
  const [failCount, setFailCount] = useState(0);
  const [skipCount, setSkipCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [finalSummary, setFinalSummary] = useState<WeeklyResearchSummary | null>(null);
  const [errorSummary, setErrorSummary] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [databaseStatus, setDatabaseStatus] = useState<LocalResearchDatabaseStatus | null>(null);
  const [seedSetupView, setSeedSetupView] = useState<'prompt' | 'pick_list'>('prompt');
  const [seedRanges, setSeedRanges] = useState<WeeklySeedRangeRow[]>([]);
  const [manualSeedOverride, setManualSeedOverride] = useState(false);
  const [experimentalChainMode, setExperimentalChainMode] = useState(false);
  const [reviewedTruthSeed, setReviewedTruthSeed] = useState(false);
  const [scanDiagnose, setScanDiagnose] = useState<WeeklyScanDiagnose | null>(null);
  const [scanCandidates, setScanCandidates] = useState<RangeAuditSample[]>([]);
  const [scanCandidateIndex, setScanCandidateIndex] = useState(0);

  const databasePath = databaseStatus?.databasePath;
  const databaseReady = Boolean(databaseStatus?.readyForWeeklyScan);
  const visibleWeeklySeed = getVisibleWeeklySeed?.() ?? null;

  const auditPosition = Math.min(auditIndex + 1, WEEKLY_RESEARCH_AUDIT_TARGET);
  const currentSample = auditSamples[auditIndex] || null;
  const currentScanCandidate = scanCandidates[scanCandidateIndex] || null;
  const chipStatus = chipStatusLabel(phase, busy, auditPosition);

  const setFailure = useCallback((result: LocalResearchRunResult, fallback?: string) => {
    setPhase('error');
    setErrorSummary(friendlyError(result) || fallback || 'Research failed.');
    setErrorDetails(formatErrorDetails(result) || null);
    setStatusLine('Research failed.');
  }, []);

  const resetWorkflow = useCallback(() => {
    setPhase('idle');
    setStatusLine('Baseline replay detector — same path as Review Candidate.');
    setScanSummary(null);
    setScanDiagnose(null);
    setScanCandidates([]);
    setScanCandidateIndex(0);
    onResearchOverlaysChange?.([]);
    setPromotedCount(0);
    setAuditSamples([]);
    setAuditIndex(0);
    setPassCount(0);
    setFailCount(0);
    setSkipCount(0);
    setFinalSummary(null);
    setErrorSummary(null);
    setErrorDetails(null);
    setSeedSetupView('prompt');
    setSeedRanges([]);
  }, [onResearchOverlaysChange]);

  const publishResearchOverlays = useCallback((
    samples: RangeAuditSample[],
    activeIndex = 0,
  ) => {
    if (!onResearchOverlaysChange) return;
    onResearchOverlaysChange(auditSamplesToFocusedOverlays(samples, activeIndex, { includePrior: false }));
  }, [onResearchOverlaysChange]);

  const executeWeeklyScan = useCallback(async () => {
    setBusy(true);
    setPhase('scanning');
    setStatusLine('Scanning 2025 W1 — swing discovery + BOS→reclaim (same as Review Candidate)…');
    try {
      const scanResult = await runWeeklyHistoricalScan(databasePath, {
        useManualSeed: manualSeedOverride,
        experimentalChain: experimentalChainMode,
        reviewedTruthSeed,
      });
      const summary = scanSummaryFromResult(scanResult);
      if (!scanResult.ok || !summary) {
        setFailure(scanResult);
        return;
      }
      setScanSummary(summary);
      setScanDiagnose(null);
      setScanCandidates([]);
      setScanCandidateIndex(0);
      let loadedCandidates: RangeAuditSample[] = [];
      if (summary.rangesFound === 0 && summary.detectionRunId) {
        const diagnoseResult = await diagnoseWeeklyScan({
          symbol,
          detectionRunId: summary.detectionRunId,
          databasePath,
        });
        setScanDiagnose(scanDiagnoseFromResult(diagnoseResult));
      } else if (summary.rangesFound > 0 && summary.detectionRunId) {
        const candidateResult = await loadWeeklyScanCandidates(
          summary.detectionRunId,
          databasePath,
          Math.max(summary.rangesFound, 20),
        );
        const candidates = auditSamplesFromResult(candidateResult);
        loadedCandidates = candidates;
        setScanCandidates(candidates);
        if (candidates.length > 0) {
          setScanCandidateIndex(0);
          publishResearchOverlays(candidates, 0);
          showSampleOnChart(candidates[0], onViewOnChart, { enterFullscreen: true });
          setStatusLine('Scan complete. Ranges loaded on fullscreen chart — review below.');
        } else {
          setStatusLine('Scan complete. Candidates saved but could not load for chart view — try Refresh.');
        }
      } else {
        setStatusLine('Scan complete. Review the counts below.');
      }
      setPhase('promote_prompt');
      setMessage?.(`Weekly scan found ${summary.rangesFound} ranges for ${symbol} 2025`);
      if (summary.detectionRunId && loadedCandidates.length > 0) {
        const session = buildWeeklyResearchSession({
          symbol,
          summary,
          samples: loadedCandidates,
        });
        if (session) onScanComplete?.(session);
      }
    } finally {
      setBusy(false);
    }
  }, [databasePath, experimentalChainMode, manualSeedOverride, onScanComplete, onViewOnChart, publishResearchOverlays, reviewedTruthSeed, setFailure, setMessage, symbol]);

  const beginAudit = useCallback(async (
    rangesFound: number,
    promoted: number,
    detectionRunId?: string | null,
  ) => {
    setPhase('audit');
    setStatusLine('Loading weekly ranges for visual check…');
    let auditResult = await loadWeeklyAuditSamples(WEEKLY_RESEARCH_AUDIT_TARGET, databasePath);
    let samples = auditSamplesFromResult(auditResult);
    if (samples.length === 0 && detectionRunId) {
      auditResult = await loadWeeklyScanCandidates(
        detectionRunId,
        databasePath,
        WEEKLY_RESEARCH_AUDIT_TARGET,
      );
      samples = auditSamplesFromResult(auditResult);
    }
    if (samples.length === 0) {
      setPhase('error');
      const hint = promoted > 0
        ? 'Promoted ranges were saved but could not be loaded for audit. Check the database path and try again.'
        : rangesFound > 0
          ? 'No ranges were promoted to map_ranges. Confirm promote completed, or re-run scan and promote.'
          : 'No ranges were found in the scan. Save your W1 seed and run again.';
      setErrorSummary(hint);
      setErrorDetails(null);
      setStatusLine('Research paused — no ranges to audit.');
      return;
    }
    const queue = samples.slice(0, WEEKLY_RESEARCH_AUDIT_TARGET);
    setAuditSamples(queue);
    setAuditIndex(0);
    setPassCount(0);
    setFailCount(0);
    setSkipCount(0);
    setPromotedCount(promoted);
    setScanSummary((prev) => prev || { rangesFound, noValidRange: 0, candlesScanned: 0 });
    setStatusLine('Review each range on the chart. Mark Pass or Fail, or use Next to skip.');
    publishResearchOverlays(queue, 0);
    showSampleOnChart(queue[0], onViewOnChart, { enterFullscreen: true });
    setMessage?.(`Weekly research audit started · ${queue.length} ranges loaded`);
  }, [databasePath, onViewOnChart, publishResearchOverlays, setFailure, setMessage]);

  const runWeeklyResearch = async () => {
    if (!bridge || busy) return;
    if (!databaseReady) {
      setExpanded(true);
      setPhase('idle');
      setStatusLine('Choose a local database with W1 candles before running weekly research.');
      setMessage?.('Local database not ready — choose or copy your VPS database file first.');
      return;
    }
    await executeWeeklyScan();
  };

  const openManualSeedSetup = async () => {
    if (!bridge || busy) return;
    setExpanded(true);
    setPhase('seed_setup');
    setSeedSetupView('prompt');
    setStatusLine('Optional manual seed — only needed for Advanced override mode.');
  };

  const cancelSeedSetup = () => {
    setPhase('idle');
    setSeedSetupView('prompt');
    setStatusLine('Baseline replay detector — same path as Review Candidate.');
  };

  const useVisibleSeed = async () => {
    if (!visibleWeeklySeed || busy) return;
    setBusy(true);
    setStatusLine('Saving weekly seed from chart RH/RL…');
    try {
      const result = await createManualWeeklySeed({
        symbol,
        rangeHigh: visibleWeeklySeed.rangeHigh,
        rangeLow: visibleWeeklySeed.rangeLow,
        rangeHighTime: visibleWeeklySeed.rangeHighTime,
        rangeLowTime: visibleWeeklySeed.rangeLowTime,
        databasePath,
      });
      const seeded = weeklySeedCheckFromResult(result);
      if (!result.ok || !seeded?.has_seed) {
        setFailure(result, 'Could not create weekly seed range.');
        return;
      }
      setPhase('idle');
      setSeedSetupView('prompt');
      setStatusLine(
        `Weekly seed saved · RH ${visibleWeeklySeed.rangeHigh} · RL ${visibleWeeklySeed.rangeLow}. Run scan when ready.`,
      );
      setMessage?.(`Weekly seed #${seeded.seed?.id ?? 'saved'} · chart stays visible — run scan next`);
    } finally {
      setBusy(false);
    }
  };

  const openSeedPicker = async () => {
    if (busy) return;
    setBusy(true);
    setStatusLine('Loading existing W1 ranges…');
    try {
      const listResult = await listWeeklySeedRanges(symbol, databasePath);
      const ranges = weeklySeedRangesFromResult(listResult);
      if (!listResult.ok) {
        setFailure(listResult, 'Could not list weekly ranges.');
        return;
      }
      setSeedRanges(ranges);
      setSeedSetupView('pick_list');
      setStatusLine(ranges.length
        ? 'Select an existing W1 range to use as the weekly seed.'
        : 'No W1 ranges found in the local database.');
    } finally {
      setBusy(false);
    }
  };

  const selectExistingSeed = async (rangeId: number) => {
    if (busy) return;
    setBusy(true);
    setStatusLine('Activating selected weekly seed…');
    try {
      const result = await activateWeeklySeed({ symbol, rangeId, databasePath });
      const check = weeklySeedCheckFromResult(result);
      if (!result.ok || !check?.has_seed) {
        setFailure(result, 'Could not activate weekly seed range.');
        return;
      }
      setMessage?.(`Weekly seed activated · range #${rangeId}`);
      setPhase('idle');
      setStatusLine(`Weekly seed active · range #${rangeId}. Run scan when ready.`);
    } finally {
      setBusy(false);
    }
  };

  const declinePromote = () => {
    setPhase('idle');
    setStatusLine('Promote skipped. Run weekly research again when ready.');
  };

  const acceptPromote = async () => {
    if (!scanSummary || busy) return;
    setBusy(true);
    setPhase('promoting');
    setStatusLine('Saving promoted weekly ranges…');
    try {
      const promoteResult = await runWeeklyPromote(databasePath, scanSummary.detectionRunId);
      if (!promoteResult.ok) {
        setFailure(promoteResult);
        return;
      }
      const promoted = promotedCountFromResult(promoteResult);
      setPromotedCount(promoted);
      if (scanSummary.detectionRunId && promoted > 0) {
        const promotedResult = await loadWeeklyScanCandidates(
          scanSummary.detectionRunId,
          databasePath,
          Math.max(promoted, scanSummary.rangesFound, 50),
          'confirmed_ranges',
        );
        const promotedSamples = auditSamplesFromResult(promotedResult);
        if (promotedSamples.length) {
          publishResearchOverlays(promotedSamples, 0);
          showSampleOnChart(promotedSamples[0], onViewOnChart, { enterFullscreen: true });
        }
      }
      await beginAudit(scanSummary.rangesFound, promoted, scanSummary.detectionRunId);
    } finally {
      setBusy(false);
    }
  };

  const advanceAudit = useCallback((
    nextIndex: number,
    counts?: { pass: number; fail: number; skip: number },
  ) => {
    const pass = counts?.pass ?? passCount;
    const fail = counts?.fail ?? failCount;
    const skip = counts?.skip ?? skipCount;
    if (nextIndex >= WEEKLY_RESEARCH_AUDIT_TARGET || nextIndex >= auditSamples.length) {
      const summary: WeeklyResearchSummary = {
        audited: pass + fail + skip,
        pass,
        fail,
        skipped: skip,
        rangesFound: scanSummary?.rangesFound || 0,
        promoted: promotedCount,
      };
      setFinalSummary(summary);
      setPhase('summary');
      setStatusLine('Weekly research audit complete.');
      setMessage?.(`Audit complete · Pass ${summary.pass} · Fail ${summary.fail}`);
      return;
    }
    setAuditIndex(nextIndex);
    publishResearchOverlays(auditSamples, nextIndex);
    showSampleOnChart(auditSamples[nextIndex], onViewOnChart, { enterFullscreen: true });
  }, [auditSamples, failCount, onViewOnChart, passCount, promotedCount, publishResearchOverlays, scanSummary, setMessage, skipCount]);

  const onPass = async () => {
    if (phase !== 'audit' || busy || !currentSample) return;
    const suggestionId = suggestionIdFromSample(currentSample);
    if (!suggestionId) {
      setStatusLine('This range cannot be recorded. Use Next to continue.');
      return;
    }
    setBusy(true);
    try {
      const result = await recordWeeklyAuditVerdict(suggestionId, true, databasePath);
      if (!result.ok) {
        setFailure(result);
        return;
      }
      const nextPass = passCount + 1;
      setPassCount(nextPass);
      advanceAudit(auditIndex + 1, { pass: nextPass, fail: failCount, skip: skipCount });
    } finally {
      setBusy(false);
    }
  };

  const onFail = async () => {
    if (phase !== 'audit' || busy || !currentSample) return;
    const suggestionId = suggestionIdFromSample(currentSample);
    if (!suggestionId) {
      setStatusLine('This range cannot be recorded. Use Next to continue.');
      return;
    }
    setBusy(true);
    try {
      const result = await recordWeeklyAuditVerdict(suggestionId, false, databasePath);
      if (!result.ok) {
        setFailure(result);
        return;
      }
      const nextFail = failCount + 1;
      setFailCount(nextFail);
      advanceAudit(auditIndex + 1, { pass: passCount, fail: nextFail, skip: skipCount });
    } finally {
      setBusy(false);
    }
  };

  const onNext = () => {
    if (phase !== 'audit' || busy) return;
    const nextSkip = skipCount + 1;
    setSkipCount(nextSkip);
    advanceAudit(auditIndex + 1, { pass: passCount, fail: failCount, skip: nextSkip });
  };

  const researchSteps = useMemo(() => (
    ['Setup', 'Scan', 'Review', 'Audit', 'Done'] as const
  ), []);

  const activeStepIndex = useMemo(() => {
    if (phase === 'seed_setup' || phase === 'idle') return 0;
    if (phase === 'scanning') return 1;
    if (phase === 'promote_prompt' || phase === 'promoting') return 2;
    if (phase === 'audit') return 3;
    if (phase === 'summary') return 4;
    if (phase === 'error') return 0;
    return 0;
  }, [phase]);

  const showSetupPanel = phase === 'idle' || phase === 'seed_setup' || phase === 'error';

  const viewScanCandidate = (index: number, enterFullscreen = true) => {
    const sample = scanCandidates[index];
    if (!sample) return;
    setScanCandidateIndex(index);
    publishResearchOverlays(scanCandidates, index);
    showSampleOnChart(sample, onViewOnChart, { enterFullscreen });
  };

  if (!bridge) {
    return (
      <div className="weeklyResearchFloat" aria-label="Weekly Research">
        <div className="weeklyResearchChip is-disabled">
          <span className="weeklyResearchChipTitle">Weekly Research</span>
          <span className="weeklyResearchChipStatus">Unavailable</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`weeklyResearchFloat${expanded ? ' is-expanded' : ''}`} aria-label="Weekly Research">
      <button
        type="button"
        className={`weeklyResearchChip${phase === 'error' ? ' is-error' : ''}${busy ? ' is-busy' : ''}`}
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        title="Open weekly research"
      >
        <span className="weeklyResearchChipTitle">Research</span>
        <span className={`weeklyResearchChipDot${phase === 'error' ? ' is-error' : ''}${busy ? ' is-busy' : ''}${phase === 'seed_setup' ? ' is-warn' : ''}${phase === 'summary' ? ' is-ok' : ''}`} aria-hidden="true" />
        <span className="weeklyResearchChipStatus">{chipStatus}</span>
        <span className="weeklyResearchChipCaret">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded ? (
        <>
          <aside className="weeklyResearchDrawer" role="dialog" aria-label="Weekly research panel">
            <div className="weeklyResearchDrawerHeader">
              <div>
                <b>Weekly Research</b>
                <span>{symbol} · 2025 · W1</span>
              </div>
              <button type="button" className="weeklyResearchClose" onClick={() => setExpanded(false)} aria-label="Close">×</button>
            </div>
            <div className="weeklyResearchStepper" aria-label="Research progress">
              {researchSteps.map((label, index) => (
                <span
                  key={label}
                  className={`weeklyResearchStep${index === activeStepIndex ? ' is-active' : ''}${index < activeStepIndex ? ' is-done' : ''}`}
                >
                  {label}
                </span>
              ))}
            </div>

            <div className="weeklyResearchDrawerBody">
              {showSetupPanel ? (
                <LocalResearchDatabasePanel
                  symbol={symbol}
                  timeframe="W1"
                  onStatusChange={setDatabaseStatus}
                />
              ) : null}
              <p className="weeklyResearchStatusLine">{statusLine}</p>

              {phase === 'error' && (
                <div className="weeklyResearchErrorBlock">
                  <div className="weeklyResearchErrorLine">
                    Research failed —{' '}
                    <details className="weeklyResearchErrorDetails">
                      <summary>Details</summary>
                      <pre>{errorDetails || errorSummary || 'No details available.'}</pre>
                    </details>
                  </div>
                  <button type="button" onClick={resetWorkflow}>Start over</button>
                </div>
              )}

              {phase === 'idle' && (
                <>
                  <button type="button" className="primaryBtn" disabled={busy || !databaseReady} onClick={() => void runWeeklyResearch()}>
                    Run Weekly Research
                  </button>
                  <p className="mutedSmall">
                    Uses the trusted Review Candidate replay detector (RANGE_V2). Set W1 seed on chart or activate a manual seed in Advanced.
                  </p>
                </>
              )}

              {phase === 'seed_setup' && seedSetupView === 'prompt' && (
                <div className="weeklyResearchStatsRow">
                  <p className="weeklyResearchWarnLine">Optional manual seed override</p>
                  <p className="mutedSmall">
                    Normal scans bootstrap from candles only. Set a manual W1 seed only if you enable Advanced override.
                  </p>
                  <div className="weeklyResearchActionRow">
                    <button
                      type="button"
                      className="primaryBtn"
                      disabled={busy || !visibleWeeklySeed}
                      onClick={() => void useVisibleSeed()}
                      title={visibleWeeklySeed
                        ? `RH ${visibleWeeklySeed.rangeHigh} · RL ${visibleWeeklySeed.rangeLow}`
                        : 'Set W1 RH/RL on the chart first'}
                    >
                      Use visible RH/RL as seed
                    </button>
                    <button type="button" disabled={busy} onClick={() => void openSeedPicker()}>
                      Choose existing range
                    </button>
                    <button type="button" disabled={busy} onClick={cancelSeedSetup}>Cancel</button>
                  </div>
                  {visibleWeeklySeed ? (
                    <p className="mutedSmall">
                      W1 chart anchors: RH {visibleWeeklySeed.rangeHigh} · RL {visibleWeeklySeed.rangeLow}
                    </p>
                  ) : (
                    <p className="mutedSmall">Switch to W1 on the chart and set RH/RL to use visible anchors.</p>
                  )}
                </div>
              )}

              {phase === 'seed_setup' && seedSetupView === 'pick_list' && (
                <div className="weeklyResearchStatsRow">
                  <p className="mutedSmall">Select a W1 range to activate as the weekly seed.</p>
                  {seedRanges.length === 0 ? (
                    <p className="weeklyResearchWarnLine">No W1 ranges in the local database yet.</p>
                  ) : (
                    <div className="weeklyResearchSeedList">
                      {seedRanges.map((row) => (
                        <button
                          key={row.id}
                          type="button"
                          className="weeklyResearchSeedItem"
                          disabled={busy || !row.selectable}
                          onClick={() => void selectExistingSeed(row.id)}
                        >
                          <span>#{row.id} · {row.status || 'UNKNOWN'}</span>
                          <span>
                            RH {row.range_high_price ?? '—'} · RL {row.range_low_price ?? '—'}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="weeklyResearchActionRow">
                    <button type="button" disabled={busy} onClick={() => setSeedSetupView('prompt')}>Back</button>
                    <button type="button" disabled={busy} onClick={cancelSeedSetup}>Cancel</button>
                  </div>
                </div>
              )}

              {phase === 'scanning' && <p className="mutedSmall">Working… this may take a minute.</p>}

              {phase === 'promote_prompt' && scanSummary && (
                <div className="weeklyResearchStatsRow">
                  <div className="weeklyResearchStat"><span>Ranges found</span><strong>{scanSummary.rangesFound}</strong></div>
                  <div className="weeklyResearchStat"><span>No valid range</span><strong>{scanSummary.noValidRange}</strong></div>
                  <div className="weeklyResearchStat"><span>Candles scanned</span><strong>{scanSummary.candlesScanned}</strong></div>
                  {scanSummary.rangesFound === 0 ? (
                    <>
                      <p className="weeklyResearchWarnLine">
                        {zeroRangeScanMessage(scanSummary, scanDiagnose)}
                      </p>
                      {formatLifecycleCounts(scanDiagnose?.lifecycleStateCounts) ? (
                        <p className="mutedSmall">
                          Lifecycle mix: {formatLifecycleCounts(scanDiagnose?.lifecycleStateCounts)}
                        </p>
                      ) : null}
                      {scanDiagnose?.closestWeek?.lifecycle_state ? (
                        <p className="mutedSmall">
                          Closest week: {scanDiagnose.closestWeek.lifecycle_state}
                          {scanDiagnose.closestWeek.replay_until_time
                            ? ` · replay to ${scanDiagnose.closestWeek.replay_until_time}`
                            : ''}
                          {scanDiagnose.closestWeek.reason_text
                            ? ` — ${scanDiagnose.closestWeek.reason_text}`
                            : ''}
                        </p>
                      ) : null}
                      <button type="button" onClick={resetWorkflow}>Start over</button>
                    </>
                  ) : (
                    <>
                      <p className="weeklyResearchWarnLine">
                        Review each range in the <b>Detector (D)</b> panel on the right — edit RH/RL, promote, or reject.
                      </p>
                      <div className="weeklyResearchActionRow">
                        <button type="button" className="primaryBtn" disabled={busy} onClick={() => void acceptPromote()}>Yes, promote all</button>
                        <button type="button" disabled={busy} onClick={declinePromote}>Not now</button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {phase === 'promoting' && <p className="mutedSmall">Promoting ranges…</p>}

              {phase === 'audit' && (
                <div className="weeklyResearchStatsRow">
                  <div className="weeklyResearchStat"><span>Audit</span><strong>{auditPosition} / {WEEKLY_RESEARCH_AUDIT_TARGET}</strong></div>
                  <div className="weeklyResearchStat"><span>Pass</span><strong>{passCount}</strong></div>
                  <div className="weeklyResearchStat"><span>Fail</span><strong>{failCount}</strong></div>
                  {currentSample ? (
                    <p className="mutedSmall">
                      RH {currentSample.rh ?? currentSample.range_high_price ?? '—'}
                      {' · '}
                      RL {currentSample.rl ?? currentSample.range_low_price ?? '—'}
                    </p>
                  ) : null}
                  <div className="weeklyResearchActionRow">
                    <button type="button" className="primaryBtn" disabled={busy || !currentSample} onClick={() => {
                      if (!currentSample) return;
                      publishResearchOverlays(auditSamples, auditIndex);
                      showSampleOnChart(currentSample, onViewOnChart, { enterFullscreen: true });
                    }}>Fullscreen chart</button>
                    <button type="button" className="approveBtn" disabled={busy} onClick={() => void onPass()}>Pass</button>
                    <button type="button" className="dangerTiny" disabled={busy} onClick={() => void onFail()}>Fail</button>
                    <button type="button" disabled={busy} onClick={onNext}>Next</button>
                  </div>
                </div>
              )}

              {phase === 'summary' && finalSummary && (
                <div className="weeklyResearchStatsRow">
                  <div className="weeklyResearchStat"><span>Ranges found</span><strong>{finalSummary.rangesFound}</strong></div>
                  <div className="weeklyResearchStat"><span>Promoted</span><strong>{finalSummary.promoted}</strong></div>
                  <div className="weeklyResearchStat"><span>Pass</span><strong>{finalSummary.pass}</strong></div>
                  <div className="weeklyResearchStat"><span>Fail</span><strong>{finalSummary.fail}</strong></div>
                  <div className="weeklyResearchStat"><span>Skipped</span><strong>{finalSummary.skipped}</strong></div>
                  <p className="mutedSmall">
                    {finalSummary.pass >= 18
                      ? 'Weekly research looks healthy.'
                      : 'Some ranges need another look before trusting this batch.'}
                  </p>
                  <button type="button" className="primaryBtn" onClick={resetWorkflow}>Run again</button>
                </div>
              )}

              <details className="weeklyResearchAdvanced">
                <summary>Advanced ▼</summary>
                <label className="weeklyResearchSeedlessToggle">
                  <input
                    type="checkbox"
                    checked={reviewedTruthSeed}
                    onChange={(e) => setReviewedTruthSeed(e.target.checked)}
                  />
                  Use reviewed truth as seed
                </label>
                <p className="mutedSmall">
                  Seeds from promoted APPROVED/EDITED map_ranges before each replay step when available.
                  Falls back to temporary in-scan candidate only when no promoted truth exists.
                </p>
                <label className="weeklyResearchSeedlessToggle">
                  <input
                    type="checkbox"
                    checked={experimentalChainMode}
                    onChange={(e) => setExperimentalChainMode(e.target.checked)}
                  />
                  Experimental chain mode — not default.
                </label>
                <p className="mutedSmall">
                  Candles-only bootstrap chain. Produces different results than Review Candidate; use for experiments only.
                </p>
                <label className="weeklyResearchSeedlessToggle">
                  <input
                    type="checkbox"
                    checked={manualSeedOverride}
                    onChange={(e) => setManualSeedOverride(e.target.checked)}
                  />
                  Use manual ACTIVE seed override (legacy strict mode)
                </label>
                <div className="weeklyResearchActionRow">
                  <button type="button" disabled={busy} onClick={() => void openManualSeedSetup()}>
                    Set optional manual seed
                  </button>
                </div>
                <LocalResearchControls compact seedPolicy={reviewedTruthSeed ? 'reviewed_truth_only' : undefined} />
              </details>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
