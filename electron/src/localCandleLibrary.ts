/**
 * Local candle library — primary chart read path.
 * VPS is delta/missing-window only; never full-history reload on TF switch.
 */

import {
  candleRangeFromWindow,
  fetchLocalCandles,
  getLocalCandlesStatus,
  type LocalCandleRow,
} from './localResearchClient';
import {
  shouldClearRangeUiFromRehydration,
  validateRangeRehydration,
  type RangeRehydrationListResult,
} from './rangeRehydrationService';
import {
  CHART_LIBRARY_TIMEFRAMES,
  INCREMENTAL_DELTA_LIMIT,
  INITIAL_BOOTSTRAP_LIMIT,
  mergeParsedCandleRows,
  normaliseSyncTimeframe,
  syncIncrementalDeltaFromVps,
  syncMissingWindowFromVps,
  type TimeframeSyncResult,
} from './syncService';

export type LocalLibraryLoadSource =
  | 'local'
  | 'local+missing_window'
  | 'none';

export type LocalLibraryDebugStatus = {
  symbol: string;
  timeframe: string;
  localCount: number;
  loadedTf: string;
  lastSyncedAt: string | null;
  syncSource: string | null;
  syncMode: string | null;
  missingWindow: boolean;
  firstTime: string | null;
  lastTime: string | null;
};

export type LocalChartLoadResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  candles: LocalCandleRow[];
  source: LocalLibraryLoadSource;
  localCount: number;
  rehydration: RangeRehydrationListResult | null;
  should_clear_ui: boolean;
  missingWindow: boolean;
  debug: LocalLibraryDebugStatus;
  error?: string;
  statusMessage?: string;
};

export { CHART_LIBRARY_TIMEFRAMES };

function emptyDebug(symbol: string, timeframe: string): LocalLibraryDebugStatus {
  return {
    symbol,
    timeframe,
    localCount: 0,
    loadedTf: timeframe,
    lastSyncedAt: null,
    syncSource: null,
    syncMode: null,
    missingWindow: false,
    firstTime: null,
    lastTime: null,
  };
}

export async function readLocalLibraryDebugStatus(
  symbol: string,
  timeframe: string,
): Promise<LocalLibraryDebugStatus> {
  const sym = String(symbol || 'XAUUSD').toUpperCase();
  const tf = normaliseSyncTimeframe(timeframe);
  const status = await getLocalCandlesStatus(sym, tf);
  const syncState = status.syncState;
  return {
    symbol: sym,
    timeframe: tf,
    localCount: Number(status.symbolCandles ?? 0),
    loadedTf: tf,
    lastSyncedAt: syncState?.last_sync_at ?? null,
    syncSource: syncState?.last_mode ? 'vps' : null,
    syncMode: syncState?.last_mode ?? null,
    missingWindow: false,
    firstTime: status.firstTime ?? null,
    lastTime: status.lastTime ?? null,
  };
}

export function buildLocalLibraryStatusLine(debug: LocalLibraryDebugStatus | null): string {
  if (!debug) return 'Local — · Sync —';
  const syncAt = debug.lastSyncedAt ? debug.lastSyncedAt.slice(0, 19).replace('T', ' ') : '—';
  const mode = debug.syncMode || debug.syncSource || '—';
  const windowWarn = debug.missingWindow ? ' · MISSING WINDOW' : '';
  return `Local ${debug.localCount} · Loaded ${debug.loadedTf} · Sync ${syncAt} · ${mode}${windowWarn}`;
}

export function formatMissingCandleMessage(timeframe: string, window?: { start?: string; end?: string } | null): string {
  const tf = normaliseSyncTimeframe(timeframe);
  if (window?.start && window?.end) {
    return `No ${tf} candles available for this window (${window.start} → ${window.end}). Sync/import required.`;
  }
  return `No ${tf} candles available for this window. Sync/import required.`;
}

