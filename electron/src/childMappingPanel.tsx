import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  auditSampleToViewTarget,
  auditSamplesToFocusedOverlays,
  type RangeAuditSample,
  type RangeAuditViewTarget,
  type ResearchChartOverlay,
} from './reviewCandidateClient';
import { getLocalResearchBridge } from './localResearchClient';
import { scanSummaryFromResult } from './localResearchWorkflow';
import {
  advanceChildCandidateIndex,
  candidateLabel,
  currentChildCandidate,
  loadChildScanCandidates,
  runChildHistoricalScan,
  scanSummaryMessage,
  type ChildMappingSession,
} from './childMappingWorkflow';
import type { GuidedMappingCursor } from './guidedMappingCursor';
import {
  filterCandidatesAfterCursor,
  formatGuidedCursorDate,
  formatGuidedParentEndDate,
} from './guidedMappingCursor';

type ChildSaveResult = {
  ok: boolean;
  rangeId?: string;
  rangeEndTime?: string | null;
  bosWarning?: string | null;
};

type Props = {
  symbol: string;
  session: ChildMappingSession;
  guidedCursor?: GuidedMappingCursor | null;
  onSessionChange: (session: ChildMappingSession) => void;
  onViewOnChart?: (target: RangeAuditViewTarget, opts?: { enterFullscreen?: boolean }) => void;
  onResearchOverlaysChange?: (overlays: ResearchChartOverlay[]) => void;
  onApplyCandidate: (sample: RangeAuditSample) => void;
  onManualCreate: () => void;
  onRequestSave: () => Promise<ChildSaveResult>;
  onSkipGap?: () => void;
  onParentComplete?: () => void;
  onNextChild?: () => void;
  onClose: () => void;
  setMessage: (msg: string) => void;
};

