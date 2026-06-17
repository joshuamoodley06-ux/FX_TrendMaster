import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  type DetectorSuggestionRow,
  type ReviewAction,
  type ReviewEdits,
  fetchPendingSuggestions,
  reviewSuggestion,
  runDetectorV1,
} from './reviewCandidateClient';

type Props = {
  apiBase: string;
  symbol: string;
  structureLayer: string;
  sourceTimeframe: string;
  parentRangeId?: number | null;
  activeRangeId?: number | null;
  caseRef?: string | null;
  rangeHigh?: number | null;
  rangeLow?: number | null;
  rangeScale?: string;
  rangeRole?: string | null;
  activeCandleTimeMs?: number | null;
  activeCandleTimeLabel?: string | null;
  replayMode?: boolean;
  onPromoted?: () => void | Promise<void>;
  setMessage: (msg: string) => void;
};

type DisplayMode = 'collapsed' | 'compact' | 'expanded';

const ERROR_CATEGORIES = [
  'WRONG_RH',
  'WRONG_RL',
  'WRONG_BOS',
  'MAJOR_MINOR_ERROR',
  'WRONG_REF_CANDLE',
  'FALSE_SWING',
  'OTHER',
] as const;

function isRangeKind(kind: string) {
  return kind === 'RANGE_MAJOR' || kind === 'RANGE_MINOR';
}

function fmtTime(ms?: number | null) {
  if (!ms) return '—';
  try {
    return new Date(ms).toISOString().replace('T', ' ').slice(0, 19);
  } catch {
    return String(ms);
  }
}

