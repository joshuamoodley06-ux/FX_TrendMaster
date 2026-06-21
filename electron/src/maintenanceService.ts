import { DEFAULT_VPS_BASE_URL } from './vpsConfig';

export const DEFAULT_MAINTENANCE_INTERVAL_MS = 60 * 60 * 1000;
export const DEFAULT_MAINTENANCE_TIMEOUT_MS = 45_000;
export const DEFAULT_RANGE_FETCH_LIMIT = 5000;
export const DEFAULT_SYMBOL_STORAGE_KEY = 'fx_tm_symbol';

/** Range auto-merge / consolidation suggestions are permanently disabled. */
export const AUTO_MERGE_ENABLED = false;

export type MaintenanceRangeRow = Record<string, unknown> & {
  range_id?: number | string;
  id?: number | string;
  parent_range_id?: number | string | null;
  structure_layer?: string;
  layer?: string;
  source_timeframe?: string;
  range_scope?: string;
  status?: string;
  case_id?: number | string | null;
  raw_case_id?: string | null;
  case_ref?: string | null;
  range_high_price?: number | string | null;
  range_low_price?: number | string | null;
  range_start_time?: string | null;
  range_end_time?: string | null;
  range_high_time?: string | null;
  range_low_time?: string | null;
  active_from_time?: string | null;
};

export type OrphanRangeFinding = {
  kind: 'missing_parent' | 'self_parent';
  range_id: string;
  parent_range_id: string;
  structure_layer: string;
  source_timeframe: string;
  range_scope: string;
  status: string;
  case_ref: string | null;
  message: string;
};

export type MergeOverlapSummary = {
  startMs: number;
  endMs: number;
  startIso: string;
  endIso: string;
  overlapMs: number;
  overlapRatioOfSmaller: number;
};

export type SuggestedMergeProposal = {
  range_high_price: number | null;
  range_low_price: number | null;
  range_start_time: string | null;
  range_end_time: string | null;
};

export type SuggestedMerge = {
  merge_id: string;
  reason: string;
  confidence: 'high' | 'medium' | 'low';
  structure_layer: string;
  parent_range_id: string | null;
  case_ref: string | null;
  range_ids: string[];
  ranges: Array<{
    range_id: string;
    status: string;
    range_scope: string;
    spanMs: number;
    range_start_time: string | null;
    range_end_time: string | null;
  }>;
  overlap: MergeOverlapSummary;
  proposed: SuggestedMergeProposal;
  warnings: string[];
  /** Maintenance is read-only — Pilot must confirm before any destructive action. */
  requires_user_confirmation: true;
};

export type MaintenanceReport = {
  ok: boolean;
  symbol: string;
  reason: string;
  generated_at: string;
  range_count: number;
  orphan_count: number;
  suggested_merge_count: number;
  orphans: OrphanRangeFinding[];
  suggested_merges: SuggestedMerge[];
  read_only: true;
  error?: string;
};

export type MaintenanceServiceStatus = {
  phase: 'idle' | 'running' | 'ready' | 'error';
  symbol?: string;
  reason?: string;
  lastRunAt?: string;
  lastError?: string;
  report?: MaintenanceReport | null;
};

export type MaintenanceServiceOptions = {
  baseUrl?: string;
  fetchTimeoutMs?: number;
  maintenanceIntervalMs?: number;
  symbolStorageKey?: string;
  rangeLimit?: number;
  onStatus?: (status: MaintenanceServiceStatus) => void;
};

export type RunMaintenanceOptions = {
  symbol?: string;
  case_id?: number | string | null;
  raw_case_id?: string | null;
  case_ref?: string | null;
  reason?: string;
  ranges?: MaintenanceRangeRow[];
};

export function normaliseMaintenanceSymbol(raw: unknown): string {
  return String(raw || 'XAUUSD').trim().toUpperCase();
}

export function getRangeRowId(row: MaintenanceRangeRow): string {
  return String(row.range_id ?? row.id ?? '').trim();
}

export function getRangeStructureLayer(row: MaintenanceRangeRow): string {
  return String(row.structure_layer || row.layer || '').trim().toUpperCase();
}

