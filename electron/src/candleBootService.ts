import {
  fetchLocalCandles,
  getLocalCandlesStatus,
  upsertLocalCandles,
} from './localResearchClient';
import {
  buildUpsertPayloadFromVpsResponse,
  syncSymbolFromVps,
  syncTimeframeFromVps,
  type VpsCandlesResponse,
} from './syncService';

export async function readLocalCacheBarCount(symbol: string, timeframe: string): Promise<number> {
  const status = await getLocalCandlesStatus(symbol, timeframe);
  if (!status.ok) return 0;
  return Number(status.symbolCandles ?? 0);
}

export async function persistRemoteCandlesToCache(
  symbol: string,
  timeframe: string,
  response: VpsCandlesResponse,
  mode = 'chart_load',
): Promise<{ ok: boolean; upserted: number; error?: string }> {
  const payload = buildUpsertPayloadFromVpsResponse(response, {
    symbol,
    timeframe,
    source: 'vps-sync',
    mode,
  });
  if (!payload) {
    return { ok: false, upserted: 0, error: 'No candles to persist' };
  }
  const result = await upsertLocalCandles(payload);
  return {
    ok: !!result.ok,
    upserted: Number(result.upserted || 0),
    error: result.error,
  };
}

export async function syncSymbolTimeframeToCache(
  symbol: string,
  timeframe: string,
  options?: { refresh?: boolean; reason?: string },
) {
  return syncTimeframeFromVps(symbol, timeframe, {
    reason: options?.reason ?? 'boot_sync',
    refresh: options?.refresh,
  });
}

export async function syncSymbolAllTimeframesToCache(
  symbol: string,
  options?: { refresh?: boolean; reason?: string; baseUrl?: string },
) {
  return syncSymbolFromVps(symbol, {
    reason: options?.reason ?? 'background_sync',
    refresh: options?.refresh,
    baseUrl: options?.baseUrl,
  });
}

export async function fetchCachedCandlesForChart(
  symbol: string,
  timeframe: string,
  limit = 8000,
) {
  return fetchLocalCandles(symbol, timeframe, { limit });
}