function fmtContextDate(ms?: number | null) {
  if (!ms) return null;
  try {
    return new Date(ms).toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

function candidatePriceLabel(row: DetectorSuggestionRow) {
  if (isRangeKind(row.candidate_kind)) {
    return `RH ${row.suggested_rh ?? '—'} / RL ${row.suggested_rl ?? '—'}`;
  }
  return `${row.event_side || '—'} @ ${row.event_price ?? '—'}`;
}

function metaMatchesContext(
  row: DetectorSuggestionRow,
  detectionRunId: string | null,
  replayUntilMs: number | null,
) {
  const meta = row.meta_json || {};
  if (detectionRunId) {
    return meta.detection_run_id === detectionRunId;
  }
  if (replayUntilMs != null && replayUntilMs > 0) {
    return Number(meta.replay_until_time_ms) === replayUntilMs;
  }
  return false;
}

function newDetectionRunId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ReviewCandidatePanel(props: Props) {
  const [displayMode, setDisplayMode] = useState<DisplayMode>('collapsed');
  const [suggestions, setSuggestions] = useState<DetectorSuggestionRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningDetector, setRunningDetector] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rejectCategory, setRejectCategory] = useState<string>('OTHER');
  const [rejectNotes, setRejectNotes] = useState('');
  const [editRh, setEditRh] = useState('');
  const [editRl, setEditRl] = useState('');
  const [editScale, setEditScale] = useState('MAJOR');
  const [editRole, setEditRole] = useState('');
  const [editEventPrice, setEditEventPrice] = useState('');
  const [lastDetectionRunId, setLastDetectionRunId] = useState<string | null>(null);
  const [contextReplayUntilMs, setContextReplayUntilMs] = useState<number | null>(null);
  const [contextLabel, setContextLabel] = useState<string | null>(null);
  const [lastDebugSummary, setLastDebugSummary] = useState<Record<string, unknown> | null>(null);

  const selected = useMemo(
    () => suggestions.find(s => s.suggestion_id === selectedId) || null,
    [suggestions, selectedId],
  );

  const syncEditFields = useCallback((row: DetectorSuggestionRow | null) => {
    if (!row) return;
    setEditRh(row.suggested_rh != null ? String(row.suggested_rh) : '');
    setEditRl(row.suggested_rl != null ? String(row.suggested_rl) : '');
    setEditScale(String(row.range_scale || props.rangeScale || 'MAJOR'));
    setEditRole(String(row.range_role || ''));
    setEditEventPrice(row.event_price != null ? String(row.event_price) : '');
  }, [props.rangeScale]);

  const filterRows = useCallback(
    (rows: DetectorSuggestionRow[]) => {
      if (!lastDetectionRunId && !(contextReplayUntilMs != null && contextReplayUntilMs > 0)) {
        return rows.filter(r => {
          const meta = r.meta_json || {};
          return !meta.detection_run_id && !meta.replay_until_time_ms;
        });
      }
      return rows.filter(r => metaMatchesContext(r, lastDetectionRunId, contextReplayUntilMs));
    },
    [lastDetectionRunId, contextReplayUntilMs],
  );

  useEffect(() => {
    if (
      contextReplayUntilMs != null
      && props.activeCandleTimeMs != null
      && props.activeCandleTimeMs !== contextReplayUntilMs
    ) {
      setLastDetectionRunId(null);
      setContextReplayUntilMs(props.activeCandleTimeMs);
      setContextLabel(fmtContextDate(props.activeCandleTimeMs));
    }
  }, [props.activeCandleTimeMs, contextReplayUntilMs]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPendingSuggestions(props.apiBase, {
        symbol: props.symbol,
        structure_layer: props.structureLayer,
        source_timeframe: props.sourceTimeframe,
        parent_range_id: props.parentRangeId ?? undefined,
        detection_run_id: lastDetectionRunId ?? undefined,
        replay_until_time_ms: lastDetectionRunId
          ? undefined
          : (contextReplayUntilMs ?? props.activeCandleTimeMs ?? undefined),
        limit: 100,
      });
      if (!data.ok) {
        props.setMessage(`Review candidates load failed: ${data.error || 'unknown'}`);
        setSuggestions([]);
        return;
      }
      const rows = filterRows(data.suggestions || []);
      setSuggestions(rows);
      if (!selectedId && rows.length) setSelectedId(rows[0].suggestion_id);
      else if (selectedId && !rows.find(r => r.suggestion_id === selectedId)) {
        setSelectedId(rows[0]?.suggestion_id || null);
      }
    } finally {
      setLoading(false);
    }
  }, [props, selectedId, lastDetectionRunId, contextReplayUntilMs, filterRows]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    syncEditFields(selected);
  }, [selected, syncEditFields]);

  const runDetector = async () => {
    setRunningDetector(true);
    const detectionRunId = newDetectionRunId();
    const replayUntilMs = props.activeCandleTimeMs ?? null;
    try {
      const out = await runDetectorV1(props.apiBase, {
        symbol: props.symbol,
        source_timeframe: props.sourceTimeframe,
        structure_layer: props.structureLayer,
        range_high: props.rangeHigh ?? undefined,
        range_low: props.rangeLow ?? undefined,
        range_scale: props.rangeScale || 'MAJOR',
        range_role: props.rangeRole ?? undefined,
        parent_range_id: props.parentRangeId ?? undefined,
        active_range_id: props.activeRangeId ?? undefined,
        seed_from_electron: props.activeRangeId != null && props.activeRangeId > 0,
        case_ref: props.caseRef ?? undefined,
        detection_run_id: detectionRunId,
        replay_until_time_ms: replayUntilMs ?? undefined,
        replay_until_time: props.activeCandleTimeLabel ?? undefined,
      });
      if (!out.ok) {
        props.setMessage(`Detector run failed: ${out.error || 'unknown'}`);
        return;
      }
      const runId = out.detection_run_id || detectionRunId;
      const untilMs = out.replay_until_time_ms ?? replayUntilMs;
      setLastDetectionRunId(runId);
      setContextReplayUntilMs(untilMs ?? null);
      const ctxMeta = out.detection_context || {};
      const label =
        (typeof ctxMeta.replay_until_time === 'string' && ctxMeta.replay_until_time) ||
        fmtContextDate(untilMs) ||
        props.activeCandleTimeLabel?.slice(0, 10) ||
        null;
      setContextLabel(label);
      setLastDebugSummary(out.debug_summary ?? null);
      const dbg = out.debug_summary as Record<string, unknown> | undefined;
      const dbgLine = dbg
        ? ` | mode=${String(dbg.range_mode ?? '?')} range=${String(dbg.range_candidate_kind ?? '?')} life=${String(dbg.lifecycle_state ?? '?')} seed=${String(dbg.seed_source ?? '?')} no_seed=${String(dbg.no_seed_context ?? '?')}`
        : '';
      const at = props.activeCandleTimeLabel ? ` @ ${props.activeCandleTimeLabel}` : '';
      props.setMessage(`Python detector wrote ${out.written_count ?? 0} suggestion(s)${at}${dbgLine}.`);
      if (displayMode === 'collapsed') setDisplayMode('compact');
      await refresh();
    } finally {
      setRunningDetector(false);
    }
  };

  const buildEdits = (): ReviewEdits | undefined => {
    if (!selected) return undefined;
    const edits: ReviewEdits = {};
    if (isRangeKind(selected.candidate_kind)) {
      const rh = parseFloat(editRh);
      const rl = parseFloat(editRl);
      if (Number.isFinite(rh)) edits.suggested_rh = rh;
      if (Number.isFinite(rl)) edits.suggested_rl = rl;
      if (editScale) edits.range_scale = editScale;
      if (editRole) edits.range_role = editRole;
    } else {
      const ep = parseFloat(editEventPrice);
      if (Number.isFinite(ep)) edits.event_price = ep;
    }
    return Object.keys(edits).length ? edits : undefined;
  };

  const submitReview = async (action: ReviewAction, withEdits = false) => {
    if (!selected) return;
    setBusy(true);
    try {
      const payload = {
        suggestion_id: selected.suggestion_id,
        action: withEdits ? 'EDIT' as const : action,
        edits: withEdits ? buildEdits() : undefined,
        error_category: action === 'REJECT' ? rejectCategory : undefined,
        notes: action === 'REJECT' ? rejectNotes : '',
      };
      const out = await reviewSuggestion(props.apiBase, payload);
      if (!out.ok) {
        props.setMessage(`Review failed: ${out.error || 'unknown'}`);
        return;
      }
      if (out.duplicate) {
        props.setMessage('Suggestion already reviewed (no duplicate promotion).');
      } else if (action === 'REJECT') {
        props.setMessage(`Rejected ${selected.candidate_kind} suggestion.`);
      } else {
        props.setMessage(
          `${withEdits ? 'Edited & approved' : 'Approved'} ${selected.candidate_kind}` +
          `${out.promoted_range_id ? ` → range #${out.promoted_range_id}` : ''}` +
          `${out.promoted_event_id ? ` → event #${out.promoted_event_id}` : ''}`,
        );
      }
      await refresh();
      if (props.onPromoted) await props.onPromoted();
    } finally {
      setBusy(false);
    }
  };

  const displayContextLabel = contextLabel
    || (selected?.meta_json?.replay_until_time as string | undefined)
    || fmtContextDate(contextReplayUntilMs ?? props.activeCandleTimeMs);

  const emptyContextHint = lastDetectionRunId || contextReplayUntilMs;

  const renderCompactCard = (row: DetectorSuggestionRow) => (
    <button
      key={row.suggestion_id}
      type="button"
      className={`reviewCandidateCompactCard${selectedId === row.suggestion_id ? ' active' : ''}`}
      onClick={() => setSelectedId(row.suggestion_id)}
    >
      <span className="reviewCardKind">{row.candidate_kind}</span>
      <span className="reviewCardScale">{row.range_scale || '—'}</span>
      <span className="reviewCardPrice">{candidatePriceLabel(row)}</span>
      <span className="reviewCardVersion">{row.detector_version}</span>
      <span className="reviewCardConf">{row.confidence || 'MED'}</span>
    </button>
  );

  const renderActionRow = (showEditExpand = true) => (
    <div className="reviewActionRow reviewActionRowCompact">
      <button type="button" className="approveBtn" disabled={busy || !selected} onClick={() => void submitReview('APPROVE')}>
        Approve
      </button>
      <button
        type="button"
        className="editBtn"
        disabled={busy || !selected}
        onClick={() => {
          if (displayMode !== 'expanded') {
            setDisplayMode('expanded');
            return;
          }
          void submitReview('EDIT', true);
        }}
      >
        Edit + Approve
      </button>
      <select
        className="reviewRejectSelect"
        value={rejectCategory}
        disabled={busy || !selected}
        onChange={e => setRejectCategory(e.target.value)}
        aria-label="Reject category"
      >
        {ERROR_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <button type="button" className="rejectBtn" disabled={busy || !selected} onClick={() => void submitReview('REJECT')}>
        Reject
      </button>
      {showEditExpand && selected && displayMode === 'compact' && (
        <button type="button" className="reviewDetailsBtn" disabled={busy} onClick={() => setDisplayMode('expanded')}>
          Details
        </button>
      )}
    </div>
  );

  const renderExpandedDetail = () => {
    if (!selected) return null;
    return (
      <div className="reviewCandidateExpandedDrawer">
        <div className="reviewExpandedHeader">
          <strong>Full candidate detail</strong>
          <button type="button" className="reviewCollapseBtn" onClick={() => setDisplayMode('compact')}>
            Close
          </button>
        </div>
        <div className="reviewDetailGrid">
          <div><span>Kind</span><strong>{selected.candidate_kind}</strong></div>
          <div><span>Detector</span><strong>{selected.detector_version}</strong></div>
          <div><span>Engine</span><strong>{selected.engine_source}</strong></div>
          <div><span>Context</span><strong>{displayContextLabel || '—'}</strong></div>
          <div><span>Scale</span><strong>{selected.range_scale || '—'}</strong></div>
          <div><span>Role</span><strong>{selected.range_role || '—'}</strong></div>
          <div><span>RH / RL</span><strong>{selected.suggested_rh ?? '—'} / {selected.suggested_rl ?? '—'}</strong></div>
          <div><span>Event</span><strong>{selected.event_side || '—'} @ {selected.event_price ?? '—'}</strong></div>
          <div><span>Time</span><strong>{fmtTime(selected.candle_time_utc_ms)}</strong></div>
          <div><span>Confidence</span><strong>{selected.confidence || 'MEDIUM'}</strong></div>
          <div><span>Break rule</span><strong>{selected.break_rule || '—'}</strong></div>
        </div>
        {selected.reason_text && <p className="reviewReason">{selected.reason_text}</p>}
        {selected.meta_json && (
          <details className="reviewMetaDetails">
            <summary>meta_json</summary>
            <pre>{JSON.stringify(selected.meta_json, null, 2)}</pre>
          </details>
        )}
        {isRangeKind(selected.candidate_kind) && (
          <div className="reviewEditFields">
            <label>RH <input value={editRh} onChange={e => setEditRh(e.target.value)} /></label>
            <label>RL <input value={editRl} onChange={e => setEditRl(e.target.value)} /></label>
            <label>Scale
              <select value={editScale} onChange={e => setEditScale(e.target.value)}>
                <option value="MAJOR">MAJOR</option>
                <option value="MINOR">MINOR</option>
              </select>
            </label>
            <label>Role
              <select value={editRole} onChange={e => setEditRole(e.target.value)}>
                <option value="">—</option>
                <option value="ACTIVE_CONTAINER">ACTIVE_CONTAINER</option>
                <option value="INTERNAL_LEG">INTERNAL_LEG</option>
                <option value="EXPANSION_LEG">EXPANSION_LEG</option>
              </select>
            </label>
          </div>
        )}
        {!isRangeKind(selected.candidate_kind) && (
          <div className="reviewEditFields">
            <label>Event price <input value={editEventPrice} onChange={e => setEditEventPrice(e.target.value)} /></label>
          </div>
        )}
        <label className="reviewRejectNotes">
          Reject notes
          <input value={rejectNotes} onChange={e => setRejectNotes(e.target.value)} placeholder="optional" />
        </label>
        {renderActionRow(false)}
      </div>
    );
  };

  if (displayMode === 'collapsed') {
    return (
      <div className="reviewCandidatePanel reviewCandidatePanelCollapsed">
        <button
          type="button"
          className="reviewCandidateChip"
          onClick={() => setDisplayMode('compact')}
          aria-expanded={false}
        >
          <span className="reviewCandidateChipTitle">Review Candidates ({suggestions.length})</span>
          {displayContextLabel && (
            <span className="reviewCandidateChipContext">Up to {displayContextLabel}</span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className={`reviewCandidatePanel reviewCandidatePanel${displayMode === 'expanded' ? 'Expanded' : 'Compact'}`}>
      <div className="reviewCandidateCompactHeader">
        <div className="reviewCandidateCompactTitle">
          <strong>Review Candidates ({suggestions.length})</strong>
          {displayContextLabel && (
            <span className="reviewDetectionContext">
              Context: up to <strong>{displayContextLabel}</strong>
              {props.replayMode ? ' (replay)' : ''}
            </span>
          )}
          {lastDebugSummary && (
            <span className="reviewDetectionDebug">
              Debug: {String(lastDebugSummary.range_candidate_kind ?? '—')} · life={String(lastDebugSummary.lifecycle_state ?? '—')} · seed={String(lastDebugSummary.seed_source ?? '—')} · no_seed={String(lastDebugSummary.no_seed_context ?? '—')}
            </span>
          )}
        </div>
        <button
          type="button"
          className="reviewCollapseBtn"
          onClick={() => setDisplayMode('collapsed')}
          aria-label="Collapse review candidates"
        >
          −
        </button>
      </div>

      <div className="reviewCandidateToolbar reviewCandidateToolbarCompact">
        <button type="button" onClick={() => void runDetector()} disabled={runningDetector || busy}>
          {runningDetector ? 'Running…' : 'Run Python Detector'}
        </button>
        <button type="button" onClick={() => void refresh()} disabled={loading || busy}>Refresh</button>
      </div>

      <div className="reviewCandidateCompactBody">
        {loading && <div className="mutedSmall">Loading…</div>}
        {!loading && !suggestions.length && (
          <div className="mutedSmall reviewEmptyState">
            {emptyContextHint
              ? 'No suggestions for current replay context. Run Python Detector.'
              : 'No pending suggestions.'}
          </div>
        )}
        <div className="reviewCandidateCompactList">
          {suggestions.map(renderCompactCard)}
        </div>

        {selected && displayMode === 'compact' && (
          <div className="reviewSelectedSummary">
            <span className="reviewSummaryKind">{selected.candidate_kind}</span>
            <span>{selected.range_scale || '—'}</span>
            <span>{candidatePriceLabel(selected)}</span>
            <span>{selected.detector_version}</span>
            <span>{selected.confidence || 'MEDIUM'}</span>
          </div>
        )}

        {displayMode === 'compact' && renderActionRow()}
      </div>

      {displayMode === 'expanded' && renderExpandedDetail()}
    </div>
  );
}
