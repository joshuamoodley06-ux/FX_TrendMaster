import { describe, expect, it, vi } from 'vitest';
import {
  buildUpsertPayloadFromVpsResponse,
  buildVpsCandlesUrl,
  initWarmBoot,
  normaliseSyncSymbol,
  normaliseUpsertCandleTime,
  resolveSymbolForWarmBoot,
  runWarmBoot,
  syncTimeframeFromVps,
  transformVpsCandleRow,
} from './syncService';
import * as localResearchClient from './localResearchClient';

describe('syncService transforms', () => {
  it('normalises ISO candle times to MT5 storage format', () => {
    expect(normaliseUpsertCandleTime('2024-01-02T00:00:00.000Z')).toBe('2024.01.02 00:00');
    expect(normaliseUpsertCandleTime('2024.01.02 00:00')).toBe('2024.01.02 00:00');
  });

  it('transforms VPS rows into upsert candle rows', () => {
    const row = transformVpsCandleRow(
      {
        time: '2024.01.02 00:00',
        open: '2300.5',
        high: 2310,
        low: 2290,
        close: '2305.25',
        volume: '123',
      },
      { symbol: 'xauusd', timeframe: 'd1', source: 'vps-sync' },
    );
    expect(row).toEqual({
      symbol: 'XAUUSD',
      timeframe: 'D1',
      time: '2024.01.02 00:00',
      open: 2300.5,
      high: 2310,
      low: 2290,
      close: 2305.25,
      volume: 123,
      source: 'vps-sync',
    });
  });

  it('builds upsert payload with sync state from VPS response', () => {
    const payload = buildUpsertPayloadFromVpsResponse(
      {
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'H1',
        candles: [
          { time: '2024.01.02 10:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
          { time: '2024.01.02 11:00', open: 1.5, high: 2.5, low: 1.4, close: 2.1, volume: 11 },
        ],
      },
      { symbol: 'XAUUSD', timeframe: 'H1', source: 'vps-sync', mode: 'app_start' },
    );

    expect(payload?.candles).toHaveLength(2);
    expect(payload?.symbol).toBe('XAUUSD');
    expect(payload?.timeframe).toBe('H1');
    expect(payload?.syncState).toMatchObject({
      symbol: 'XAUUSD',
      timeframe: 'H1',
      last_time: '2024.01.02 11:00',
      bar_count: 2,
      last_mode: 'app_start',
      last_error: null,
    });
  });

  it('builds VPS fetch URLs with normalised params', () => {
    const url = buildVpsCandlesUrl('https://api.example.com/', 'xauusd', 'd1', {
      limit: 500,
      start: '2024-01-01',
      refresh: true,
    });
    expect(url).toBe(
      'https://api.example.com/api/v1/candles?symbol=XAUUSD&timeframe=D1&limit=500&start=2024-01-01&refresh=1',
    );
    expect(normaliseSyncSymbol(' us500.cash ')).toBe('US500.CASH');
  });
});

describe('syncTimeframeFromVps', () => {
  it('fetches VPS candles and writes through electronAPI.candles.upsert', async () => {
    const upsert = vi.spyOn(localResearchClient, 'upsertLocalCandles').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      upserted: 2,
      skipped: 0,
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'D1',
        candles: [
          { time: '2024.01.02 00:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
          { time: '2024.01.03 00:00', open: 1.5, high: 2.5, low: 1.4, close: 2.1, volume: 11 },
        ],
      }),
    }));

    const result = await syncTimeframeFromVps('XAUUSD', 'D1', { reason: 'test' });
    expect(result.ok).toBe(true);
    expect(result.fetched).toBe(2);
    expect(result.upserted).toBe(2);
    expect(upsert).toHaveBeenCalledWith(expect.objectContaining({
      symbol: 'XAUUSD',
      timeframe: 'D1',
      candles: expect.arrayContaining([
        expect.objectContaining({ time: '2024.01.02 00:00' }),
      ]),
      syncState: expect.objectContaining({
        symbol: 'XAUUSD',
        timeframe: 'D1',
        bar_count: 2,
        last_mode: 'test',
      }),
    }));

    vi.unstubAllGlobals();
    upsert.mockRestore();
  });
});

describe('warm boot', () => {
  it('resolves unavailable stored symbols to a known default', () => {
    const resolved = resolveSymbolForWarmBoot('DELETED_SYM', ['XAUUSD', 'US500.CASH']);
    expect(resolved.reset).toBe(true);
    expect(resolved.symbol).toBe('XAUUSD');
    expect(resolved.previous).toBe('DELETED_SYM');
  });

  it('initWarmBoot falls back to defaults when chart load fails for stale symbol', async () => {
    vi.spyOn(localResearchClient, 'upsertLocalCandles').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      upserted: 0,
      skipped: 0,
    });
    vi.spyOn(localResearchClient, 'fetchLocalCandles')
      .mockResolvedValueOnce({
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'H1',
        source: 'cache',
        databasePath: 'C:\\cache\\candle_cache.db',
        candles: [],
      })
      .mockResolvedValueOnce({
        ok: true,
        symbol: 'XAUUSD',
        timeframe: 'D1',
        source: 'cache',
        databasePath: 'C:\\cache\\candle_cache.db',
        candles: [{ time: '2024.01.02T00:00:00.000Z', open: 1, high: 2, low: 0.5, close: 1.5 }],
      });

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          groups: [{ symbol: 'XAUUSD' }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: false,
          symbol: 'OLD_SYM',
          timeframe: 'H1',
          candles: [],
          error: 'symbol removed',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          symbol: 'XAUUSD',
          timeframe: 'D1',
          candles: [
            { time: '2024.01.02 00:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 },
          ],
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const result = await runWarmBoot({
      symbol: 'OLD_SYM',
      timeframe: 'H1',
      caseId: 'missing-case',
    });

    expect(result.ok).toBe(true);
    expect(result.symbol).toBe('XAUUSD');
    expect(result.timeframe).toBe('D1');
    expect(result.caseId).toBe('missing-case');
    expect(result.resets.some((line) => line.includes('OLD_SYM'))).toBe(true);

    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('exposes initWarmBoot through SyncService without throwing', async () => {
    vi.spyOn(localResearchClient, 'upsertLocalCandles').mockResolvedValue({
      ok: true,
      databasePath: 'C:\\cache\\candle_cache.db',
      upserted: 1,
      skipped: 0,
    });
    vi.spyOn(localResearchClient, 'fetchLocalCandles').mockResolvedValue({
      ok: true,
      symbol: 'XAUUSD',
      timeframe: 'D1',
      source: 'cache',
      databasePath: 'C:\\cache\\candle_cache.db',
      candles: [{ time: '2024.01.02T00:00:00.000Z', open: 1, high: 2, low: 0.5, close: 1.5 }],
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        groups: [{ symbol: 'XAUUSD' }],
        candles: [{ time: '2024.01.02 00:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 }],
      }),
    }));

    await expect(initWarmBoot({ symbol: 'XAUUSD', timeframe: 'D1' }))
      .resolves.toMatchObject({ ok: true, symbol: 'XAUUSD', timeframe: 'D1' });

    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
});
