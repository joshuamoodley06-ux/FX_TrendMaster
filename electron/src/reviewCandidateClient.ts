export type DetectorSuggestionRow = {
  suggestion_id: string;
  candidate_kind: string;
  detector_version: string;
  engine_source: string;
  status: string;
  symbol: string;
  structure_layer: string;
  source_timeframe: string;
  chart_timeframe?: string;
  parent_range_id?: number | null;
  active_range_id?: number | null;
  case_ref?: string | null;
  suggested_rh?: number | null;
  suggested_rl?: number | null;
  range_scale?: string | null;
  range_role?: string | null;
  event_side?: string | null;
  event_price?: number | null;
  break_rule?: string | null;
  movement_rule?: string | null;
  derived_event_code?: string | null;
  confidence?: string | null;
  reason_text?: string;
  candle_time_utc_ms?: number;
  meta_json?: Record<string, unknown> | null;
};

export type ReviewEdits = {
  suggested_rh?: number;
  suggested_rl?: number;
  range_scale?: string;
  range_role?: string;
  event_price?: number;
  event_side?: string;
};

export type ReviewAction = 'APPROVE' | 'EDIT' | 'REJECT' | 'AUDIT_PASS' | 'AUDIT_FAIL';

export type RangeAuditSample = {
  source: 'suggestions' | 'confirmed_ranges';
  id?: string;
  suggestion_id?: string | null;
  range_id?: number | null;
  candidate_kind?: string;
  rh?: number | null;
  rl?: number | null;
  range_high_price?: number | null;
  range_low_price?: number | null;
  symbol?: string;
  structure_layer?: string;
  source_timeframe?: string;
  chart_timeframe?: string;
  detector_version?: string;
  replay_until_time?: string | null;
  replay_until_time_ms?: number | null;
  first_candle_time?: string | null;
  last_candle_time?: string | null;
  range_start_time?: string | null;
  range_end_time?: string | null;
  lifecycle_state?: string | null;
  boundary_selection_reason?: string | null;
  meta_json?: Record<string, unknown> | null;
};

export type RangeAuditViewTarget = {
  kind: 'suggestion' | 'confirmed_range';
  rh: number;
  rl: number;
  range_start_time?: string | null;
  range_end_time?: string | null;
  source_timeframe?: string;
  chart_timeframe?: string;
  structure_layer?: string;
  candidate_kind?: string;
  detector_version?: string;
  replay_until_time?: string | null;
  lifecycle_state?: string | null;
  boundary_selection_reason?: string | null;
  suggestion_id?: string | null;
  range_id?: number | null;
};

async function parseJson<T>(res: Response): Promise<T> {
  return res.json() as Promise<T>;
}

