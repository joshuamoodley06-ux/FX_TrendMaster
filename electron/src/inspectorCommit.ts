/**
 * InspectorCommit — single durable-write funnel for mapping ingress.
 * Range selection, manual marks, structural saves, and lifecycle patches
 * must all route through inspectorCommit / inspectorCommitOrThrow.
 */

export type InspectorCommitSource =
  | 'manual_mark' | 'marker_bundle' | 'chart_click' | 'event_drag' | 'htf_candidate'
  | 'structural_quick_button' | 'structural_range_save' | 'structural_range_next'
  | 'structural_bos' | 'structural_undo' | 'range_lifecycle_patch' | 'range_chain_link'
  | 'range_reparent' | 'range_archive' | 'range_hard_delete' | 'raw_delete';

export type InspectorCommitKind =
  | 'raw_mapping_event' | 'raw_mapping_event_delete' | 'structural_event'
  | 'structural_event_patch'
  | 'structural_range' | 'structural_range_patch'
  | 'structural_range_reparent' | 'structural_range_hard_delete';

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
  status?: string;
  editId?: string;
  duplicate?: boolean;
  backendStatus?: 'UNCONFIRMED' | 'REJECTED' | 'RESPONSE_INVALID' | 'CONFIRMED' | string;
  backendAttemptCount?: number;
  backendResponse?: unknown;
  backendConfirmedPayload?: unknown;
  backendHttpStatus?: number | null;
  backendRangeId?: string | null;
  backendEventId?: string | null;
  backendError?: string;
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
  backendSucceeded: (editId: string, backendResponse: unknown, httpStatus?: number) => Promise<LocalMappingProcessingState>;
  backendFailed: (editId: string, details: { error: string; response?: unknown; httpStatus?: number }) => Promise<LocalMappingProcessingState>;
  retry: (editId: string) => Promise<LocalMappingProcessingState>;
};

function normalizeBaseUrl(base: string): string { return base.replace(/\/$/, ''); }

function resolveCommitTarget(req: InspectorCommitRequest): { url: string; method: 'POST' | 'PATCH' } {
  const base = normalizeBaseUrl(req.baseUrl);
  switch (req.kind) {
    case 'raw_mapping_event': return { url: `${base}/api/v1/raw-mapping/events`, method: 'POST' };
    case 'raw_mapping_event_delete': return { url: `${base}/api/v1/raw-mapping/events/delete`, method: 'POST' };
    case 'structural_event': return { url: `${base}/api/v1/map/structural-event`, method: 'POST' };
    case 'structural_event_patch': {
      const eventId = req.pathParams?.eventId;
      if (!eventId) throw new Error('structural_event_patch requires pathParams.eventId');
      return { url: `${base}/api/v1/map/structural-event/${encodeURIComponent(eventId)}`, method: 'PATCH' };
    }
    case 'structural_range': return { url: `${base}/api/v1/map/range`, method: 'POST' };
    case 'structural_range_patch': {
      const rangeId = req.pathParams?.rangeId;
      if (!rangeId) throw new Error('structural_range_patch requires pathParams.rangeId');
      return { url: `${base}/api/v1/map/range/${encodeURIComponent(rangeId)}`, method: 'PATCH' };
    }
    case 'structural_range_reparent': return { url: `${base}/api/v1/map/range/reparent`, method: 'POST' };
    case 'structural_range_hard_delete': return { url: `${base}/api/v1/map/ranges/hard-delete`, method: 'POST' };
    default: throw new Error(`Unknown inspector commit kind: ${(req as { kind?: string }).kind ?? 'unknown'}`);
  }
}

