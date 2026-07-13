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
  | 'range_hard_delete'
  | 'raw_delete';

export type InspectorCommitKind =
  | 'raw_mapping_event'
  | 'raw_mapping_event_delete'
  | 'structural_event'
  | 'structural_event_patch'
  | 'structural_range'
  | 'structural_range_patch'
  | 'structural_range_reparent'
  | 'structural_range_hard_delete';

export type InspectorCommitRequest = {
  baseUrl: string;
  kind: InspectorCommitKind;
  source: InspectorCommitSource;
  payload?: Record<string, unknown>;
  pathParams?: { eventId?: string; rangeId?: string };
};

export type LocalMappingProcessingState = {
  ok: boolean;
  saved: boolean;
  state: 'SUCCESS' | 'PENDING' | 'FAILED';
  editId?: string;
  duplicate?: boolean;
  attemptCount?: number;
  databasePath?: string;
  electronDatabasePath?: string;
  pythonDatabasePath?: string | null;
  sameDatabasePath?: boolean | null;
  processorVersion?: string | null;
  result?: unknown;
  error?: string;
};

export type InspectorCommitResult<T = unknown> = {
  ok: boolean;
  kind: InspectorCommitKind;
  source: InspectorCommitSource;
  data?: T;
  error?: string;
  httpStatus?: number;
  localProcessing?: LocalMappingProcessingState;
};

type LocalMappingBridgeApi = {
  submit: (request: {
    kind: InspectorCommitKind;
    source: InspectorCommitSource;
    payload?: Record<string, unknown>;
    pathParams?: { eventId?: string; rangeId?: string };
  }) => Promise<LocalMappingProcessingState>;
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
    case 'structural_range_hard_delete':
      return { url: `${base}/api/v1/map/ranges/hard-delete`, method: 'POST' };
    default: {
      const unknown = (req as { kind?: string }).kind ?? 'unknown';
      throw new Error(`Unknown inspector commit kind: ${unknown}`);
    }
  }
}

function localMappingBridge(): LocalMappingBridgeApi | undefined {
  return (globalThis as typeof globalThis & { localMappingBridge?: LocalMappingBridgeApi }).localMappingBridge;
}

function requiresLocalDurability(kind: InspectorCommitKind): boolean {
  return kind === 'structural_range' || kind === 'structural_event';
}

async function persistLocallyBeforeBackend(
  req: InspectorCommitRequest,
): Promise<LocalMappingProcessingState | undefined> {
  if (!requiresLocalDurability(req.kind)) return undefined;
  const bridge = localMappingBridge();
  if (!bridge) return undefined; // Browser/dev fallback. Electron preload owns the durable path.
  try {
    return await bridge.submit({
      kind: req.kind,
      source: req.source,
      payload: req.payload,
      pathParams: req.pathParams,
    });
  } catch (err: unknown) {
    return {
      ok: false,
      saved: false,
      state: 'FAILED',
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

function attachLocalProcessing<T>(data: T, localProcessing?: LocalMappingProcessingState): T {
  if (!localProcessing || !data || typeof data !== 'object' || Array.isArray(data)) return data;
  return {
    ...(data as Record<string, unknown>),
    local_processing: localProcessing,
  } as T;
}

export async function inspectorCommit<T = unknown>(
  req: InspectorCommitRequest,
): Promise<InspectorCommitResult<T>> {
  let url = '';
  let method: 'POST' | 'PATCH' = 'POST';
  let localProcessing: LocalMappingProcessingState | undefined;
  try {
    ({ url, method } = resolveCommitTarget(req));
    localProcessing = await persistLocallyBeforeBackend(req);
    if (localProcessing && !localProcessing.saved) {
      return {
        ok: false,
        kind: req.kind,
        source: req.source,
        error: localProcessing.error || 'Local mapping edit could not be saved.',
        localProcessing,
      };
    }

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
      data: ok ? attachLocalProcessing(data, localProcessing) : undefined,
      error: ok ? undefined : (data?.error || data?.detail || `Backend request failed ${res.status}`),
      httpStatus: res.status,
      localProcessing,
    };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      kind: req.kind,
      source: req.source,
      error: message,
      localProcessing,
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
