/**
 * InspectorCommit — single durable-write funnel for mapping ingress.
 * Range selection, manual marks, structural saves, and lifecycle patches
 * must all route through inspectorCommit / inspectorCommitOrThrow.
 */

export type InspectorCommitSource =
  | 'manual_mark'
  | 'marker_bundle'
  | 'chart_click'
  | 'event_drag'
  | 'htf_candidate'
  | 'structural_quick_button'
  | 'structural_range_save'
  | 'structural_range_next'
  | 'structural_bos'
  | 'structural_undo'
  | 'range_lifecycle_patch'
  | 'range_chain_link'
  | 'range_reparent'
  | 'range_archive'
  | 'raw_delete';

export type InspectorCommitKind =
  | 'raw_mapping_event'
  | 'raw_mapping_event_delete'
  | 'structural_event'
  | 'structural_event_patch'
  | 'structural_range'
  | 'structural_range_patch'
  | 'structural_range_reparent';

export type InspectorCommitRequest = {
  baseUrl: string;
  kind: InspectorCommitKind;
  source: InspectorCommitSource;
  payload?: Record<string, unknown>;
  pathParams?: { eventId?: string; rangeId?: string };
};

export type InspectorCommitResult<T = unknown> = {
  ok: boolean;
  kind: InspectorCommitKind;
  source: InspectorCommitSource;
  data?: T;
  error?: string;
  httpStatus?: number;
};

function normalizeBaseUrl(base: string): string {
  return base.replace(/\/$/, '');
}

function resolveCommitTarget(req: InspectorCommitRequest): { url: string; method: 'POST' | 'PATCH' } {
  const base = normalizeBaseUrl(req.baseUrl);
  switch (req.kind) {
    case 'raw_mapping_event':
      return { url: `${base}/api/v1/raw-mapping/events`, method: 'POST' };
    case 'raw_mapping_event_delete':
      return { url: `${base}/api/v1/raw-mapping/events/delete`, method: 'POST' };
    case 'structural_event':
      return { url: `${base}/api/v1/map/structural-event`, method: 'POST' };
    case 'structural_event_patch': {
      const eventId = req.pathParams?.eventId;
      if (!eventId) throw new Error('structural_event_patch requires pathParams.eventId');
      return {
        url: `${base}/api/v1/map/structural-event/${encodeURIComponent(eventId)}`,
        method: 'PATCH',
      };
    }
    case 'structural_range':
      return { url: `${base}/api/v1/map/range`, method: 'POST' };
    case 'structural_range_patch': {
      const rangeId = req.pathParams?.rangeId;
      if (!rangeId) throw new Error('structural_range_patch requires pathParams.rangeId');
      return {
        url: `${base}/api/v1/map/range/${encodeURIComponent(rangeId)}`,
        method: 'PATCH',
      };
    }
    case 'structural_range_reparent':
      return { url: `${base}/api/v1/map/range/reparent`, method: 'POST' };
    default: {
      const unknown = (req as { kind?: string }).kind ?? 'unknown';
      throw new Error(`Unknown inspector commit kind: ${unknown}`);
    }
  }
}

export async function inspectorCommit<T = unknown>(
  req: InspectorCommitRequest,
): Promise<InspectorCommitResult<T>> {
  let url = '';
  let method: 'POST' | 'PATCH' = 'POST';
  try {
    ({ url, method } = resolveCommitTarget(req));
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.payload ?? {}),
    });
    const data = (await res.json().catch(() => ({
      ok: false,
      error: `Invalid backend response ${res.status}`,
    }))) as T & { ok?: boolean; error?: string; detail?: string };
    const ok = res.ok && data?.ok !== false;
    return {
      ok,
      kind: req.kind,
      source: req.source,
      data: ok ? data : undefined,
      error: ok ? undefined : (data?.error || data?.detail || `Backend request failed ${res.status}`),
      httpStatus: res.status,
    };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      kind: req.kind,
      source: req.source,
      error: message,
    };
  }
}

export async function inspectorCommitOrThrow<T = unknown>(
  req: InspectorCommitRequest,
): Promise<T> {
  const result = await inspectorCommit<T>(req);
  if (!result.ok) {
    throw new Error(result.error || 'Inspector commit failed');
  }
  return result.data as T;
}
