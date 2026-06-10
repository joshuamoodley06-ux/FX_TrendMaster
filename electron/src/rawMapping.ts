export const RAW_EVENT_TYPES = [
  'SET_INITIAL_ANCHOR',
  'SET_ANCHOR',
  'ADJUST_ANCHOR',
  'MANUAL_BOS',
  'AUTO_BOS',
  'RECLAIM',
  'ABANDON_RANGE',
  'DELETE_RECORD',
  'NOTE',
] as const;

export type RawEventType = (typeof RAW_EVENT_TYPES)[number];

export const SEMANTIC_SIDES = ['HIGH', 'LOW', 'REF', 'UP', 'DOWN', 'NONE'] as const;
export type SemanticSide = (typeof SEMANTIC_SIDES)[number];

export const BACKEND_EVENT_SIDES = ['HIGH', 'LOW', 'NONE'] as const;
export type BackendEventSide = (typeof BACKEND_EVENT_SIDES)[number];

export type RawSource = 'manual' | 'auto' | 'system' | 'import';

export class RawMappingError extends Error {
  status?: number;
  payload?: unknown;

  constructor(message: string, options?: { status?: number; payload?: unknown }) {
    super(message);
    this.name = 'RawMappingError';
    this.status = options?.status;
    this.payload = options?.payload;
  }
}

export type RawMappingCaseCreateRequest = {
  symbol: string;
  case_name: string;
  base_timeframe: string;
  price_scale_default: number;
  notes?: string;
  case_id?: string;
};

export type RawMappingCase = {
  case_id: string;
  symbol: string;
  case_name: string;
  base_timeframe: string;
  price_scale_default: number;
  status?: string;
  notes?: string;
  schema_version?: string;
  created_at_utc_ms?: number;
  updated_at_utc_ms?: number | null;
};

export type RawMappingCaseCreateResponse = {
  ok: boolean;
  case?: RawMappingCase;
  case_id?: string;
  created?: boolean;
  error?: string;
  detail?: string;
  status?: number;
};

export type RawMappingEvent = {
  event_id: string;
  case_id: string;
  symbol: string;
  timeframe: string;
  candle_time_utc_ms: number;
  candle_index?: number | null;
  price?: number | null;
  price_int?: number | null;
  price_scale?: number | null;
  event_type: RawEventType | string;
  event_side: BackendEventSide | string;
  source: RawSource | string;
  created_order?: number;
  is_deleted?: number;
  supersedes_event_id?: string | null;
  schema_version?: string;
  notes?: string;
  created_at_utc_ms?: number;
  updated_at_utc_ms?: number | null;
  raw_payload_json?: string | Record<string, unknown> | null;
};

export type RawMappingEventCreateRequest = {
  event_id: string;
  case_id: string;
  symbol: string;
  timeframe: string;
  candle_time_utc_ms: number;
  candle_index?: number | null;
  price?: number | null;
  event_type: RawEventType;
  event_side: BackendEventSide;
  source: RawSource;
  supersedes_event_id?: string | null;
  notes?: string;
  raw_payload_json: Record<string, unknown>;
};

export type RawMappingEventCreateResponse = {
  ok: boolean;
  status?: number;
  event?: RawMappingEvent;
  duplicate?: boolean;
  error?: string;
  detail?: string;
};

export type RawMappingExportMeta = {
  case_id: string;
  schema_version: string;
  total_records: number;
  ledger_hash: string;
  case?: RawMappingCase;
};

export type RawMappingExportResponse = {
  ok: boolean;
  meta?: RawMappingExportMeta;
  sequence_by_intent?: RawMappingEvent[];
  sequence_by_timeline?: RawMappingEvent[];
  error?: string;
  detail?: string;
  status?: number;
};