function localMappingBridge(): LocalMappingBridgeApi | undefined {
  return (globalThis as typeof globalThis & { localMappingBridge?: LocalMappingBridgeApi }).localMappingBridge;
}
function requiresLocalDurability(kind: InspectorCommitKind): boolean {
  return kind === 'structural_range' || kind === 'structural_event';
}
async function prepareLocalInstruction(req: InspectorCommitRequest): Promise<LocalMappingProcessingState | undefined> {
  if (!requiresLocalDurability(req.kind)) return undefined;
  const bridge = localMappingBridge();
  if (!bridge) return undefined;
  try {
    return await bridge.submit({ kind: req.kind, source: req.source, payload: req.payload, pathParams: req.pathParams });
  } catch (err: unknown) {
    return { ok: false, saved: false, state: 'FAILED', error: err instanceof Error ? err.message : String(err) };
  }
}
function attachLocalProcessing<T>(data: T, localProcessing?: LocalMappingProcessingState): T {
  if (!localProcessing || !data || typeof data !== 'object' || Array.isArray(data)) return data;
  return { ...(data as Record<string, unknown>), local_processing: localProcessing } as T;
}
function unresolvedConfirmationError(localProcessing: LocalMappingProcessingState): string {
  return localProcessing.error
    || localProcessing.backendError
    || 'Backend returned success without a usable final structural identity. Manual reconciliation is required.';
}

export async function inspectorCommit<T = unknown>(req: InspectorCommitRequest): Promise<InspectorCommitResult<T>> {
  let url = '';
  let method: 'POST' | 'PATCH' = 'POST';
  let localProcessing: LocalMappingProcessingState | undefined;
  const bridge = localMappingBridge();
  try {
    ({ url, method } = resolveCommitTarget(req));
    localProcessing = await prepareLocalInstruction(req);
    if (localProcessing && !localProcessing.saved) {
      return { ok: false, kind: req.kind, source: req.source,
        error: localProcessing.error || 'Local mapping edit could not be saved.', localProcessing };
    }

    if (localProcessing?.backendStatus === 'RESPONSE_INVALID') {
      return {
        ok: false,
        kind: req.kind,
        source: req.source,
        error: unresolvedConfirmationError(localProcessing),
        httpStatus: localProcessing.backendHttpStatus ?? undefined,
        localProcessing,
      };
    }

    if (localProcessing?.backendStatus === 'CONFIRMED' && localProcessing.editId && bridge) {
      localProcessing = await bridge.retry(localProcessing.editId);
      const storedBackend = localProcessing.backendResponse as T | undefined;
      return {
        ok: true, kind: req.kind, source: req.source,
        data: storedBackend ? attachLocalProcessing(storedBackend, localProcessing) : undefined,
        httpStatus: 200, localProcessing,
      };
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req.payload ?? {}),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (localProcessing?.editId && bridge) {
        localProcessing = await bridge.backendFailed(localProcessing.editId, { error: message });
      }
      return { ok: false, kind: req.kind, source: req.source, error: message, localProcessing };
    }

    const data = (await res.json().catch(() => ({
      ok: false,
      error: `Invalid backend response ${res.status}`,
    }))) as T & { ok?: boolean; error?: string; detail?: string };
    const ok = res.ok && data?.ok !== false;
    if (!ok) {
      const error = data?.error || data?.detail || `Backend request failed ${res.status}`;
      if (localProcessing?.editId && bridge) {
        localProcessing = await bridge.backendFailed(localProcessing.editId, {
          error, response: data, httpStatus: res.status,
        });
      }
      return { ok: false, kind: req.kind, source: req.source, error, httpStatus: res.status, localProcessing };
    }

    if (localProcessing?.editId && bridge) {
      localProcessing = await bridge.backendSucceeded(localProcessing.editId, data, res.status);
      if (localProcessing.backendStatus === 'RESPONSE_INVALID' || localProcessing.status === 'BACKEND_CONFIRMATION_INCOMPLETE') {
        return {
          ok: false,
          kind: req.kind,
          source: req.source,
          error: unresolvedConfirmationError(localProcessing),
          httpStatus: res.status,
          localProcessing,
        };
      }
    }
    return {
      ok: true, kind: req.kind, source: req.source,
      data: attachLocalProcessing(data, localProcessing),
      httpStatus: res.status, localProcessing,
    };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, kind: req.kind, source: req.source, error: message, localProcessing };
  }
}

export async function inspectorCommitOrThrow<T = unknown>(req: InspectorCommitRequest): Promise<T> {
  const result = await inspectorCommit<T>(req);
  if (!result.ok) throw new Error(result.error || 'Inspector commit failed');
  return result.data as T;
}
