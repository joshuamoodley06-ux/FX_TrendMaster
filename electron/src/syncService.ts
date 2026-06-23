import { DEFAULT_VPS_BASE_URL, resolveVpsBaseUrl } from './vpsConfig';
import {
  type CandleSyncStateRow,
  type CandlesUpsertRequest,
  type CandlesUpsertResult,
  type UpsertCandleRow,
  fetchLocalCandles,
  getLocalCandlesStatus,
  upsertLocalCandles,
} from './localResearchClient';
import { loadMappingSession, type MappingSessionState } from './mappingSessionPersistence';
import type { MappingDraft } from './types';

export const DEFAULT_SYNC_TIMEFRAMES = ['MN1', 'W1', 'D1', 'H4', 'H1', 'M15'] as const;
/** Chart library TFs — M1 excluded; MN1 deferred. */
export const CHART_LIBRARY_TIMEFRAMES = ['M15', 'H1', 'H4', 'D1', 'W1'] as const;
export const INCREMENTAL_DELTA_LIMIT = 24;
export const INITIAL_BOOTSTRAP_LIMIT = 500;
export const DEFAULT_SYNC_LIMIT = 8000;
export const DEFAULT_SYNC_TIMEOUT_MS = 45_000;
export const DEFAULT_RESYNC_INTERVAL_MS = 5 * 60 * 1000;
export const DEFAULT_SYMBOL_STORAGE_KEY = 'fx_tm_symbol';
export const DEFAULT_WARM_BOOT_SYMBOL = 'XAUUSD';
export const DEFAULT_WARM_BOOT_TIMEFRAME = 'D1';
export const DEFAULT_FALLBACK_SYMBOLS = ['XAUUSD', 'US500.CASH'] as const;
export const RAW_CASE_STORAGE_KEY = 'fx_tm_raw_active_case_id_v087_29c';
export const MAPPING_DRAFTS_STORAGE_KEY = 'fx_tm_mapping_drafts_v1';
export {
  MAPPING_DATA_STORAGE_KEY,
  clearMappingEventsForContainer,
  isMappingEventsScopeHydrated,
  mappingEventsScopeKey,
  resolveActiveCaseDisplayId,
} from './mappingEventsPersistence';
export { STALE_CACHE_BLOCKED, clearAllUIAnchors } from './clearAllUIAnchors';

export type VpsCandleRow = {
  symbol?: string;
  timeframe?: string;
  time?: string;
  timestamp?: string;
  date?: string;
  open?: number | string;
  high?: number | string;
  low?: number | string;
  close?: number | string;
  volume?: number | string;
  tick_volume?: number | string;
  source?: string;
};

export type VpsCandlesResponse = {
  ok?: boolean;
  symbol?: string;
  timeframe?: string;
  count?: number;
  candles?: VpsCandleRow[];
  error?: string;
};

export type TimeframeSyncResult = {
  timeframe: string;
  ok: boolean;
  fetched: number;
  upserted: number;
  skipped: number;
  lastTime?: string | null;
  error?: string;
};

export type SymbolSyncResult = {
  ok: boolean;
  symbol: string;
  reason: string;
  totalFetched: number;
  totalUpserted: number;
  totalSkipped: number;
  results: TimeframeSyncResult[];
  error?: string;
};

export type SyncServiceStatus = {
  phase: 'idle' | 'syncing' | 'ready' | 'error';
  symbol?: string;
  reason?: string;
  lastSyncAt?: string;
  lastError?: string;
  results?: TimeframeSyncResult[];
};

export type SyncServiceOptions = {
  baseUrl?: string;
  timeframes?: readonly string[];
  limit?: number;
  fetchTimeoutMs?: number;
  resyncIntervalMs?: number;
  source?: string;
  symbolStorageKey?: string;
  onStatus?: (status: SyncServiceStatus) => void;
};

export type FetchSymbolsResult = {
  ok: boolean;
  symbols: string[];
  source: 'vps' | 'fallback';
  error?: string;
};

export type LoadChartDataResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  candleCount: number;
  sync: TimeframeSyncResult;
  localOk: boolean;
  error?: string;
};

export type SyncDraftStateResult = {
  ok: boolean;
  caseId: string | null;
  session: MappingSessionState | null;
  drafts: Record<string, MappingDraft>;
  draftTimeframes: string[];
  warnings: string[];
  error?: string;
};

export type WarmBootResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  caseId: string | null;
  symbols: string[];
  candleCount: number;
  draftTimeframes: string[];
  sessionRestored: boolean;
  resets: string[];
  warnings: string[];
  errors: string[];
};

