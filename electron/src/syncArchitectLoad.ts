import {
  candleRangeFromWindow,
  fetchLocalCandles,
  type LocalCandleRow,
} from './localResearchClient';
import {
  shouldClearRangeUiFromRehydration,
  validateRangeRehydration,
} from './rangeRehydrationService';

export type SyncArchitectLoadResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  candles: LocalCandleRow[];
  source: 'local_sqlite' | 'cache' | 'none';
  synced: boolean;
  rehydration: Awaited<ReturnType<typeof validateRangeRehydration>> | null;
  should_clear_ui: boolean;
  error?: string;
};

/** Local-first chart session load — VPS sync is handled separately by localCandleLibrary. */
export async function loadSessionFromSyncArchitect(
  symbol: string,
  timeframe: string,
  options?: {
    refresh?: boolean;
    skipVpsSync?: boolean;
    range?: { start?: string; end?: string } | null;
    caseId?: string | null;
  },
): Promise<SyncArchitectLoadResult> {
  const sym = String(symbol || 'XAUUSD').trim().toUpperCase();
  const tf = String(timeframe || 'D1').trim().toUpperCase();

  const rehydration = await validateRangeRehydration(sym, tf, options?.caseId ?? null);
  const shouldClearUi = shouldClearRangeUiFromRehydration(rehydration);

  const local = shouldClearUi
    ? {
      ok: false,
      symbol: sym,
      timeframe: tf,
      source: 'cache' as const,
      databasePath: rehydration.databasePath,
      candles: [] as LocalCandleRow[],
      error: rehydration.error || 'Stale mapping_ranges cache blocked warm boot rehydration',
    }
    : await fetchLocalCandles(sym, tf, candleRangeFromWindow(options?.range));

  return {
    ok: !shouldClearUi && local.ok && local.candles.length > 0,
    symbol: sym,
    timeframe: tf,
    candles: shouldClearUi ? [] : local.candles,
    source: shouldClearUi ? 'none' : (local.ok && local.candles.length ? local.source : 'none'),
    synced: false,
    rehydration,
    should_clear_ui: shouldClearUi,
    error: local.error,
  };
}
