import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  auditSamplesToFocusedOverlays,
  auditSampleToViewTarget,
  weekLabelFromSample,
  type RangeAuditSample,
  type RangeAuditViewTarget,
  type ResearchChartOverlay,
} from './reviewCandidateClient';
import {
  exportDetectionAuditLocalResearch,
  getLocalResearchBridge,
  listDetectorRunLocalResearch,
  reviewSuggestionLocalResearch,
  type LocalResearchRunResult,
} from './localResearchClient';
import { retracementPctDisplay } from './analystPresets';
import type { WeeklyResearchSession } from './weeklyResearchSession';

const ERROR_CATEGORIES = [
  'WRONG_RH',
  'WRONG_RL',
  'WRONG_BOS',
  'MAJOR_MINOR_ERROR',
  'WRONG_REF_CANDLE',
  'FALSE_SWING',
  'OTHER',
] as const;

type ChartAnchor = { price?: string; time?: string };

type Props = {
  symbol: string;
  structureLayer: string;
  sourceTimeframe: string;
  detectionRunId: string | null;
  weeklySession?: WeeklyResearchSession | null;
  onWeeklySessionChange?: (session: WeeklyResearchSession | null) => void;
  onDetectionRunIdChange?: (runId: string | null) => void;
  onViewOnChart?: (target: RangeAuditViewTarget, opts?: { enterFullscreen?: boolean }) => void;
  onResearchOverlaysChange?: (overlays: ResearchChartOverlay[]) => void;
  onPromoted?: () => void | Promise<void>;
  chartRh?: ChartAnchor;
  chartRl?: ChartAnchor;
  chartPickTick?: number;
  setMessage: (msg: string) => void;
};

type DraftEdits = { rh: string; rl: string };

function samplesFromListRunResult(result: LocalResearchRunResult): RangeAuditSample[] {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return [];
  const samples = (result.parsed as { samples?: RangeAuditSample[] }).samples;
  return Array.isArray(samples) ? samples : [];
}

function suggestionIdFromSample(sample: RangeAuditSample | null | undefined): string | null {
  if (!sample) return null;
  return sample.suggestion_id || (sample.source === 'suggestions' ? sample.id || null : null);
}

function statusBadgeClass(status?: string | null): string {
  const s = String(status || 'PENDING').toUpperCase();
  if (s === 'APPROVED') return 'is-approved';
  if (s === 'EDITED') return 'is-edited';
  if (s === 'REJECTED') return 'is-rejected';
  return 'is-pending';
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
  const priceText = price != null ? ` @ ${Number(price).toFixed(2)}` : '';
  return `Retracement ${cls || '—'} · ${retracementPctDisplay(pct ?? undefined)}${priceText}`;
}

function rememberDetectedBaseline(
  rows: RangeAuditSample[],
  store: Map<string, { rh: number; rl: number }>,
) {
  for (const row of rows) {
    const id = suggestionIdFromSample(row);
    if (!id || store.has(id)) continue;
    const meta = row.meta_json || {};
    const rh = Number(meta.detector_suggested_rh ?? row.rh ?? row.range_high_price);
    const rl = Number(meta.detector_suggested_rl ?? row.rl ?? row.range_low_price);
    if (!Number.isFinite(rh) || !Number.isFinite(rl)) continue;
    store.set(id, { rh, rl });
  }
}

function getDetectedBaseline(
  sample: RangeAuditSample | null,
  store: Map<string, { rh: number; rl: number }>,
): { rh: number; rl: number } | null {
  const id = suggestionIdFromSample(sample);
  if (id && store.has(id)) return store.get(id) || null;
  if (!sample) return null;
  const meta = sample.meta_json || {};
  const rh = Number(meta.detector_suggested_rh ?? sample.rh ?? sample.range_high_price);
  const rl = Number(meta.detector_suggested_rl ?? sample.rl ?? sample.range_low_price);
  if (!Number.isFinite(rh) || !Number.isFinite(rl)) return null;
  return { rh, rl };
}

function priceChanged(a: number, b: number): boolean {
  return Math.abs(a - b) > 0.001;
}

function inferErrorCategory(
  detected: { rh: number; rl: number },
  editedRh: number,
  editedRl: number,
): string {
  const rhChanged = priceChanged(detected.rh, editedRh);
  const rlChanged = priceChanged(detected.rl, editedRl);
  if (rhChanged && rlChanged) return 'WRONG_RH';
  if (rhChanged) return 'WRONG_RH';
  if (rlChanged) return 'WRONG_RL';
  return 'NO_ERROR';
}