export type WarmBootOptions = {
  baseUrl?: string;
  symbol?: string;
  timeframe?: string;
  caseId?: string | number | null;
  limit?: number;
  fetchTimeoutMs?: number;
  source?: string;
  symbolStorageKey?: string;
};

export function normaliseSyncSymbol(raw: unknown): string {
  return String(raw || 'XAUUSD').trim().toUpperCase();
}

export function normaliseSyncTimeframe(raw: unknown): string {
  return String(raw || 'D1').trim().toUpperCase();
}

/** Convert ISO / YYYY-MM-DD timestamps to MT5-style storage keys used by the local cache. */
export function normaliseUpsertCandleTime(raw: unknown): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  if (/^\d{4}\.\d{2}\.\d{2}/.test(text)) return text;
  const isoCandidate = text.includes('T') ? text : text.replace(' ', 'T');
  const parsed = new Date(isoCandidate.endsWith('Z') ? isoCandidate : `${isoCandidate}Z`);
  if (Number.isNaN(parsed.getTime())) return text;
  const y = parsed.getUTCFullYear();
  const mo = String(parsed.getUTCMonth() + 1).padStart(2, '0');
  const d = String(parsed.getUTCDate()).padStart(2, '0');
  const h = String(parsed.getUTCHours()).padStart(2, '0');
  const mi = String(parsed.getUTCMinutes()).padStart(2, '0');
  return `${y}.${mo}.${d} ${h}:${mi}`;
}

function parseFiniteNumber(raw: unknown): number | null {
  if (raw == null || raw === '') return null;
  const value = Number(String(raw).replace(',', '.'));
  return Number.isFinite(value) ? value : null;
}

export function transformVpsCandleRow(
  raw: VpsCandleRow,
  defaults: { symbol: string; timeframe: string; source?: string },
): UpsertCandleRow | null {
  const time = normaliseUpsertCandleTime(raw.time ?? raw.timestamp ?? raw.date);
  const open = parseFiniteNumber(raw.open);
  const high = parseFiniteNumber(raw.high);
  const low = parseFiniteNumber(raw.low);
  const close = parseFiniteNumber(raw.close);
  if (!time || open === null || high === null || low === null || close === null) {
    return null;
  }
  const volumeRaw = raw.volume ?? raw.tick_volume;
  const volume = parseFiniteNumber(volumeRaw);
  const isClosedRaw = (raw as { is_closed?: unknown; isClosed?: unknown }).is_closed
    ?? (raw as { isClosed?: unknown }).isClosed;
  const isClosed = isClosedRaw === false || isClosedRaw === 0 || isClosedRaw === '0' ? 0 : 1;
  return {
    symbol: normaliseSyncSymbol(raw.symbol ?? defaults.symbol),
    timeframe: normaliseSyncTimeframe(raw.timeframe ?? defaults.timeframe),
    time,
    open,
    high,
    low,
    close,
    volume: volume ?? 0,
    source: String(raw.source ?? defaults.source ?? 'vps-sync'),
    is_closed: isClosed,
  };
}

export function buildVpsCandlesUrl(
  baseUrl: string,
  symbol: string,
  timeframe: string,
  options?: { limit?: number; start?: string; end?: string; refresh?: boolean },
): string {
  const params = new URLSearchParams({
    symbol: normaliseSyncSymbol(symbol),
    timeframe: normaliseSyncTimeframe(timeframe),
    limit: String(Math.max(1, Math.min(options?.limit ?? DEFAULT_SYNC_LIMIT, 10_000))),
  });
  if (options?.start) params.set('start', options.start);
  if (options?.end) params.set('end', options.end);
  if (options?.refresh) params.set('refresh', '1');
  return `${baseUrl.replace(/\/+$/, '')}/api/v1/candles?${params.toString()}`;
}

export function buildUpsertPayloadFromVpsResponse(
  response: VpsCandlesResponse,
  defaults: { symbol: string; timeframe: string; source?: string; mode?: string },
): CandlesUpsertRequest | null {
  const rows = Array.isArray(response.candles) ? response.candles : [];
  if (!rows.length && response.ok === false) return null;

  const candles: UpsertCandleRow[] = [];
  for (const raw of rows) {
    const row = transformVpsCandleRow(raw, defaults);
    if (row) candles.push(row);
  }
  if (!candles.length) return null;

  const lastTime = candles[candles.length - 1]?.time ?? null;
  const syncState: CandleSyncStateRow = {
    symbol: normaliseSyncSymbol(defaults.symbol),
    timeframe: normaliseSyncTimeframe(defaults.timeframe),
    last_time: lastTime,
    bar_count: candles.length,
    last_sync_at: new Date().toISOString(),
    last_mode: defaults.mode ?? 'vps_pull',
    last_error: null,
  };

  return {
    candles,
    symbol: syncState.symbol,
    timeframe: syncState.timeframe,
    source: defaults.source ?? 'vps-sync',
    syncState,
  };
}