export function getRangeScope(row: MaintenanceRangeRow): string {
  return String(row.range_scope || 'MAJOR').trim().toUpperCase();
}

export function getRangeStatus(row: MaintenanceRangeRow): string {
  return String(row.status || 'ACTIVE').trim().toUpperCase();
}

export function buildRangeIdIndex(ranges: MaintenanceRangeRow[]): Map<string, MaintenanceRangeRow> {
  const index = new Map<string, MaintenanceRangeRow>();
  for (const row of ranges) {
    const id = getRangeRowId(row);
    if (id) index.set(id, row);
  }
  return index;
}

/** Identify ranges whose parent_range_id does not resolve to an existing range row. */
export function findOrphanRanges(ranges: MaintenanceRangeRow[]): OrphanRangeFinding[] {
  const index = buildRangeIdIndex(ranges);
  const orphans: OrphanRangeFinding[] = [];

  for (const row of ranges) {
    const rangeId = getRangeRowId(row);
    const parentRaw = row.parent_range_id;
    if (parentRaw == null || parentRaw === '') continue;

    const parentId = String(parentRaw).trim();
    if (!parentId) continue;

    if (rangeId && parentId === rangeId) {
      orphans.push({
        kind: 'self_parent',
        range_id: rangeId,
        parent_range_id: parentId,
        structure_layer: getRangeStructureLayer(row),
        source_timeframe: String(row.source_timeframe || ''),
        range_scope: getRangeScope(row),
        status: getRangeStatus(row),
        case_ref: row.case_ref != null ? String(row.case_ref) : null,
        message: `Range #${rangeId} references itself as parent.`,
      });
      continue;
    }

    if (!index.has(parentId)) {
      orphans.push({
        kind: 'missing_parent',
        range_id: rangeId || '(unknown)',
        parent_range_id: parentId,
        structure_layer: getRangeStructureLayer(row),
        source_timeframe: String(row.source_timeframe || ''),
        range_scope: getRangeScope(row),
        status: getRangeStatus(row),
        case_ref: row.case_ref != null ? String(row.case_ref) : null,
        message: `Range #${rangeId || '?'} references missing parent #${parentId}.`,
      });
    }
  }

  return orphans.sort((a, b) => a.range_id.localeCompare(b.range_id, undefined, { numeric: true }));
}

/**
 * Auto-merge disabled — returns no consolidation suggestions.
 * Mapping sessions and ranges are treated as distinct, additive records.
 */
export function findSuggestedMerges(
  _ranges: MaintenanceRangeRow[],
  _options?: {
    overlapRatioThreshold?: number;
    maxSmallSpanMsByLayer?: Record<string, number>;
  },
): SuggestedMerge[] {
  return [];
}

export function buildMaintenanceReport(
  symbol: string,
  ranges: MaintenanceRangeRow[],
  options?: {
    reason?: string;
  },
): MaintenanceReport {
  const orphans = findOrphanRanges(ranges);

  return {
    ok: true,
    symbol: normaliseMaintenanceSymbol(symbol),
    reason: options?.reason ?? 'maintenance_scan',
    generated_at: new Date().toISOString(),
    range_count: ranges.length,
    orphan_count: orphans.length,
    suggested_merge_count: 0,
    orphans,
    suggested_merges: [],
    read_only: true,
  };
}

export function buildMapRangesUrl(
  baseUrl: string,
  symbol: string,
  options?: {
    limit?: number;
    case_id?: number | string | null;
    raw_case_id?: string | null;
    case_ref?: string | null;
    structure_layer?: string | null;
    parent_range_id?: number | string | null;
  },
): string {
  const params = new URLSearchParams({
    symbol: normaliseMaintenanceSymbol(symbol),
    limit: String(Math.max(1, Math.min(options?.limit ?? DEFAULT_RANGE_FETCH_LIMIT, 5000))),
  });
  if (options?.case_id != null && options.case_id !== '') params.set('case_id', String(options.case_id));
  if (options?.raw_case_id) params.set('raw_case_id', String(options.raw_case_id));
  if (options?.case_ref) params.set('case_ref', String(options.case_ref));
  if (options?.structure_layer) params.set('structure_layer', String(options.structure_layer));
  if (options?.parent_range_id != null && options.parent_range_id !== '') {
    params.set('parent_range_id', String(options.parent_range_id));
  }
  return `${baseUrl.replace(/\/+$/, '')}/api/v1/map/ranges?${params.toString()}`;
}