export async function fetchPendingSuggestions(
  apiBase: string,
  filters: {
    symbol: string;
    structure_layer?: string;
    source_timeframe?: string;
    parent_range_id?: number | null;
    limit?: number;
    detection_run_id?: string | null;
    replay_until_time_ms?: number | null;
  },
): Promise<{ ok: boolean; suggestions?: DetectorSuggestionRow[]; count?: number; error?: string }> {
  const url = new URL(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/suggestions`);
  url.searchParams.set('symbol', filters.symbol);
  url.searchParams.set('status', 'PENDING');
  if (filters.structure_layer) url.searchParams.set('structure_layer', filters.structure_layer);
  if (filters.source_timeframe) url.searchParams.set('source_timeframe', filters.source_timeframe);
  if (filters.parent_range_id != null && filters.parent_range_id !== '') {
    url.searchParams.set('parent_range_id', String(filters.parent_range_id));
  }
  if (filters.limit) url.searchParams.set('limit', String(filters.limit));
  if (filters.detection_run_id) url.searchParams.set('detection_run_id', filters.detection_run_id);
  if (filters.replay_until_time_ms != null && filters.replay_until_time_ms > 0) {
    url.searchParams.set('replay_until_time_ms', String(filters.replay_until_time_ms));
  }
  const res = await fetch(url.toString());
  const data = await parseJson<{ ok: boolean; suggestions?: DetectorSuggestionRow[]; count?: number; error?: string; detail?: string }>(res);
  if (!res.ok || !data.ok) {
    return { ok: false, suggestions: [], count: 0, error: data.error || data.detail || res.statusText };
  }
  return data;
}

export async function runDetectorV1(
  apiBase: string,
  payload: {
    symbol: string;
    source_timeframe: string;
    structure_layer?: string;
    range_high?: number | null;
    range_low?: number | null;
    range_scale?: string;
    range_role?: string | null;
    active_index?: number;
    replay_until_time_ms?: number;
    replay_until_time?: string;
    visible_from_time_ms?: number;
    visible_from_time?: string;
    active_candle_time_ms?: number;
    active_candle_time?: string;
    parent_range_id?: number | null;
    active_range_id?: number | null;
    seed_from_electron?: boolean;
    case_ref?: string | null;
    detection_run_id?: string;
    limit?: number;
    date_from_ms?: number;
    date_from?: string;
    date_to_ms?: number;
    date_to?: string;
    period_scan?: boolean;
    range_scale_mode?: string;
  },
): Promise<{
  ok: boolean;
  written_count?: number;
  detection_run_id?: string;
  replay_until_time_ms?: number | null;
  detection_context?: Record<string, unknown>;
  debug_summary?: Record<string, unknown>;
  error?: string;
}> {
  const res = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/run-detector`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await parseJson<{
    ok: boolean;
    written_count?: number;
    detection_run_id?: string;
    replay_until_time_ms?: number | null;
    detection_context?: Record<string, unknown>;
    debug_summary?: Record<string, unknown>;
    error?: string;
    detail?: string;
  }>(res);
  if (!res.ok || !data.ok) {
    return { ok: false, error: data.error || data.detail || res.statusText };
  }
  return data;
}

export function auditSampleToViewTarget(sample: RangeAuditSample): RangeAuditViewTarget | null {
  const rh = Number(sample.rh ?? sample.range_high_price);
  const rl = Number(sample.rl ?? sample.range_low_price);
  if (!Number.isFinite(rh) || !Number.isFinite(rl) || rh <= rl) return null;
  return {
    kind: sample.source === 'confirmed_ranges' ? 'confirmed_range' : 'suggestion',
    rh,
    rl,
    range_start_time: sample.range_start_time || sample.first_candle_time || null,
    range_end_time: sample.range_end_time || sample.last_candle_time || sample.replay_until_time || null,
    source_timeframe: sample.source_timeframe,
    chart_timeframe: sample.chart_timeframe || sample.source_timeframe,
    structure_layer: sample.structure_layer,
    candidate_kind: sample.candidate_kind,
    detector_version: sample.detector_version,
    replay_until_time: sample.replay_until_time || null,
    lifecycle_state: sample.lifecycle_state || null,
    boundary_selection_reason: sample.boundary_selection_reason || null,
    suggestion_id: sample.suggestion_id || (sample.source === 'suggestions' ? sample.id : null),
    range_id: sample.range_id ?? null,
  };
}

export function suggestionToViewTarget(row: DetectorSuggestionRow): RangeAuditViewTarget | null {
  const rh = Number(row.suggested_rh);
  const rl = Number(row.suggested_rl);
  if (!Number.isFinite(rh) || !Number.isFinite(rl) || rh <= rl) return null;
  const meta = row.meta_json || {};
  return {
    kind: 'suggestion',
    rh,
    rl,
    range_start_time: (meta.first_candle_time as string) || null,
    range_end_time: (meta.last_candle_time as string) || (meta.replay_until_time as string) || null,
    source_timeframe: row.source_timeframe,
    chart_timeframe: row.chart_timeframe || row.source_timeframe,
    structure_layer: row.structure_layer,
    candidate_kind: row.candidate_kind,
    detector_version: row.detector_version,
    replay_until_time: (meta.replay_until_time as string) || null,
    lifecycle_state: (meta.lifecycle_state as string) || null,
    boundary_selection_reason: (meta.boundary_selection_reason as string) || null,
    suggestion_id: row.suggestion_id,
  };
}

export async function fetchRandomAuditSamples(
  apiBase: string,
  payload: {
    symbol: string;
    structure_layer: string;
    source_timeframe: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    source?: 'suggestions' | 'confirmed_ranges';
    detector_version?: string;
    detection_run_id?: string;
  },
): Promise<{ ok: boolean; samples?: RangeAuditSample[]; count?: number; pool_size?: number; error?: string }> {
  const res = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/ranges/random-audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await parseJson<{
    ok: boolean;
    samples?: RangeAuditSample[];
    count?: number;
    pool_size?: number;
    error?: string;
    detail?: string;
  }>(res);
  if (!res.ok || !data.ok) {
    return { ok: false, samples: [], error: data.error || data.detail || res.statusText };
  }
  return data;
}

export async function recordAuditVerdict(
  apiBase: string,
  payload: {
    suggestion_id: string;
    action: 'AUDIT_PASS' | 'AUDIT_FAIL';
    notes?: string;
  },
): Promise<{ ok: boolean; correction_id?: string; error?: string }> {
  const res = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/suggestions/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await parseJson<{ ok: boolean; correction_id?: string; error?: string; detail?: string }>(res);
  if (!res.ok || !data.ok) {
    return { ok: false, error: data.error || data.detail || res.statusText };
  }
  return data;
}

export async function reviewSuggestion(
  apiBase: string,
  payload: {
    suggestion_id: string;
    action: ReviewAction;
    edits?: ReviewEdits;
    error_category?: string;
    notes?: string;
  },
): Promise<{ ok: boolean; promoted_range_id?: number | null; promoted_event_id?: number | null; duplicate?: boolean; error?: string }> {
  const res = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/suggestions/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await parseJson<{
    ok: boolean;
    promoted_range_id?: number | null;
    promoted_event_id?: number | null;
    duplicate?: boolean;
    error?: string;
    detail?: string;
  }>(res);
  if (!res.ok || !data.ok) {
    return { ok: false, error: data.error || data.detail || res.statusText };
  }
  return data;
}