export async function fetchVpsCandles(
  symbol: string,
  timeframe: string,
  options?: {
    baseUrl?: string;
    limit?: number;
    start?: string;
    end?: string;
    refresh?: boolean;
    fetchTimeoutMs?: number;
  },
): Promise<VpsCandlesResponse> {
  const baseUrl = options?.baseUrl ?? resolveVpsBaseUrl();
  const url = buildVpsCandlesUrl(baseUrl, symbol, timeframe, options);
  const controller = new AbortController();
  const timeoutMs = options?.fetchTimeoutMs ?? DEFAULT_SYNC_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) {
      return {
        ok: false,
        symbol: normaliseSyncSymbol(symbol),
        timeframe: normaliseSyncTimeframe(timeframe),
        candles: [],
        error: payload?.error || `HTTP ${response.status}`,
      };
    }
    return payload as VpsCandlesResponse;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      symbol: normaliseSyncSymbol(symbol),
      timeframe: normaliseSyncTimeframe(timeframe),
      candles: [],
      error: message,
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function syncTimeframeFromVps(
  symbol: string,
  timeframe: string,
  options?: SyncServiceOptions & { reason?: string; refresh?: boolean; mode?: string },
): Promise<TimeframeSyncResult> {
  const tf = normaliseSyncTimeframe(timeframe);
  const sym = normaliseSyncSymbol(symbol);
  const source = options?.source ?? 'vps-sync';
  const reason = options?.reason ?? 'timeframe_sync';
  const mode = options?.mode ?? reason;

  const remote = await fetchVpsCandles(sym, tf, {
    baseUrl: options?.baseUrl,
    limit: options?.limit ?? DEFAULT_SYNC_LIMIT,
    refresh: options?.refresh,
    fetchTimeoutMs: options?.fetchTimeoutMs,
  });

  return applyVpsCandlesToLocalCache(sym, tf, remote, { source, mode, reason });
}

export function mergeParsedCandleRows<T extends { time: string }>(left: T[], right: T[]): T[] {
  const byTime = new Map<string, T>();
  for (const row of left) byTime.set(String(row.time), row);
  for (const row of right) byTime.set(String(row.time), row);
  return Array.from(byTime.values()).sort(
    (a, b) => new Date(String(a.time)).getTime() - new Date(String(b.time)).getTime(),
  );
}

async function applyVpsCandlesToLocalCache(
  sym: string,
  tf: string,
  remote: VpsCandlesResponse,
  defaults: { source: string; mode: string; reason: string },
): Promise<TimeframeSyncResult> {
  const payload = buildUpsertPayloadFromVpsResponse(remote, {
    symbol: sym,
    timeframe: tf,
    source: defaults.source,
    mode: defaults.mode,
  });

  if (!payload) {
    return {
      timeframe: tf,
      ok: false,
      fetched: 0,
      upserted: 0,
      skipped: 0,
      error: remote.error || 'VPS returned no candles',
    };
  }

  const status = await getLocalCandlesStatus(sym, tf);
  const priorCount = Number(status.symbolCandles ?? 0);
  payload.syncState = {
    ...payload.syncState!,
    bar_count: Math.max(priorCount, payload.candles.length),
    last_mode: defaults.mode,
  };

  const upsert: CandlesUpsertResult = await upsertLocalCandles(payload);
  if (!upsert.ok) {
    return {
      timeframe: tf,
      ok: false,
      fetched: payload.candles.length,
      upserted: 0,
      skipped: payload.candles.length,
      error: upsert.error || 'Local candle upsert failed',
    };
  }

  return {
    timeframe: tf,
    ok: true,
    fetched: payload.candles.length,
    upserted: upsert.upserted,
    skipped: upsert.skipped,
    lastTime: payload.syncState?.last_time ?? null,
  };
}