export function ChildMappingPanel({
  symbol,
  session,
  guidedCursor,
  onSessionChange,
  onViewOnChart,
  onResearchOverlaysChange,
  onApplyCandidate,
  onManualCreate,
  onRequestSave,
  onSkipGap,
  onParentComplete,
  onNextChild,
  onClose,
  setMessage,
}: Props) {
  const bridge = getLocalResearchBridge();
  const [busy, setBusy] = useState(false);
  const [statusLine, setStatusLine] = useState('Preparing child mapping…');
  const scanStartedRef = useRef(false);

  useEffect(() => {
    scanStartedRef.current = false;
  }, [session.parentRangeId, session.detectionRunId]);

  const current = currentChildCandidate(session);
  const position = session.candidates.length
    ? `${Math.min(session.candidateIndex + 1, session.candidates.length)} / ${session.candidates.length}`
    : '0 / 0';

  const publishOverlays = useCallback((rows: RangeAuditSample[], activeIndex: number) => {
    if (!onResearchOverlaysChange) return;
    onResearchOverlaysChange(auditSamplesToFocusedOverlays(rows, activeIndex, { includePrior: false }));
  }, [onResearchOverlaysChange]);

  const showCandidateOnChart = useCallback((sample: RangeAuditSample | null, jump = true) => {
    if (!sample || !onViewOnChart) return;
    const target = auditSampleToViewTarget(sample);
    if (target) onViewOnChart(target, { enterFullscreen: jump });
  }, [onViewOnChart]);

  const runDiscovery = useCallback(async () => {
    if (!bridge) {
      setStatusLine('Local research bridge unavailable — use Manual Create.');
      onSessionChange({ ...session, phase: 'reviewing', candidates: [] });
      return;
    }
    setBusy(true);
    setStatusLine(`Scanning ${session.childLayer} inside parent window…`);
    onSessionChange({ ...session, phase: 'scanning' });
    try {
      const dbStatus = await bridge.getDatabaseStatus({ symbol, timeframe: session.childSourceTf });
      const databasePath = dbStatus.databasePath;
      const { dateFrom, dateTo } = session.researchWindow;
      if (!dateFrom || !dateTo) {
        setStatusLine('Parent window dates missing — use Manual Create.');
        onSessionChange({ ...session, phase: 'reviewing', candidates: [] });
        return;
      }
      const scanResult = await runChildHistoricalScan({
        symbol,
        childLayer: session.childLayer,
        childSourceTf: session.childSourceTf,
        dateFrom,
        dateTo,
        databasePath,
      });
      const summary = scanSummaryFromResult(scanResult);
      const runId = summary?.detectionRunId || null;
      if (!scanResult.ok || !runId) {
        setStatusLine(scanSummaryMessage(summary, session.childLayer));
        onSessionChange({
          ...session,
          phase: 'reviewing',
          detectionRunId: runId,
          candidates: [],
          candidateIndex: 0,
        });
        setMessage(`Child scan: ${scanResult.error || scanResult.stderr || 'no run id'}`);
        return;
      }
      const loaded = await loadChildScanCandidates({
        symbol,
        childLayer: session.childLayer,
        childSourceTf: session.childSourceTf,
        detectionRunId: runId,
        databasePath,
      });
      const rawCandidates = loaded.samples;
      const candidates = guidedCursor?.active
        ? filterCandidatesAfterCursor(rawCandidates, guidedCursor.cursor_time_ms)
        : rawCandidates;
      const nextSession: ChildMappingSession = {
        ...session,
        detectionRunId: runId,
        candidates,
        candidateIndex: 0,
        phase: candidates.length ? 'reviewing' : 'done',
      };
      onSessionChange(nextSession);
      publishOverlays(candidates, 0);
      const line = scanSummaryMessage(summary, session.childLayer);
      setStatusLine(line);
      setMessage(line);
      if (candidates[0]) showCandidateOnChart(candidates[0], true);
    } finally {
      setBusy(false);
    }
  }, [
    bridge,
    onSessionChange,
    publishOverlays,
    session,
    setMessage,
    showCandidateOnChart,
    guidedCursor,
    symbol,
  ]);

  useEffect(() => {
    if (session.phase !== 'scanning' || scanStartedRef.current) return;
    scanStartedRef.current = true;
    if (session.candidates.length > 0) {
      setStatusLine(`Restored ${session.candidates.length} ${session.childLayer} candidate(s) from session.`);
      return;
    }
    void runDiscovery();
  }, [session.phase, session.candidates.length, runDiscovery]);

  const jumpToIndex = (nextIndex: number) => {
    const safe = Math.min(Math.max(0, nextIndex), Math.max(0, session.candidates.length - 1));
    const next = { ...session, candidateIndex: safe, phase: 'reviewing' as const };
    onSessionChange(next);
    publishOverlays(next.candidates, safe);
    showCandidateOnChart(next.candidates[safe] || null, false);
  };

  const afterDecision = (nextSession: ChildMappingSession) => {
    onSessionChange(nextSession);
    if (nextSession.phase === 'done') {
      setStatusLine('Child mapping pass complete — continue manually or close.');
      onResearchOverlaysChange?.([]);
      return;
    }
    publishOverlays(nextSession.candidates, nextSession.candidateIndex);
    showCandidateOnChart(nextSession.candidates[nextSession.candidateIndex] || null, true);
  };

  const handleApproveAndSave = async () => {
    if (!current) return;
    setBusy(true);
    try {
      onApplyCandidate(current);
      const result = await onRequestSave();
      if (!result.ok) return;
      setMessage(`Saved ${session.childLayer} under parent #${session.parentRangeId}.`);
      if (result.bosWarning) setMessage(result.bosWarning);
      if (guidedCursor?.active && onNextChild) {
        onNextChild();
        return;
      }
      afterDecision(advanceChildCandidateIndex(session));
    } finally {
      setBusy(false);
    }
  };

  const handleManualSaveWithBos = async () => {
    setBusy(true);
    try {
      const result = await onRequestSave();
      if (!result.ok) return;
      setMessage(`Saved manual ${session.childLayer} under parent #${session.parentRangeId}.`);
      if (result.bosWarning) setMessage(result.bosWarning);
      if (guidedCursor?.active && onNextChild) {
        onNextChild();
        return;
      }
      afterDecision(advanceChildCandidateIndex(session));
    } finally {
      setBusy(false);
    }
  };

  const handleReject = () => {
    afterDecision(advanceChildCandidateIndex(session));
    setMessage('Candidate rejected — next.');
  };

  const handleManualCreate = () => {
    onManualCreate();
    setStatusLine('Manual create — set RH/RL on chart, then Save Range.');
    setMessage('Manual Daily create — parent linkage preserved.');
  };

  const parentRh = session.parentRange.range_high_price ?? session.parentRange.range_high;
  const parentRl = session.parentRange.range_low_price ?? session.parentRange.range_low;

  return (
    <section className="childMappingPanel">
      <div className="childMappingHeader">
        <b>Child mapping · {session.childLayer}</b>
        <span>Parent {session.parentLayer} #{session.parentRangeId}</span>
      </div>
      <div className="childMappingMeta">
        <span>Window {session.researchWindow.dateFrom || '—'} → {session.researchWindow.dateTo || '—'}</span>
        <span>Parent RH {String(parentRh ?? '—')} / RL {String(parentRl ?? '—')}</span>
      </div>
      {guidedCursor?.active && (
        <div className="guidedCursorInfo">
          <div><span>Parent</span><strong>{guidedCursor.active_parent_layer} #{guidedCursor.active_parent_range_id}</strong></div>
          <div><span>Child Layer</span><strong>{guidedCursor.active_child_layer}</strong></div>
          <div><span>Cursor</span><strong>{formatGuidedCursorDate(guidedCursor)}</strong></div>
          <div><span>Parent End</span><strong>{formatGuidedParentEndDate(guidedCursor)}</strong></div>
          <div><span>Status</span><strong>{guidedCursor.cursor_status}</strong></div>
          {guidedCursor.pending_bos && (
            <div><span>Pending BOS</span><strong>{guidedCursor.pending_bos.direction}</strong></div>
          )}
        </div>
      )}
      <div className="childMappingStatus">{statusLine}</div>
      {session.candidates.length > 0 && (
        <div className="childMappingCandidate">
          <div className="childMappingCandidateTitle">Candidate {position}</div>
          <div className="childMappingCandidateBody">{candidateLabel(current)}</div>
        </div>
      )}
      <div className="childMappingActions">
        <button type="button" disabled={busy || !current} onClick={() => void handleApproveAndSave()}>
          Approve &amp; Save
        </button>
        <button type="button" disabled={busy || !current} onClick={() => current && onApplyCandidate(current)}>
          Load to chart
        </button>
        <button type="button" disabled={busy || !current} onClick={handleReject}>
          Reject
        </button>
        <button type="button" disabled={busy} onClick={handleManualCreate}>
          Manual Create
        </button>
        {guidedCursor?.active && (
          <button type="button" disabled={busy} onClick={() => void handleManualSaveWithBos()}>
            Save Manual Range + BOS
          </button>
        )}
        {guidedCursor?.active && onSkipGap && (
          <button type="button" className="secondary" disabled={busy} onClick={onSkipGap}>
            Skip Gap
          </button>
        )}
        {guidedCursor?.active && onParentComplete && (
          <button type="button" className="secondary" disabled={busy} onClick={onParentComplete}>
            Parent Complete
          </button>
        )}
        {guidedCursor?.active && onNextChild && (
          <button type="button" disabled={busy || !current} onClick={onNextChild}>
            Next Child
          </button>
        )}
        <button type="button" disabled={busy || session.candidates.length < 2} onClick={() => jumpToIndex(session.candidateIndex + 1)}>
          Next
        </button>
        <button type="button" disabled={busy || session.candidateIndex <= 0} onClick={() => jumpToIndex(session.candidateIndex - 1)}>
          Prev
        </button>
        <button type="button" className="secondary" disabled={busy} onClick={() => void runDiscovery()}>
          Rescan
        </button>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
    </section>
  );
}