export async function fetchMapRanges(
  symbol: string,
  options?: RunMaintenanceOptions & {
    baseUrl?: string;
    fetchTimeoutMs?: number;
    limit?: number;
  },
): Promise<{ ok: boolean; ranges: MaintenanceRangeRow[]; error?: string }> {
  const baseUrl = options?.baseUrl ?? DEFAULT_VPS_BASE_URL;
  const url = buildMapRangesUrl(baseUrl, symbol, {
    limit: options?.limit,
    case_id: options?.case_id,
    raw_case_id: options?.raw_case_id,
    case_ref: options?.case_ref,
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options?.fetchTimeoutMs ?? DEFAULT_MAINTENANCE_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) {
      return {
        ok: false,
        ranges: [],
        error: payload?.error || `HTTP ${response.status}`,
      };
    }
    const ranges = Array.isArray(payload?.ranges) ? payload.ranges as MaintenanceRangeRow[] : [];
    return { ok: true, ranges };
  } catch (err) {
    return {
      ok: false,
      ranges: [],
      error: err instanceof Error ? err.message : String(err),
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function runMaintenanceScan(
  options: RunMaintenanceOptions & {
    baseUrl?: string;
    fetchTimeoutMs?: number;
    rangeLimit?: number;
  } = {},
): Promise<MaintenanceReport> {
  const symbol = normaliseMaintenanceSymbol(options.symbol ?? 'XAUUSD');
  const reason = options.reason ?? 'manual_scan';

  let ranges = options.ranges ?? [];
  if (!ranges.length) {
    const fetched = await fetchMapRanges(symbol, options);
    if (!fetched.ok) {
      return {
        ok: false,
        symbol,
        reason,
        generated_at: new Date().toISOString(),
        range_count: 0,
        orphan_count: 0,
        suggested_merge_count: 0,
        orphans: [],
        suggested_merges: [],
        read_only: true,
        error: fetched.error || 'Failed to fetch map ranges',
      };
    }
    ranges = fetched.ranges;
  }

  return buildMaintenanceReport(symbol, ranges, {
    reason,
  });
}

export class MaintenanceService {
  private readonly options: Required<Pick<MaintenanceServiceOptions, 'baseUrl' | 'fetchTimeoutMs' | 'maintenanceIntervalMs' | 'symbolStorageKey' | 'rangeLimit'>> &
    Pick<MaintenanceServiceOptions, 'onStatus'>;
  private activeSymbol: string | null = null;
  private inFlight: Promise<MaintenanceReport> | null = null;
  private intervalTimer: ReturnType<typeof setInterval> | null = null;
  private status: MaintenanceServiceStatus = { phase: 'idle', report: null };

  constructor(options: MaintenanceServiceOptions = {}) {
    this.options = {
      baseUrl: options.baseUrl ?? DEFAULT_VPS_BASE_URL,
      fetchTimeoutMs: options.fetchTimeoutMs ?? DEFAULT_MAINTENANCE_TIMEOUT_MS,
      maintenanceIntervalMs: options.maintenanceIntervalMs ?? DEFAULT_MAINTENANCE_INTERVAL_MS,
      symbolStorageKey: options.symbolStorageKey ?? DEFAULT_SYMBOL_STORAGE_KEY,
      rangeLimit: options.rangeLimit ?? DEFAULT_RANGE_FETCH_LIMIT,
      onStatus: options.onStatus,
    };
  }

  getStatus(): MaintenanceServiceStatus {
    return { ...this.status, report: this.status.report ? { ...this.status.report } : null };
  }

  private emitStatus(patch: Partial<MaintenanceServiceStatus>): void {
    this.status = { ...this.status, ...patch };
    this.options.onStatus?.(this.getStatus());
  }

  readStoredSymbol(): string {
    if (typeof window === 'undefined') return 'XAUUSD';
    try {
      const raw = window.localStorage.getItem(this.options.symbolStorageKey);
      if (!raw) return 'XAUUSD';
      return normaliseMaintenanceSymbol(JSON.parse(raw));
    } catch {
      return 'XAUUSD';
    }
  }

  start(initialSymbol?: string): void {
    this.activeSymbol = normaliseMaintenanceSymbol(initialSymbol ?? this.readStoredSymbol());
    this.startIntervalTimer();
    void this.run({ symbol: this.activeSymbol, reason: 'app_start' });
  }

  onSymbolSelected(symbol: string): void {
    const next = normaliseMaintenanceSymbol(symbol);
    this.activeSymbol = next;
    void this.run({ symbol: next, reason: 'symbol_selected' });
  }

  stop(): void {
    if (this.intervalTimer) clearInterval(this.intervalTimer);
    this.intervalTimer = null;
    this.inFlight = null;
    this.emitStatus({ phase: 'idle' });
  }

  async run(options: RunMaintenanceOptions = {}): Promise<MaintenanceReport> {
    const symbol = normaliseMaintenanceSymbol(options.symbol ?? this.activeSymbol ?? this.readStoredSymbol());
    if (this.inFlight && this.activeSymbol === symbol) {
      return this.inFlight;
    }

    this.activeSymbol = symbol;
    this.emitStatus({ phase: 'running', symbol, reason: options.reason, lastError: undefined });

    const runPromise = runMaintenanceScan({
      ...options,
      symbol,
      baseUrl: this.options.baseUrl,
      fetchTimeoutMs: this.options.fetchTimeoutMs,
      rangeLimit: this.options.rangeLimit,
    }).then((report) => {
      this.emitStatus({
        phase: report.ok ? 'ready' : 'error',
        symbol,
        lastRunAt: report.generated_at,
        lastError: report.error,
        report,
      });
      return report;
    }).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      const failed: MaintenanceReport = {
        ok: false,
        symbol,
        reason: options.reason ?? 'maintenance_scan',
        generated_at: new Date().toISOString(),
        range_count: 0,
        orphan_count: 0,
        suggested_merge_count: 0,
        orphans: [],
        suggested_merges: [],
        read_only: true,
        error: message,
      };
      this.emitStatus({ phase: 'error', symbol, lastError: message, report: failed });
      return failed;
    }).finally(() => {
      if (this.inFlight === runPromise) this.inFlight = null;
    });

    this.inFlight = runPromise;
    return runPromise;
  }

  private startIntervalTimer(): void {
    if (this.intervalTimer) clearInterval(this.intervalTimer);
    if (!this.options.maintenanceIntervalMs || this.options.maintenanceIntervalMs <= 0) return;
    this.intervalTimer = setInterval(() => {
      const symbol = this.activeSymbol ?? this.readStoredSymbol();
      void this.run({ symbol, reason: 'interval' });
    }, this.options.maintenanceIntervalMs);
  }
}

let defaultMaintenanceService: MaintenanceService | null = null;
let maintenanceBootstrapCleanup: (() => void) | null = null;

export function getMaintenanceService(options?: MaintenanceServiceOptions): MaintenanceService {
  if (!defaultMaintenanceService) {
    defaultMaintenanceService = new MaintenanceService(options);
  }
  return defaultMaintenanceService;
}

/** Opt-in background maintenance scans (read-only reports). Disabled unless explicitly started. */
export function initBackgroundMaintenance(options?: MaintenanceServiceOptions): () => void {
  if (maintenanceBootstrapCleanup) maintenanceBootstrapCleanup();
  const service = getMaintenanceService(options);
  service.start();
  maintenanceBootstrapCleanup = () => {
    service.stop();
    maintenanceBootstrapCleanup = null;
  };
  return maintenanceBootstrapCleanup;
}