function buildAutoEditNotes(
  detected: { rh: number; rl: number },
  editedRh: number,
  editedRl: number,
): string {
  const parts: string[] = [];
  if (priceChanged(detected.rh, editedRh)) parts.push(`RH ${detected.rh} → ${editedRh}`);
  if (priceChanged(detected.rl, editedRl)) parts.push(`RL ${detected.rl} → ${editedRl}`);
  return parts.join(' · ') || 'user corrected RH/RL';
}

function sampleToViewTarget(
  sample: RangeAuditSample,
  editRh: string,
  editRl: string,
): RangeAuditViewTarget | null {
  const base = auditSampleToViewTarget(sample);
  if (!base) return null;
  const rh = parseFloat(editRh);
  const rl = parseFloat(editRl);
  if (Number.isFinite(rh) && Number.isFinite(rl) && rh > rl) {
    return { ...base, rh, rl };
  }
  return base;
}

function patchSampleAfterReview(
  sample: RangeAuditSample,
  action: 'APPROVE' | 'EDIT' | 'REJECT',
  rh: number,
  rl: number,
  promotedRangeId?: number | null,
): RangeAuditSample {
  if (action === 'REJECT') {
    return { ...sample, status: 'REJECTED' };
  }
  return {
    ...sample,
    status: action === 'EDIT' ? 'EDITED' : 'APPROVED',
    rh,
    rl,
    range_high_price: rh,
    range_low_price: rl,
    promoted_range_id: promotedRangeId ?? sample.promoted_range_id,
  };
}