/** Incremental VPS pull — latest delta only, not full history. */
export async function syncIncrementalDeltaFromVps(
  symbol: string,
  timeframe: string,
  options?: SyncServiceOptions & { reason?: string; mode?: string; quiet?: boolean },
): Promise<TimeframeSyncResult> {
  const sym = normaliseSyncSymbol(symbol);
  const tf = normaliseSyncTimeframe(timeframe);
  const status = await getLocalCandlesStatus(sym, tf);
  const lastTime = status.syncState?.last_time ?? status.lastTime ?? null;
  const limit = INCREMENTAL_DELTA_LIMIT;
  const remote = await fetchVpsCandles(sym, tf, {
    baseUrl: options?.baseUrl,
    limit,
    start: lastTime || undefined,
    refresh: false,
    fetchTimeoutMs: options?.fetchTimeoutMs,
  });

  return applyVpsCandlesToLocalCache(sym, tf, remote, {
    source: options?.source ?? 'vps-sync',
    mode: options?.mode ?? 'incremental_delta',
    reason: options?.reason ?? 'incremental_delta',
  });
}

/** Fetch only a missing chart window from VPS — used when local library has no bars for span. */
export async function syncMissingWindowFromVps(
  symbol: string,
  timeframe: string,
  window: { start?: string; end?: string },
  options?: SyncServiceOptions & { reason?: string; mode?: string },
): Promise<TimeframeSyncResult> {
  const sym = normaliseSyncSymbol(symbol);
  const tf = normaliseSyncTimeframe(timeframe);
  const remote = await fetchVpsCandles(sym, tf, {
    baseUrl: options?.baseUrl,
    limit: options?.limit ?? 2000,
    start: window.start,
    end: window.end,
    refresh: false,
    fetchTimeoutMs: options?.fetchTimeoutMs,
  });

  return applyVpsCandlesToLocalCache(sym, tf, remote, {
    source: options?.source ?? 'vps-sync',
    mode: options?.mode ?? 'missing_window',
    reason: options?.reason ?? 'missing_window',
  });
}

/** First-time bootstrap for empty local library — moderate limit, not full 8000 history. */
export async function syncBootstrapTimeframeFromVps(
  symbol: string,
  timeframe: string,
  options?: SyncServiceOptions & { reason?: string },
): Promise<TimeframeSyncResult> {
  const sym = normaliseSyncSymbol(symbol);
  const tf = normaliseSyncTimeframe(timeframe);
  const status = await getLocalCandlesStatus(sym, tf);
  if (Number(status.symbolCandles ?? 0) > 0) {
    return syncIncrementalDeltaFromVps(sym, tf, { ...options, reason: options?.reason ?? 'bootstrap_skip' });
  }
  const remote = await fetchVpsCandles(sym, tf, {
    baseUrl: options?.baseUrl,
    limit: options?.limit ?? INITIAL_BOOTSTRAP_LIMIT,
    refresh: false,
    fetchTimeoutMs: options?.fetchTimeoutMs,
  });
  return applyVpsCandlesToLocalCache(sym, tf, remote, {
    source: options?.source ?? 'vps-sync',
    mode: 'initial_bootstrap',
    reason: options?.reason ?? 'initial_bootstrap',
  });
}

export async function syncSymbolFromVps(
  symbol: string,
  options?: SyncServiceOptions & { reason?: string; refresh?: boolean },
): Promise<SymbolSyncResult> {
  const sym = normaliseSyncSymbol(symbol);
  const timeframes = options?.timeframes ?? DEFAULT_SYNC_TIMEFRAMES;
  const reason = options?.reason ?? 'symbol_sync';
  const results: TimeframeSyncResult[] = [];

  for (const timeframe of timeframes) {
    const tf = normaliseSyncTimeframe(timeframe);
    if (!tf) continue;
    results.push(await syncBootstrapTimeframeFromVps(sym, tf, { ...options, reason }));
  }

  const totalFetched = results.reduce((sum, row) => sum + row.fetched, 0);
  const totalUpserted = results.reduce((sum, row) => sum + row.upserted, 0);
  const totalSkipped = results.reduce((sum, row) => sum + row.skipped, 0);
  const ok = results.some((row) => row.ok);
  const errors = results.filter((row) => row.error).map((row) => `${row.timeframe}: ${row.error}`);

  return {
    ok,
    symbol: sym,
    reason,
    totalFetched,
    totalUpserted,
    totalSkipped,
    results,
    error: errors.length ? errors.join('; ') : undefined,
  };
}

