import { describe, expect, it } from 'vitest';
import {
  buildLoadedCandleContext,
  childLayerAfterTransition,
  evaluateCandleFeedGuard,
  isStaleCandleLoadResult,
  rehydrateLoadedCandleContextForVisibleFeed,
} from './candleFeedIdentity';

describe('candleFeedIdentity', () => {
  const microActive = {
    symbol: 'XAUUSD',
    caseId: 'case-1',
    chartTimeframe: 'M15',
    sourceTimeframe: 'M15',
    structureLayer: 'MICRO' as const,
    candleLoadInFlight: false,
    candleCount: 120,
  };

  it('blocks marking when active layer expects M15 but loaded feed is H1', () => {
    const loaded = buildLoadedCandleContext({
      requestId: 3,
      symbol: 'XAUUSD',
      caseId: 'case-1',
      chartTimeframe: 'H1',
      sourceTimeframe: 'H1',
      structureLayer: 'INTRADAY',
      candleCount: 400,
    });
    const guard = evaluateCandleFeedGuard(microActive, loaded);
    expect(guard.ready).toBe(false);
    expect(guard.mismatch).toBe('loaded-tf');
    expect(guard.reloadChartTimeframe).toBe('M15');
    expect(guard.message).toContain('expected M15');
    expect(guard.message).toContain('loaded H1');
  });

  it('detects stale H1 load that must not overwrite newer M15 request', () => {
    expect(isStaleCandleLoadResult({
      startedRequestId: 2,
      startedTf: 'H1',
      latestRequestId: 3,
      activeChartTf: 'M15',
    })).toBe(true);
    expect(isStaleCandleLoadResult({
      startedRequestId: 3,
      startedTf: 'M15',
      latestRequestId: 3,
      activeChartTf: 'M15',
    })).toBe(false);
  });

  it('blocks marking while Micro transition candles are loading', () => {
    const guard = evaluateCandleFeedGuard(
      { ...microActive, candleLoadInFlight: true, candleCount: 0 },
      null,
    );
    expect(guard.ready).toBe(false);
    expect(guard.mismatch).toBe('loading');
    expect(guard.message).toContain('Loading Micro candles');
  });

  it('passes when chart tab matches loaded candle timeframe for Micro', () => {
    const loaded = buildLoadedCandleContext({
      requestId: 4,
      symbol: 'XAUUSD',
      caseId: 'case-1',
      chartTimeframe: 'M15',
      sourceTimeframe: 'M15',
      structureLayer: 'MICRO',
      candleCount: 88,
    });
    const guard = evaluateCandleFeedGuard(microActive, loaded);
    expect(guard.ready).toBe(true);
  });

  it('maps Intraday parent to Micro child layer for transition', () => {
    expect(childLayerAfterTransition('INTRADAY')).toBe('MICRO');
    expect(childLayerAfterTransition('DAILY')).toBe('INTRADAY');
  });

  it('stores source_timeframe/chart_timeframe on loaded Micro context', () => {
    const loaded = buildLoadedCandleContext({
      requestId: 5,
      symbol: 'XAUUSD',
      caseId: 'case-1',
      chartTimeframe: 'M15',
      sourceTimeframe: 'M15',
      structureLayer: 'MICRO',
      candleCount: 10,
    });
    expect(loaded?.sourceTimeframe).toBe('M15');
    expect(loaded?.chartTimeframe).toBe('M15');
    expect(loaded?.structureLayer).toBe('MICRO');
  });

  it('rehydrates loaded context when visible candles exist but loaded stamp was skipped', () => {
    const rehydrated = rehydrateLoadedCandleContextForVisibleFeed({
      loaded: null,
      requestId: 9,
      symbol: 'XAUUSD',
      caseId: 'case-1',
      chartTimeframe: 'H1',
      sourceTimeframe: 'H1',
      structureLayer: 'INTRADAY',
      candleCount: 240,
    });
    expect(rehydrated?.chartTimeframe).toBe('H1');
    expect(rehydrated?.candleCount).toBe(240);
    const guard = evaluateCandleFeedGuard(
      {
        symbol: 'XAUUSD',
        caseId: 'case-1',
        chartTimeframe: 'H1',
        sourceTimeframe: 'H1',
        structureLayer: 'INTRADAY',
        candleLoadInFlight: false,
        candleCount: 240,
      },
      rehydrated,
    );
    expect(guard.ready).toBe(true);
  });
});