export function DetectorWorkspacePanel({
  symbol,
  structureLayer,
  sourceTimeframe,
  detectionRunId,
  weeklySession,
  onWeeklySessionChange,
  onDetectionRunIdChange,
  onViewOnChart,
  onResearchOverlaysChange,
  onPromoted,
  chartRh,
  chartRl,
  chartPickTick = 0,
  setMessage,
}: Props) {
  const bridge = getLocalResearchBridge();
  const [databasePath, setDatabasePath] = useState<string | undefined>();
  const [samples, setSamples] = useState<RangeAuditSample[]>([]);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editRh, setEditRh] = useState('');
  const [editRl, setEditRl] = useState('');
  const [rejectCategory, setRejectCategory] = useState<string>(ERROR_CATEGORIES[0]);
  const [rejectNotes, setRejectNotes] = useState('');
  const [filter, setFilter] = useState<'ALL' | 'PENDING' | 'REVIEWED'>('ALL');
  const [showPriorWeek, setShowPriorWeek] = useState(false);
  const loadedRunRef = useRef<string | null>(null);
  const detectedBaselineRef = useRef<Map<string, { rh: number; rl: number }>>(new Map());
  const draftEditsRef = useRef<Map<string, DraftEdits>>(new Map());
  const lastChartPickTickRef = useRef(0);

  const sessionLabel = weeklySession?.label || `${symbol} · 2025 · W1`;
  const loadedRunId = weeklySession?.detectionRunId || detectionRunId;
  const current = samples[index] || null;
  const detectedBaseline = getDetectedBaseline(current, detectedBaselineRef.current);

  useEffect(() => {
    if (!bridge) return;
    void bridge.getDatabaseStatus({ symbol, timeframe: sourceTimeframe }).then((status) => {
      if (status.ok && status.databasePath) setDatabasePath(status.databasePath);
    });
  }, [bridge, symbol, sourceTimeframe]);

  const loadEditsForSample = useCallback((sample: RangeAuditSample | null) => {
    if (!sample) {
      setEditRh('');
      setEditRl('');
      return;
    }
    const id = suggestionIdFromSample(sample);
    const draft = id ? draftEditsRef.current.get(id) : null;
    if (draft) {
      setEditRh(draft.rh);
      setEditRl(draft.rl);
      return;
    }
    setEditRh(String(sample.rh ?? sample.range_high_price ?? ''));
    setEditRl(String(sample.rl ?? sample.range_low_price ?? ''));
  }, []);

  const persistCurrentDraft = useCallback(() => {
    const sample = samples[index];
    const id = suggestionIdFromSample(sample);
    if (!id || !editRh.trim() || !editRl.trim()) return;
    draftEditsRef.current.set(id, { rh: editRh, rl: editRl });
  }, [samples, index, editRh, editRl]);

  const publishOverlays = useCallback((rows: RangeAuditSample[], activeIndex: number, rhText?: string, rlText?: string) => {
    if (!onResearchOverlaysChange) return;
    const overlays = auditSamplesToFocusedOverlays(rows, activeIndex, { includePrior: showPriorWeek });
    const rh = parseFloat(rhText ?? '');
    const rl = parseFloat(rlText ?? '');
    if (overlays.length && Number.isFinite(rh) && Number.isFinite(rl) && rh > rl) {
      const active = overlays[overlays.length - 1];
      active.high = rh;
      active.low = rl;
    }
    onResearchOverlaysChange(overlays);
  }, [onResearchOverlaysChange, showPriorWeek]);

  const syncSession = useCallback((
    rows: RangeAuditSample[],
    nextIndex: number,
  ) => {
    if (!weeklySession || !onWeeklySessionChange) return;
    onWeeklySessionChange({
      ...weeklySession,
      samples: rows,
      reviewIndex: nextIndex,
    });
  }, [onWeeklySessionChange, weeklySession]);

  const jumpToIndex = useCallback((
    rows: RangeAuditSample[],
    nextIndex: number,
    jumpChart = false,
  ) => {
    const safeIndex = Math.min(Math.max(0, nextIndex), Math.max(0, rows.length - 1));
    setIndex(safeIndex);
    const active = rows[safeIndex] || null;
    loadEditsForSample(active);
    syncSession(rows, safeIndex);
    if (jumpChart && active && onViewOnChart) {
      const id = suggestionIdFromSample(active);
      const draft = id ? draftEditsRef.current.get(id) : null;
      const target = sampleToViewTarget(active, draft?.rh ?? String(active.rh ?? ''), draft?.rl ?? String(active.rl ?? ''));
      if (target) onViewOnChart(target, { enterFullscreen: true });
    }
  }, [loadEditsForSample, onViewOnChart, syncSession]);

  const applySamples = useCallback((
    rows: RangeAuditSample[],
    startIndex = 0,
    jumpChart = false,
  ) => {
    rememberDetectedBaseline(rows, detectedBaselineRef.current);
    setSamples(rows);
    jumpToIndex(rows, startIndex, jumpChart);
  }, [jumpToIndex]);

  useEffect(() => {
    if (!samples.length) return;
    publishOverlays(samples, index, editRh, editRl);
  }, [showPriorWeek, samples, index, editRh, editRl, publishOverlays]);

  useEffect(() => {
    if (!chartPickTick || chartPickTick === lastChartPickTickRef.current) return;
    lastChartPickTickRef.current = chartPickTick;
    const nextRh = chartRh?.price || '';
    const nextRl = chartRl?.price || '';
    if (nextRh) setEditRh(nextRh);
    if (nextRl) setEditRl(nextRl);
    const id = suggestionIdFromSample(current);
    if (id) {
      draftEditsRef.current.set(id, {
        rh: nextRh || editRh,
        rl: nextRl || editRl,
      });
    }
  }, [chartPickTick, chartRh?.price, chartRl?.price, current, editRh, editRl]);

  const refreshFromRun = useCallback(async (runId: string, opts?: { jumpChart?: boolean; keepIndex?: number }) => {
    if (!bridge || !runId) return;
    setLoading(true);
    try {
      const result = await listDetectorRunLocalResearch({
        symbol,
        structureLayer,
        sourceTimeframe,
        detectionRunId: runId,
        databasePath,
      });
      const rows = samplesFromListRunResult(result);
      if (!result.ok) {
        setMessage(`Could not reload ranges: ${result.error || result.stderr || 'unknown'}`);
        return;
      }
      loadedRunRef.current = runId;
      const keepIndex = typeof opts?.keepIndex === 'number' ? opts.keepIndex : index;
      applySamples(rows, keepIndex, opts?.jumpChart === true);
      syncSession(rows, keepIndex);
    } finally {
      setLoading(false);
    }
  }, [
    applySamples,
    bridge,
    databasePath,
    index,
    setMessage,
    sourceTimeframe,
    structureLayer,
    symbol,
    syncSession,
  ]);

  useEffect(() => {
    if (!weeklySession?.detectionRunId || !weeklySession.samples.length) return;
    const runId = weeklySession.detectionRunId;
    if (loadedRunRef.current === runId) return;
    loadedRunRef.current = runId;
    onDetectionRunIdChange?.(runId);
    applySamples(weeklySession.samples, weeklySession.reviewIndex ?? 0, false);
  }, [weeklySession?.detectionRunId, weeklySession?.samples, weeklySession?.reviewIndex, applySamples, onDetectionRunIdChange]);

  const filteredSamples = useMemo(() => {
    if (filter === 'ALL') return samples;
    if (filter === 'PENDING') {
      return samples.filter((s) => !s.status || String(s.status).toUpperCase() === 'PENDING');
    }
    return samples.filter((s) => {
      const st = String(s.status || '').toUpperCase();
      return st && st !== 'PENDING';
    });
  }, [samples, filter]);

  const navigate = (delta: number) => {
    persistCurrentDraft();
    const pool = filteredSamples.length ? filteredSamples : samples;
    if (!pool.length) return;
    const key = suggestionIdFromSample(current);
    const pos = pool.findIndex((s) => suggestionIdFromSample(s) === key);
    const start = pos >= 0 ? pos : 0;
    const nextPos = (start + delta + pool.length) % pool.length;
    const nextSample = pool[nextPos];
    const fullIndex = samples.findIndex((s) => suggestionIdFromSample(s) === suggestionIdFromSample(nextSample));
    jumpToIndex(samples, fullIndex >= 0 ? fullIndex : 0, true);
  };

  const goToNextAfterSave = useCallback((rows: RangeAuditSample[]) => {
    const pool = filter === 'PENDING'
      ? rows.filter((s) => !s.status || String(s.status).toUpperCase() === 'PENDING')
      : filter === 'REVIEWED'
        ? rows.filter((s) => {
          const st = String(s.status || '').toUpperCase();
          return st && st !== 'PENDING';
        })
        : rows;
    const currentId = suggestionIdFromSample(current);
    const pos = pool.findIndex((s) => suggestionIdFromSample(s) === currentId);
    if (pool.length <= 1) return;
    const nextPos = pos >= 0 ? (pos + 1) % pool.length : 0;
    const nextSample = pool[nextPos];
    const fullIndex = rows.findIndex((s) => suggestionIdFromSample(s) === suggestionIdFromSample(nextSample));
    jumpToIndex(rows, fullIndex >= 0 ? fullIndex : 0, true);
  }, [current, filter, jumpToIndex]);

  const submitReview = async (action: 'APPROVE' | 'EDIT' | 'REJECT' | 'SMART_SAVE') => {
    const suggestionId = suggestionIdFromSample(current);
    if (!suggestionId || !bridge || !loadedRunId || !current) return;
    const baseline = getDetectedBaseline(current, detectedBaselineRef.current);
    if (!baseline) {
      setMessage('Could not read detected RH/RL for this week.');
      return;
    }

    const rh = parseFloat(editRh);
    const rl = parseFloat(editRl);
    if (!Number.isFinite(rh) || !Number.isFinite(rl) || rh <= rl) {
      setMessage('Set valid RH and RL — high must be above low.');
      return;
    }

    let finalAction: 'APPROVE' | 'EDIT' | 'REJECT' = action === 'SMART_SAVE'
      ? (priceChanged(baseline.rh, rh) || priceChanged(baseline.rl, rl) ? 'EDIT' : 'APPROVE')
      : action;

    if (finalAction === 'EDIT' && !priceChanged(baseline.rh, rh) && !priceChanged(baseline.rl, rl)) {
      finalAction = 'APPROVE';
    }

    setBusy(true);
    try {
      const errorCategory = finalAction === 'REJECT'
        ? rejectCategory
        : finalAction === 'EDIT'
          ? inferErrorCategory(baseline, rh, rl)
          : undefined;
      const notes = finalAction === 'REJECT'
        ? rejectNotes
        : finalAction === 'EDIT'
          ? buildAutoEditNotes(baseline, rh, rl)
          : '';

      const result = await reviewSuggestionLocalResearch({
        suggestionId,
        action: finalAction,
        edits: finalAction === 'EDIT'
          ? { suggested_rh: rh, suggested_rl: rl, range_scale: 'UNKNOWN' }
          : finalAction === 'APPROVE'
            ? { range_scale: 'UNKNOWN' }
            : undefined,
        errorCategory,
        notes,
        databasePath,
      });
      const parsed = result.parsed as Record<string, unknown> | undefined;
      if (!result.ok || parsed?.ok === false) {
        setMessage(`Review failed: ${result.error || String(parsed?.error || 'unknown')}`);
        return;
      }

      draftEditsRef.current.delete(suggestionId);
      const nextSamples = samples.map((row, i) => (
        i === index
          ? patchSampleAfterReview(
            row,
            finalAction,
            rh,
            rl,
            typeof parsed?.promoted_range_id === 'number' ? parsed.promoted_range_id : null,
          )
          : row
      ));
      setSamples(nextSamples);

      if (finalAction === 'REJECT') {
        setMessage(`Rejected · week ${weekLabelFromSample(current)}`);
      } else if (finalAction === 'EDIT') {
        setMessage(`Saved correction (${errorCategory}) · ${weekLabelFromSample(current)}`);
      } else {
        setMessage(`Promoted · week ${weekLabelFromSample(current)}${parsed?.promoted_range_id ? ` → #${parsed.promoted_range_id}` : ''}`);
      }

      goToNextAfterSave(nextSamples);
    } finally {
      setBusy(false);
    }
  };

  const exportAudit = async () => {
    if (!loadedRunId || !bridge) return;
    setBusy(true);
    try {
      const result = await exportDetectionAuditLocalResearch({
        symbol,
        structureLayer,
        sourceTimeframe,
        detectionRunId: loadedRunId,
        databasePath,
      });
      const payload = result.parsed ?? (result.stdout ? JSON.parse(result.stdout) : null);
      if (!result.ok || !payload) {
        setMessage(`Export failed: ${result.error || result.stderr || 'unknown'}`);
        return;
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `detection_audit_${symbol}_2025_${loadedRunId.slice(0, 8)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage(`Exported audit JSON · ${samples.length} ranges`);
    } finally {
      setBusy(false);
    }
  };

  if (!bridge) {
    return <div className="detectorWorkspacePanel"><p className="mutedSmall">Local detector unavailable.</p></div>;
  }

  const pendingCount = samples.filter((s) => !s.status || String(s.status).toUpperCase() === 'PENDING').length;
  const scanMeta = weeklySession?.summary;
  const editedRh = parseFloat(editRh);
  const editedRl = parseFloat(editRl);
  const hasValidEdits = Number.isFinite(editedRh) && Number.isFinite(editedRl) && editedRh > editedRl;
  const rhChanged = !!(detectedBaseline && hasValidEdits && priceChanged(detectedBaseline.rh, editedRh));
  const rlChanged = !!(detectedBaseline && hasValidEdits && priceChanged(detectedBaseline.rl, editedRl));
  const hasCorrections = rhChanged || rlChanged;

  return (
    <div className="detectorWorkspacePanel rightTabPanel">
      <div className="detectorWorkspaceHeader">
        <h3>Weekly Research · {sessionLabel}</h3>
        {scanMeta ? (
          <p className="detectorStatusLine">
            {scanMeta.rangesFound} ranges found · {scanMeta.candlesScanned} weeks scanned · {scanMeta.noValidRange} no-valid-range
          </p>
        ) : (
          <p className="detectorStatusLine">Run Research → scan 2025, then review each range here.</p>
        )}
      </div>

      <div className="detectorStatsRow">
        <div className="detectorStat"><span>Ranges</span><strong>{samples.length}</strong></div>
        <div className="detectorStat"><span>Review</span><strong>{samples.length ? `${index + 1} / ${samples.length}` : '—'}</strong></div>
        <div className="detectorStat"><span>Pending</span><strong>{pendingCount}</strong></div>
      </div>

      <div className="detectorFilterRow">
        <button type="button" className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>All</button>
        <button type="button" className={filter === 'PENDING' ? 'active' : ''} onClick={() => setFilter('PENDING')}>Pending</button>
        <button type="button" className={filter === 'REVIEWED' ? 'active' : ''} onClick={() => setFilter('REVIEWED')}>Reviewed</button>
        <button type="button" disabled={busy || loading || !loadedRunId} onClick={() => loadedRunId && void refreshFromRun(loadedRunId)}>Refresh</button>
      </div>

      {loading ? <p className="mutedSmall">Loading…</p> : null}
      {busy ? <p className="mutedSmall detectorSavingHint">Saving…</p> : null}

      {!loading && !samples.length ? (
        <p className="detectorEmptyHint">No ranges loaded. Toolbar → <b>Research</b> → Run Weekly Research.</p>
      ) : null}

      {current ? (
        <div className="detectorRectifyBlock">
          <h4>Fix incorrect detection</h4>
          <p className="mutedSmall">
            Week <b>{weekLabelFromSample(current)}</b>
            {' · '}
            <span className={`detectorStatusBadge ${statusBadgeClass(current.status as string)}`}>
              {String(current.status || 'PENDING')}
            </span>
          </p>
          {detectedBaseline ? (
            <p className="detectorCandidatePrices">
              Detected RH {detectedBaseline.rh} · RL {detectedBaseline.rl}
            </p>
          ) : null}
          {hasCorrections ? (
            <p className="detectorAutoNote mutedSmall">
              Auto-note: {rhChanged ? 'WRONG_RH' : ''}{rhChanged && rlChanged ? ' · ' : ''}{rlChanged ? 'WRONG_RL' : ''}
            </p>
          ) : null}
          {formatRetracementLine(current) ? (
            <p className="weeklyResearchRetracementLine">{formatRetracementLine(current)}</p>
          ) : null}

          <p className="mutedSmall detectorChartPickHint">
            Click a candle on chart → toolbar <b>RH</b> / <b>RL</b>, or type below.
          </p>

          <div className="detectorEditGrid">
            <label className={rhChanged ? 'is-changed' : ''}>
              Correct RH
              <input value={editRh} disabled={busy} onChange={(e) => setEditRh(e.target.value)} />
            </label>
            <label className={rlChanged ? 'is-changed' : ''}>
              Correct RL
              <input value={editRl} disabled={busy} onChange={(e) => setEditRl(e.target.value)} />
            </label>
          </div>

          <div className="weeklyResearchActionRow detectorActionRow">
            <button type="button" disabled={busy || samples.length < 2} onClick={() => navigate(-1)}>Prev</button>
            <button type="button" className="primaryBtn" disabled={busy} onClick={() => {
              persistCurrentDraft();
              const target = sampleToViewTarget(current, editRh, editRl);
              if (target && onViewOnChart) onViewOnChart(target, { enterFullscreen: true });
            }}>Fullscreen chart</button>
            <button type="button" disabled={busy || samples.length < 2} onClick={() => navigate(1)}>Next</button>
          </div>

          <div className="detectorRectifyActions">
            <button
              type="button"
              className="primaryBtn detectorSaveNextBtn"
              disabled={busy || !hasValidEdits}
              onClick={() => void submitReview('SMART_SAVE')}
            >
              {busy ? 'Saving…' : hasCorrections ? 'Save correction & Next' : 'Promote & Next'}
            </button>
            <button type="button" className="rejectBtn" disabled={busy} onClick={() => void submitReview('REJECT')}>
              ✗ Reject wrong range
            </button>
          </div>

          <div className="detectorActionRow">
            <select value={rejectCategory} disabled={busy} onChange={(e) => setRejectCategory(e.target.value)} aria-label="Why wrong">
              {ERROR_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input
              className="detectorRejectNotes"
              value={rejectNotes}
              disabled={busy}
              onChange={(e) => setRejectNotes(e.target.value)}
              placeholder="Notes for reject (optional)"
            />
          </div>
        </div>
      ) : null}

      <div className="detectorExportRow">
        <button type="button" className="primaryBtn" disabled={busy || !loadedRunId || !samples.length} onClick={() => void exportAudit()}>
          Export audit JSON
        </button>
      </div>

      {samples.length > 0 ? (
        <div className="detectorRangeListSection">
          <label className="detectorOverlayToggle">
            <input
              type="checkbox"
              checked={showPriorWeek}
              disabled={index === 0}
              onChange={(e) => setShowPriorWeek(e.target.checked)}
            />
            Compare with prior week (2 lines on chart)
          </label>
          <p className="mutedSmall detectorListHint">Click a week to load candles and review RH/RL.</p>
          <div className="detectorRangeList">
            {samples.map((row, i) => (
              <button
                key={suggestionIdFromSample(row) || `row-${i}`}
                type="button"
                className={`detectorRangeListItem${i === index ? ' active' : ''} ${statusBadgeClass(row.status as string)}`}
                onClick={() => {
                  persistCurrentDraft();
                  jumpToIndex(samples, i, true);
                }}
              >
                <span>{i + 1}. {weekLabelFromSample(row)}</span>
                <span>RH {row.rh ?? '—'} · RL {row.rl ?? '—'}</span>
                <span>{row.status || 'PENDING'}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