function readJsonStorage(key: string): unknown {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeJsonStorage(key: string, value: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readStoredWarmBootTimeframe(): string {
  const session = loadMappingSession();
  if (session?.chart_timeframe) {
    return normaliseSyncTimeframe(session.chart_timeframe);
  }
  return DEFAULT_WARM_BOOT_TIMEFRAME;
}

export function readStoredWarmBootCaseId(): string | null {
  const fromStorage = readJsonStorage(RAW_CASE_STORAGE_KEY);
  if (typeof fromStorage === 'string' && fromStorage.trim()) {
    return fromStorage.trim();
  }
  const session = loadMappingSession();
  if (session?.raw_case_id) return String(session.raw_case_id);
  if (session?.case_id != null && session.case_id !== '') {
    return String(session.case_id);
  }
  return null;
}

export function writeStoredWarmBootSymbol(
  symbol: string,
  symbolStorageKey = DEFAULT_SYMBOL_STORAGE_KEY,
): void {
  writeJsonStorage(symbolStorageKey, normaliseSyncSymbol(symbol));
}

export function writeStoredWarmBootCaseId(caseId: string | null): void {
  writeJsonStorage(RAW_CASE_STORAGE_KEY, caseId ?? '');
}

export function draftContainerKey(symbol: string, caseId?: string | null): string {
  return `${normaliseSyncSymbol(symbol)}|${String(caseId ?? '')}`;
}

export function readStoredMappingDrafts(
  symbol: string,
  caseId?: string | null,
): Record<string, MappingDraft> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(MAPPING_DRAFTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Record<string, MappingDraft>>;
    return parsed[draftContainerKey(symbol, caseId)] || {};
  } catch {
    return {};
  }
}

export function resolveSymbolForWarmBoot(
  storedSymbol: string,
  availableSymbols: readonly string[],
  defaultSymbol: string = DEFAULT_WARM_BOOT_SYMBOL,
): { symbol: string; reset: boolean; previous?: string } {
  const normalised = normaliseSyncSymbol(storedSymbol);
  const available = new Set(availableSymbols.map((row) => normaliseSyncSymbol(row)));
  if (available.has(normalised)) {
    return { symbol: normalised, reset: false };
  }

  const fallback = normaliseSyncSymbol(defaultSymbol);
  if (available.has(fallback)) {
    return { symbol: fallback, reset: true, previous: normalised };
  }

  const first = availableSymbols[0];
  return {
    symbol: normaliseSyncSymbol(first || fallback),
    reset: true,
    previous: normalised,
  };
}

export async function fetchSymbols(
  options?: { baseUrl?: string; fetchTimeoutMs?: number },
): Promise<FetchSymbolsResult> {
  const fallback = [...DEFAULT_FALLBACK_SYMBOLS];
  const baseUrl = options?.baseUrl ?? resolveVpsBaseUrl();
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    options?.fetchTimeoutMs ?? DEFAULT_SYNC_TIMEOUT_MS,
  );

  try {
    const response = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/v1/candles/status`, {
      signal: controller.signal,
    });
    const payload = await response.json();
    const fromVps = new Set<string>();
    for (const group of Array.isArray(payload?.groups) ? payload.groups : []) {
      if (group?.symbol) fromVps.add(normaliseSyncSymbol(group.symbol));
    }

    const symbols = [...new Set([...fromVps, ...fallback.map(normaliseSyncSymbol)])];
    return {
      ok: true,
      symbols,
      source: fromVps.size > 0 ? 'vps' : 'fallback',
      error: response.ok ? undefined : payload?.error || `HTTP ${response.status}`,
    };
  } catch (err) {
    return {
      ok: true,
      symbols: fallback.map(normaliseSyncSymbol),
      source: 'fallback',
      error: err instanceof Error ? err.message : String(err),
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function loadChartData(
  symbol: string,
  timeframe: string,
  options?: SyncServiceOptions & { reason?: string; refresh?: boolean },
): Promise<LoadChartDataResult> {
  const sym = normaliseSyncSymbol(symbol);
  const tf = normaliseSyncTimeframe(timeframe);

  const localFirst = await fetchLocalCandles(sym, tf, { limit: options?.limit ?? DEFAULT_SYNC_LIMIT });
  let candleCount = Array.isArray(localFirst.candles) ? localFirst.candles.length : 0;
  if (localFirst.ok && candleCount > 0) {
    return {
      ok: true,
      symbol: sym,
      timeframe: tf,
      candleCount,
      sync: { timeframe: tf, ok: true, fetched: 0, upserted: 0, skipped: 0 },
      localOk: true,
    };
  }

  const sync = await syncBootstrapTimeframeFromVps(sym, tf, {
    ...options,
    reason: options?.reason ?? 'warm_boot_chart',
  });

  const local = await fetchLocalCandles(sym, tf, { limit: options?.limit ?? DEFAULT_SYNC_LIMIT });
  candleCount = Array.isArray(local.candles) ? local.candles.length : 0;
  const ok = sync.ok || (local.ok && candleCount > 0);

  return {
    ok,
    symbol: sym,
    timeframe: tf,
    candleCount,
    sync,
    localOk: local.ok,
    error: ok ? undefined : sync.error || local.error || 'No chart candles available',
  };
}

export async function syncDraftState(
  caseId: string | number | null | undefined,
  options?: {
    symbol?: string;
  },
): Promise<SyncDraftStateResult> {
  const symbol = normaliseSyncSymbol(options?.symbol ?? DEFAULT_WARM_BOOT_SYMBOL);
  const session = loadMappingSession();
  const resolvedCaseId = caseId != null && String(caseId).trim() !== ''
    ? String(caseId).trim()
    : readStoredWarmBootCaseId();

  const drafts = readStoredMappingDrafts(symbol, resolvedCaseId);

  return {
    ok: true,
    caseId: resolvedCaseId,
    session,
    drafts,
    draftTimeframes: Object.keys(drafts),
    warnings: [],
  };
}

export async function runWarmBoot(options: WarmBootOptions = {}): Promise<WarmBootResult> {
  const resets: string[] = [];
  const warnings: string[] = [];
  const errors: string[] = [];
  const symbolStorageKey = options.symbolStorageKey ?? DEFAULT_SYMBOL_STORAGE_KEY;

  const symbolsResult = await fetchSymbols({
    baseUrl: options.baseUrl,
    fetchTimeoutMs: options.fetchTimeoutMs,
  });
  if (symbolsResult.error && symbolsResult.source === 'fallback') {
    warnings.push(`Symbol list fallback used: ${symbolsResult.error}`);
  }

  const storedSymbol = options.symbol ?? readStoredWarmBootSymbol(symbolStorageKey);
  const symbolResolution = resolveSymbolForWarmBoot(storedSymbol, symbolsResult.symbols);
  let symbol = symbolResolution.symbol;
  if (symbolResolution.reset) {
    resets.push(
      symbolResolution.previous
        ? `Symbol ${symbolResolution.previous} is unavailable — reset to ${symbol}.`
        : `Stored symbol unavailable — reset to ${symbol}.`,
    );
    writeStoredWarmBootSymbol(symbol, symbolStorageKey);
  }

  let timeframe = normaliseSyncTimeframe(
    options.timeframe ?? readStoredWarmBootTimeframe(),
  );
  let caseId = options.caseId != null && String(options.caseId).trim() !== ''
    ? String(options.caseId).trim()
    : readStoredWarmBootCaseId();

  let chart = await loadChartData(symbol, timeframe, {
    baseUrl: options.baseUrl,
    limit: options.limit,
    fetchTimeoutMs: options.fetchTimeoutMs,
    source: options.source,
    reason: 'warm_boot',
  });

  if (!chart.ok) {
    errors.push(chart.error || `Chart load failed for ${symbol} ${timeframe}`);
    const defaultSymbol = DEFAULT_WARM_BOOT_SYMBOL;
    const defaultTimeframe = DEFAULT_WARM_BOOT_TIMEFRAME;
    if (symbol !== defaultSymbol || timeframe !== defaultTimeframe) {
      const retry = await loadChartData(defaultSymbol, defaultTimeframe, {
        baseUrl: options.baseUrl,
        limit: options.limit,
        fetchTimeoutMs: options.fetchTimeoutMs,
        source: options.source,
        reason: 'warm_boot_fallback',
      });
      if (retry.ok) {
        chart = retry;
        symbol = defaultSymbol;
        timeframe = defaultTimeframe;
        resets.push(`Chart data unavailable for previous selection — reset to ${symbol} ${timeframe}.`);
        writeStoredWarmBootSymbol(symbol, symbolStorageKey);
      } else {
        errors.push(retry.error || `Fallback chart load failed for ${defaultSymbol} ${defaultTimeframe}`);
      }
    }
  }

  const draft = await syncDraftState(caseId, { symbol });
  warnings.push(...draft.warnings);
  caseId = draft.caseId;

  const ok = chart.ok && draft.ok;
  return {
    ok,
    symbol,
    timeframe,
    caseId,
    symbols: symbolsResult.symbols,
    candleCount: chart.candleCount,
    draftTimeframes: draft.draftTimeframes,
    sessionRestored: draft.session != null,
    resets,
    warnings,
    errors,
  };
}

function readStoredWarmBootSymbol(symbolStorageKey: string): string {
  if (typeof window === 'undefined') return DEFAULT_WARM_BOOT_SYMBOL;
  try {
    const raw = window.localStorage.getItem(symbolStorageKey);
    if (!raw) return DEFAULT_WARM_BOOT_SYMBOL;
    return normaliseSyncSymbol(JSON.parse(raw));
  } catch {
    return DEFAULT_WARM_BOOT_SYMBOL;
  }
}

export class SyncService {
  private readonly options: Required<Pick<SyncServiceOptions, 'baseUrl' | 'timeframes' | 'limit' | 'fetchTimeoutMs' | 'resyncIntervalMs' | 'source' | 'symbolStorageKey'>> &
    Pick<SyncServiceOptions, 'onStatus'>;
  private activeSymbol: string | null = null;
  private inFlight: Promise<SymbolSyncResult> | null = null;
  private resyncTimer: ReturnType<typeof setInterval> | null = null;
  private symbolPollTimer: ReturnType<typeof setInterval> | null = null;
  private symbolDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPolledSymbol: string | null = null;
  private status: SyncServiceStatus = { phase: 'idle' };

  constructor(options: SyncServiceOptions = {}) {
    this.options = {
      baseUrl: options.baseUrl ?? resolveVpsBaseUrl(),
      timeframes: options.timeframes ?? DEFAULT_SYNC_TIMEFRAMES,
      limit: options.limit ?? DEFAULT_SYNC_LIMIT,
      fetchTimeoutMs: options.fetchTimeoutMs ?? DEFAULT_SYNC_TIMEOUT_MS,
      resyncIntervalMs: options.resyncIntervalMs ?? DEFAULT_RESYNC_INTERVAL_MS,
      source: options.source ?? 'vps-sync',
      symbolStorageKey: options.symbolStorageKey ?? DEFAULT_SYMBOL_STORAGE_KEY,
      onStatus: options.onStatus,
    };
  }

  getStatus(): SyncServiceStatus {
    return { ...this.status };
  }

  private emitStatus(patch: Partial<SyncServiceStatus>): void {
    this.status = { ...this.status, ...patch };
    this.options.onStatus?.(this.getStatus());
  }

  readStoredSymbol(): string {
    return readStoredWarmBootSymbol(this.options.symbolStorageKey);
  }

  writeStoredSymbol(symbol: string): void {
    writeStoredWarmBootSymbol(symbol, this.options.symbolStorageKey);
  }

  /** Warm boot: symbols → chart candles → local draft/session restore (read-only, graceful fallback). */
  async initWarmBoot(options: WarmBootOptions = {}): Promise<WarmBootResult> {
    this.emitStatus({ phase: 'syncing', reason: 'warm_boot', lastError: undefined });
    try {
      const result = await runWarmBoot({
        ...options,
        baseUrl: options.baseUrl ?? this.options.baseUrl,
        limit: options.limit ?? this.options.limit,
        fetchTimeoutMs: options.fetchTimeoutMs ?? this.options.fetchTimeoutMs,
        source: options.source ?? this.options.source,
        symbolStorageKey: options.symbolStorageKey ?? this.options.symbolStorageKey,
        symbol: options.symbol ?? this.readStoredSymbol(),
      });
      this.activeSymbol = result.symbol;
      this.emitStatus({
        phase: result.ok ? 'ready' : 'error',
        symbol: result.symbol,
        reason: 'warm_boot',
        lastSyncAt: new Date().toISOString(),
        lastError: result.ok ? undefined : result.errors.join('; ') || result.warnings.join('; '),
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      writeStoredWarmBootSymbol(DEFAULT_WARM_BOOT_SYMBOL, this.options.symbolStorageKey);
      this.activeSymbol = DEFAULT_WARM_BOOT_SYMBOL;
      this.emitStatus({ phase: 'error', reason: 'warm_boot', lastError: message });
      return {
        ok: false,
        symbol: DEFAULT_WARM_BOOT_SYMBOL,
        timeframe: DEFAULT_WARM_BOOT_TIMEFRAME,
        caseId: null,
        symbols: [...DEFAULT_FALLBACK_SYMBOLS],
        candleCount: 0,
        draftTimeframes: [],
        sessionRestored: false,
        resets: [`Warm boot crashed — reset to ${DEFAULT_WARM_BOOT_SYMBOL} ${DEFAULT_WARM_BOOT_TIMEFRAME}.`],
        warnings: [],
        errors: [message],
      };
    }
  }

  start(initialSymbol?: string): void {
    const symbol = normaliseSyncSymbol(initialSymbol ?? this.readStoredSymbol());
    this.activeSymbol = symbol;
    this.lastPolledSymbol = symbol;
    this.startResyncTimer();
    this.startSymbolPoll();
    void this.syncSymbol(symbol, { reason: 'app_start' });
  }

  onSymbolSelected(symbol: string): void {
    const next = normaliseSyncSymbol(symbol);
    if (!next) return;
    this.activeSymbol = next;
    this.lastPolledSymbol = next;
    if (this.symbolDebounceTimer) clearTimeout(this.symbolDebounceTimer);
    this.symbolDebounceTimer = setTimeout(() => {
      void this.syncSymbol(next, { reason: 'symbol_selected' });
    }, 250);
  }

  stop(): void {
    if (this.resyncTimer) clearInterval(this.resyncTimer);
    if (this.symbolPollTimer) clearInterval(this.symbolPollTimer);
    if (this.symbolDebounceTimer) clearTimeout(this.symbolDebounceTimer);
    this.resyncTimer = null;
    this.symbolPollTimer = null;
    this.symbolDebounceTimer = null;
    this.inFlight = null;
    this.emitStatus({ phase: 'idle' });
  }

  async syncSymbol(
    symbol: string,
    opts?: { reason?: string; refresh?: boolean; quiet?: boolean },
  ): Promise<SymbolSyncResult> {
    const sym = normaliseSyncSymbol(symbol);
    if (this.inFlight && this.activeSymbol === sym) {
      return this.inFlight;
    }

    this.activeSymbol = sym;
    if (!opts?.quiet) {
      this.emitStatus({ phase: 'syncing', symbol: sym, reason: opts?.reason, lastError: undefined });
    }

    const run = syncSymbolFromVps(sym, {
      baseUrl: this.options.baseUrl,
      timeframes: this.options.timeframes,
      limit: this.options.limit,
      fetchTimeoutMs: this.options.fetchTimeoutMs,
      source: this.options.source,
      reason: opts?.reason,
      refresh: opts?.refresh,
    }).then((result) => {
      this.emitStatus({
        phase: result.ok ? 'ready' : 'error',
        symbol: sym,
        reason: opts?.reason,
        lastSyncAt: new Date().toISOString(),
        lastError: result.ok ? undefined : result.error,
        results: result.results,
      });
      return result;
    }).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      const failed: SymbolSyncResult = {
        ok: false,
        symbol: sym,
        reason: opts?.reason ?? 'symbol_sync',
        totalFetched: 0,
        totalUpserted: 0,
        totalSkipped: 0,
        results: [],
        error: message,
      };
      this.emitStatus({ phase: 'error', symbol: sym, lastError: message, results: [] });
      return failed;
    }).finally(() => {
      if (this.inFlight === run) this.inFlight = null;
    });

    this.inFlight = run;
    return run;
  }

  private startResyncTimer(): void {
    if (this.resyncTimer) clearInterval(this.resyncTimer);
    if (!this.options.resyncIntervalMs || this.options.resyncIntervalMs <= 0) return;
    this.resyncTimer = setInterval(() => {
      const symbol = this.activeSymbol ?? this.readStoredSymbol();
      void (async () => {
        const sym = normaliseSyncSymbol(symbol);
        for (const tf of CHART_LIBRARY_TIMEFRAMES) {
          await syncIncrementalDeltaFromVps(sym, tf, {
            baseUrl: this.options.baseUrl,
            fetchTimeoutMs: this.options.fetchTimeoutMs,
            source: this.options.source,
            reason: 'interval_5m',
            mode: 'incremental_delta',
            quiet: true,
          });
        }
        this.emitStatus({
          phase: 'ready',
          symbol: sym,
          reason: 'interval_5m',
          lastSyncAt: new Date().toISOString(),
        });
      })();
    }, this.options.resyncIntervalMs);
  }

  private startSymbolPoll(): void {
    if (typeof window === 'undefined') return;
    if (this.symbolPollTimer) clearInterval(this.symbolPollTimer);
    this.symbolPollTimer = setInterval(() => {
      const next = this.readStoredSymbol();
      if (next === this.lastPolledSymbol) return;
      this.lastPolledSymbol = next;
      this.onSymbolSelected(next);
    }, 1000);
  }
}

let defaultService: SyncService | null = null;
let bootstrapCleanup: (() => void) | null = null;

export function getSyncService(options?: SyncServiceOptions): SyncService {
  if (!defaultService) {
    defaultService = new SyncService(options);
  }
  return defaultService;
}

/** Restore chart + draft state after app launch without throwing on stale preferences. */
export async function initWarmBoot(options?: WarmBootOptions): Promise<WarmBootResult> {
  return getSyncService(options).initWarmBoot(options);
}

/** Start background VPS→local candle sync on app boot and when the stored symbol changes. */
export function initBackgroundCandleSync(options?: SyncServiceOptions): () => void {
  if (bootstrapCleanup) bootstrapCleanup();

  defaultService = new SyncService(options);
  const service = defaultService;
  service.start();

  bootstrapCleanup = () => {
    service.stop();
    defaultService = null;
    bootstrapCleanup = null;
  };

  return bootstrapCleanup;
}
