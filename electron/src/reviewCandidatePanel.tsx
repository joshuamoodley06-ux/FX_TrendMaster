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
  activeCandleIndex?: number | null;
  onPromoted?: () => void | Promise<void>;
  setMessage: (msg: string) => void;
};

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

export function ReviewCandidatePanel(props: Props) {
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

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPendingSuggestions(props.apiBase, {
        symbol: props.symbol,
        structure_layer: props.structureLayer,
        source_timeframe: props.sourceTimeframe,
        parent_range_id: props.parentRangeId ?? undefined,
        limit: 100,
      });
      if (!data.ok) {
        props.setMessage(`Review candidates load failed: ${data.error || 'unknown'}`);
        setSuggestions([]);
        return;
      }
      const rows = data.suggestions || [];
      setSuggestions(rows);
      if (!selectedId && rows.length) setSelectedId(rows[0].suggestion_id);
      else if (selectedId && !rows.find(r => r.suggestion_id === selectedId)) {
        setSelectedId(rows[0]?.suggestion_id || null);
      }
    } finally {
      setLoading(false);
    }
  }, [props, selectedId]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    syncEditFields(selected);
  }, [selected, syncEditFields]);

  const runDetector = async () => {
    setRunningDetector(true);
    try {
      const out = await runDetectorV1(props.apiBase, {
        symbol: props.symbol,
        source_timeframe: props.sourceTimeframe,
        range_high: props.rangeHigh ?? undefined,
        range_low: props.rangeLow ?? undefined,
        range_scale: props.rangeScale || 'MAJOR',
        parent_range_id: props.parentRangeId ?? undefined,
        active_range_id: props.activeRangeId ?? undefined,
        case_ref: props.caseRef ?? undefined,
        active_index: props.activeCandleIndex ?? undefined,
      });
      if (!out.ok) {
        props.setMessage(`Detector run failed: ${out.error || 'unknown'}`);
        return;
      }
      props.setMessage(`Python detector wrote ${out.written_count ?? 0} suggestion(s).`);
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

  return (
    <div className="reviewCandidatePanel">
      <div className="reviewCandidateHeader">
        <h4>Review Candidates</h4>
        <p className="mutedSmall">Python suggests → you decide → save truth. No autopilot.</p>
        <div className="reviewCandidateToolbar">
          <button type="button" onClick={() => void refresh()} disabled={loading || busy}>Refresh</button>
          <button type="button" onClick={() => void runDetector()} disabled={runningDetector || busy}>
            {runningDetector ? 'Running detector…' : 'Run Python Detector'}
          </button>
        </div>
      </div>

      <div className="reviewCandidateFilters mutedSmall">
        {props.symbol} · {props.structureLayer} · {props.sourceTimeframe}
        {props.parentRangeId != null ? ` · parent #${props.parentRangeId}` : ' · no parent filter'}
        {' · '}PENDING only · engine: python_detector
      </div>

      <div className="reviewCandidateBody">
        <div className="reviewCandidateList">
          {loading && <div className="mutedSmall">Loading…</div>}
          {!loading && !suggestions.length && <div className="mutedSmall">No pending suggestions.</div>}
          {suggestions.map(row => (
            <button
              key={row.suggestion_id}
              type="button"
              className={`reviewCandidateListItem${selectedId === row.suggestion_id ? ' active' : ''}`}
              onClick={() => setSelectedId(row.suggestion_id)}
            >
              <strong>{row.candidate_kind}</strong>
              <span>{row.detector_version}</span>
              <em>{row.confidence || 'MEDIUM'}</em>
            </button>
          ))}
        </div>

        {selected && (
          <div className="reviewCandidateDetail">
            <div className="reviewDetailGrid">
              <div><span>Kind</span><strong>{selected.candidate_kind}</strong></div>
              <div><span>Detector</span><strong>{selected.detector_version}</strong></div>
              <div><span>Engine</span><strong>{selected.engine_source}</strong></div>
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

            <div className="reviewActionRow">
              <button type="button" className="approveBtn" disabled={busy} onClick={() => void submitReview('APPROVE')}>Approve</button>
              <button type="button" className="editBtn" disabled={busy} onClick={() => void submitReview('EDIT', true)}>Edit + Approve</button>
            </div>

            <div className="reviewRejectBlock">
              <label>Reject category
                <select value={rejectCategory} onChange={e => setRejectCategory(e.target.value)}>
                  {ERROR_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label>Notes <input value={rejectNotes} onChange={e => setRejectNotes(e.target.value)} placeholder="optional" /></label>
              <button type="button" className="rejectBtn" disabled={busy} onClick={() => void submitReview('REJECT')}>Reject</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