export type BuildRawPayloadInput = {
  event_id: string;
  case_id: string;
  symbol: string;
  timeframe: string;
  candle_time_utc_ms: number;
  candle_index?: number | null;
  price?: number | null;
  event_type: RawEventType;
  semantic_side: SemanticSide;
  source?: RawSource;
  notes?: string;
  supersedes_event_id?: string | null;
  extra_payload?: Record<string, unknown>;
};

const ANCHOR_EVENT_TYPES = new Set<RawEventType>([
  'SET_INITIAL_ANCHOR',
  'SET_ANCHOR',
  'ADJUST_ANCHOR',
]);

function normalizeSemanticSide(side: string): SemanticSide {
  const normalized = String(side || 'NONE').toUpperCase() as SemanticSide;
  if (!SEMANTIC_SIDES.includes(normalized)) {
    throw new RawMappingError(`Invalid semantic_side: ${side}`);
  }
  return normalized;
}

function normalizeEventType(eventType: string): RawEventType {
  const normalized = String(eventType || '').toUpperCase() as RawEventType;
  if (!RAW_EVENT_TYPES.includes(normalized)) {
    throw new RawMappingError(`Invalid event_type: ${eventType}`);
  }
  return normalized;
}

export function toBackendSafeSide(
  semanticSide: SemanticSide,
): { event_side: BackendEventSide; semantic_side: SemanticSide } {
  const semantic = normalizeSemanticSide(semanticSide);

  if (semantic === 'HIGH') return { event_side: 'HIGH', semantic_side: 'HIGH' };
  if (semantic === 'LOW') return { event_side: 'LOW', semantic_side: 'LOW' };
  if (semantic === 'NONE') return { event_side: 'NONE', semantic_side: 'NONE' };
  if (semantic === 'REF') return { event_side: 'NONE', semantic_side: 'REF' };
  if (semantic === 'UP') return { event_side: 'HIGH', semantic_side: 'UP' };
  if (semantic === 'DOWN') return { event_side: 'LOW', semantic_side: 'DOWN' };

  throw new RawMappingError(`Unsupported semantic_side: ${semanticSide}`);
}

export function validateRawPayload(
  eventType: RawEventType,
  semanticSide: SemanticSide,
  rawPayloadJson: Record<string, unknown>,
  backendEventSide: BackendEventSide,
): void {
  if (!BACKEND_EVENT_SIDES.includes(backendEventSide)) {
    throw new RawMappingError(`Invalid backend event_side: ${backendEventSide}`);
  }

  if (ANCHOR_EVENT_TYPES.has(eventType)) {
    const payloadSemantic = String(rawPayloadJson.semantic_side || '').toUpperCase();
    if (!payloadSemantic) {
      throw new RawMappingError(`Anchor event ${eventType} must include semantic_side in raw_payload_json`);
    }
    if (semanticSide === 'REF') {
      const anchorRole = String(rawPayloadJson.anchor_role || '').toUpperCase();
      const hasRefSemantic = payloadSemantic === 'REF' || anchorRole === 'REF';
      if (!hasRefSemantic) {
        throw new RawMappingError('REF anchor events must include anchor_role: "REF" or semantic_side: "REF"');
      }
    }
  }

  if (eventType === 'AUTO_BOS') {
    const direction = String(rawPayloadJson.bos_direction || '').toUpperCase();
    if (direction !== 'UP' && direction !== 'DOWN') {
      throw new RawMappingError('AUTO_BOS events must include bos_direction: "UP" or "DOWN"');
    }
  }
}