export async function loadChartCandlesLocalFirst(args: {
  symbol: string;
  timeframe: string;
  window?: { start?: string; end?: string } | null;
  caseId?: string | null;
  /** When true, skip VPS even if the requested local window is empty. */
  localOnly?: boolean;
}): Promise<LocalChartLoadResult> {
  const sym = String(args.symbol || 'XAUUSD').toUpperCase();
  const tf = normaliseSyncTimeframe(args.timeframe);
  const range = candleRangeFromWindow(args.window ?? null);

  const rehydration = await validateRangeRehydration(sym, tf, args.caseId ?? null);
  const shouldClearUi = shouldClearRangeUiFromRehydration(rehydration);
  if (shouldClearUi) {
    return {
      ok: false,
      symbol: sym,
      timeframe: tf,
      candles: [],
      source: 'none',
      localCount: 0,
      rehydration,
      should_clear_ui: true,
      missingWindow: false,
      debug: { ...emptyDebug(sym, tf), missingWindow: !!args.window },
      error: rehydration.error || 'Stale mapping_ranges cache blocked candle load',
    };
  }

  const beforeStatus = await readLocalLibraryDebugStatus(sym, tf).catch(() => emptyDebug(sym, tf));
  let local = await fetchLocalCandles(sym, tf, range);
  const localWindowCountBeforeSync = local.candles.length;
  console.info('[local-candles] load local-first', {
    requestedTf: tf,
    requestedWindow: args.window || null,
    localCountBeforeSync: localWindowCountBeforeSync,
    totalLocalCountBeforeSync: beforeStatus.localCount,
    lastSyncedAt: beforeStatus.lastSyncedAt,
    lastMode: beforeStatus.syncMode,
    vpsFetchAttempted: false,
  });
  let source: LocalLibraryLoadSource = local.ok && local.candles.length ? 'local' : 'none';
  let missingWindow = false;

  if (!local.candles.length && !args.localOnly && (args.window?.start || args.window?.end)) {
    missingWindow = true;
    const windowSync = await syncMissingWindowFromVps(sym, tf, {
      start: args.window?.start,
      end: args.window?.end,
    }, { reason: 'missing_window', mode: 'missing_window' });
    const afterSyncStatus = await readLocalLibraryDebugStatus(sym, tf).catch(() => emptyDebug(sym, tf));
    if (windowSync.ok) {
      local = await fetchLocalCandles(sym, tf, range);
      if (local.candles.length) source = 'local+missing_window';
    }
    console.info('[local-candles] missing-window sync', {
      requestedTf: tf,
      requestedWindow: args.window || null,
      localCountBeforeSync: localWindowCountBeforeSync,
      totalLocalCountBeforeSync: beforeStatus.localCount,
      vpsFetchAttempted: true,
      vpsResponseCount: windowSync.fetched,
      upsertCount: windowSync.upserted,
      localCountAfterSync: afterSyncStatus.localCount,
      chartRereadCountAfterSync: local.candles.length,
      ok: windowSync.ok,
      error: windowSync.error,
    });
  } else if (!local.candles.length) {
    console.info('[local-candles] empty local window no VPS fetch', {
      requestedTf: tf,
      requestedWindow: args.window || null,
      localCountBeforeSync: localWindowCountBeforeSync,
      totalLocalCountBeforeSync: beforeStatus.localCount,
      vpsFetchAttempted: false,
      reason: args.localOnly ? 'local-only' : 'no-window',
    });
  }

  const debug = await readLocalLibraryDebugStatus(sym, tf);
  debug.missingWindow = missingWindow && !local.candles.length;
  debug.loadedTf = tf;
  debug.localCount = local.candles.length;

  const ok = local.ok && local.candles.length > 0;
  return {
    ok,
    symbol: sym,
    timeframe: tf,
    candles: local.candles,
    source,
    localCount: local.candles.length,
    rehydration,
    should_clear_ui: false,
    missingWindow: debug.missingWindow,
    debug,
    error: ok ? undefined : local.error,
    statusMessage: ok
      ? undefined
      : formatMissingCandleMessage(tf, args.window ?? null),
  };
}

/** Background incremental VPS delta — refresh local library without blocking chart paint. */
export async function runBackgroundDeltaSync(args: {
  symbol: string;
  timeframe: string;
  window?: { start?: string; end?: string } | null;
  previousCandles?: LocalCandleRow[];
}): Promise<{
  delta: TimeframeSyncResult;
  candles: LocalCandleRow[];
  changed: boolean;
  debug: LocalLibraryDebugStatus;
}> {
  const sym = String(args.symbol || 'XAUUSD').toUpperCase();
  const tf = normaliseSyncTimeframe(args.timeframe);
  const range = candleRangeFromWindow(args.window ?? null);
  const delta = await syncIncrementalDeltaFromVps(sym, tf, {
    reason: 'chart_background_delta',
    mode: 'incremental_delta',
  });
  const local = await fetchLocalCandles(sym, tf, range);
  const debug = await readLocalLibraryDebugStatus(sym, tf);
  debug.loadedTf = tf;
  debug.localCount = local.candles.length;
  const changed = candlesChanged(args.previousCandles || [], local.candles);
  return { delta, candles: local.candles, changed, debug };
}

/** Background incremental sync for active chart symbol — all library TFs, delta only. */
export async function syncActiveSymbolIncremental(
  symbol: string,
  timeframes: readonly string[] = CHART_LIBRARY_TIMEFRAMES,
  options?: { reason?: string; quiet?: boolean },
): Promise<TimeframeSyncResult[]> {
  const sym = String(symbol || 'XAUUSD').toUpperCase();
  const results: TimeframeSyncResult[] = [];
  for (const tfRaw of timeframes) {
    const tf = normaliseSyncTimeframe(tfRaw);
    if (!CHART_LIBRARY_TIMEFRAMES.includes(tf)) continue;
    results.push(await syncIncrementalDeltaFromVps(sym, tf, {
      reason: options?.reason ?? 'interval_5m',
      mode: 'incremental_delta',
      quiet: options?.quiet,
    }));
  }
  return results;
}

export function candlesChanged(
  previous: LocalCandleRow[],
  next: LocalCandleRow[],
): boolean {
  if (previous.length !== next.length) return true;
  if (!previous.length) return false;
  const prevLast = previous[previous.length - 1];
  const nextLast = next[next.length - 1];
  if (String(prevLast.time) !== String(nextLast.time)) return true;
  return prevLast.open !== nextLast.open
    || prevLast.high !== nextLast.high
    || prevLast.low !== nextLast.low
    || prevLast.close !== nextLast.close
    || (prevLast.volume ?? 0) !== (nextLast.volume ?? 0);
}

export function mergeParsedCandleRowsForChart<T extends { time: string }>(
  base: T[],
  delta: T[],
): T[] {
  return mergeParsedCandleRows(base, delta);
}

export const LIBRARY_INITIAL_BOOTSTRAP_LIMIT = INITIAL_BOOTSTRAP_LIMIT;
export const LIBRARY_INCREMENTAL_DELTA_LIMIT = INCREMENTAL_DELTA_LIMIT;
