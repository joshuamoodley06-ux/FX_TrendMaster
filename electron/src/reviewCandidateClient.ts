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

export type ReviewAction = 'APPROVE' | 'EDIT' | 'REJECT';

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
    range_high?: number | null;
    range_low?: number | null;
    range_scale?: string;
    active_index?: number;
    active_candle_time_ms?: number;
    active_candle_time?: string;
    parent_range_id?: number | null;
    active_range_id?: number | null;
    case_ref?: string | null;
    limit?: number;
  },
): Promise<{ ok: boolean; written_count?: number; error?: string }> {
  const res = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/detection-brain/run-detector`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await parseJson<{ ok: boolean; written_count?: number; error?: string; detail?: string }>(res);
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