export function buildRawPayloadJson(input: BuildRawPayloadInput): RawMappingEventCreateRequest {
  const eventType = normalizeEventType(input.event_type);
  const semanticSide = normalizeSemanticSide(input.semantic_side);
  const { event_side, semantic_side } = toBackendSafeSide(semanticSide);
  const source = (input.source || 'manual').toLowerCase() as RawSource;

  const raw_payload_json: Record<string, unknown> = {
    semantic_side: semantic_side,
    ...(input.extra_payload || {}),
  };

  if (semantic_side === 'REF') {
    raw_payload_json.anchor_role = 'REF';
  }

  if (eventType === 'AUTO_BOS') {
    if (semantic_side === 'UP' || semantic_side === 'DOWN') {
      raw_payload_json.bos_direction = semantic_side;
    } else {
      throw new RawMappingError('AUTO_BOS requires semantic_side UP or DOWN');
    }
  }

  validateRawPayload(eventType, semantic_side, raw_payload_json, event_side);

  if (input.extra_payload?.display_marker_id && String(input.extra_payload.display_marker_id) === String(input.event_id)) {
    throw new RawMappingError('display_marker_id must not equal event_id');
  }

  if (!input.case_id) throw new RawMappingError('Missing case_id');
  if (!input.event_id) throw new RawMappingError('Missing event_id');
  if (!input.symbol) throw new RawMappingError('Missing symbol');
  if (!input.timeframe) throw new RawMappingError('Missing timeframe');
  if (input.candle_time_utc_ms == null) throw new RawMappingError('Missing candle_time_utc_ms');

  return {
    event_id: String(input.event_id),
    case_id: String(input.case_id),
    symbol: String(input.symbol).toUpperCase(),
    timeframe: String(input.timeframe).toUpperCase(),
    candle_time_utc_ms: Number(input.candle_time_utc_ms),
    candle_index: input.candle_index ?? null,
    price: input.price ?? null,
    event_type: eventType,
    event_side,
    source,
    supersedes_event_id: input.supersedes_event_id ?? null,
    notes: input.notes || '',
    raw_payload_json,
  };
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T;
  } catch {
    throw new RawMappingError(`Invalid JSON response (HTTP ${response.status})`, { status: response.status });
  }
}

async function assertRawApiOk<T extends { ok?: boolean; error?: string; detail?: string }>(
  response: Response,
  payload: T,
  action: string,
): Promise<T> {
  if (!response.ok) {
    throw new RawMappingError(
      `${action} failed: HTTP ${response.status} ${response.statusText}`,
      { status: response.status, payload },
    );
  }
  if (!payload?.ok) {
    throw new RawMappingError(
      `${action} failed: ${payload?.error || payload?.detail || 'backend returned ok=false'}`,
      { status: response.status, payload },
    );
  }
  return payload;
}

export async function createRawCase(
  apiBase: string,
  payload: RawMappingCaseCreateRequest,
): Promise<RawMappingCaseCreateResponse> {
  const response = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/raw-mapping/cases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await parseJsonResponse<RawMappingCaseCreateResponse>(response);
  return assertRawApiOk(response, body, 'Create raw case');
}

export async function saveRawEvent(
  apiBase: string,
  payload: RawMappingEventCreateRequest,
): Promise<RawMappingEventCreateResponse> {
  const response = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/raw-mapping/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await parseJsonResponse<RawMappingEventCreateResponse>(response);
  return assertRawApiOk(response, body, 'Save raw event');
}

export async function deleteRawEvent(
  apiBase: string,
  caseId: string,
  eventId: string,
  notes = 'Deleted from Electron raw mapping UI',
): Promise<RawMappingEventCreateResponse> {
  const response = await fetch(`${apiBase.replace(/\/$/, '')}/api/v1/raw-mapping/events/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, event_id: eventId, notes }),
  });
  const body = await parseJsonResponse<RawMappingEventCreateResponse>(response);
  return assertRawApiOk(response, body, 'Delete raw event');
}

export async function exportRawCaseEvents(
  apiBase: string,
  caseId: string,
): Promise<RawMappingExportResponse> {
  const url = new URL(`${apiBase.replace(/\/$/, '')}/api/v1/raw-mapping/events/export`);
  url.searchParams.set('case_id', caseId);
  const response = await fetch(url.toString());
  const body = await parseJsonResponse<RawMappingExportResponse>(response);
  return assertRawApiOk(response, body, 'Export raw case events');
}
