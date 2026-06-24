import { describe, expect, it } from 'vitest';
import {
  filterCandlesToLoadWindow,
  isCurrentCandleLoadRequest,
  loadWindowKey,
  resolveStructuralCandleLoadWindow,
  resolveStructuralContextAndReplayWindows,
  resolveStructuralDataLoadWindow,
  resolveTimeframeSwitchDataLoadWindow,
  shouldApplyParsedCandles,
  shouldBlockQuietFullHistoryReload,
  shouldClearCandlesOnLoadStart,
  shouldPreserveTradingViewMappingCandleUniverse,
  shouldUseWindowedCandleLoad,
  structuralDataLoadPadding,
  trimStructuralCandlesToHorizon,
  trimStructuralCandlesToMaxBars,
} from './candleLoadPolicy';

describe('candleLoadPolicy', () => {
  it('resolveStructuralCandleLoadWindow prefers chart viewport', () => {
    expect(resolveStructuralCandleLoadWindow({
      rangeWindow: {},
      preferredWindow: { start: '2025-06-01T00:00:00.000Z', end: '2025-06-10T00:00:00.000Z' },
    })).toEqual({
      start: '2025-06-01',
      end: '2025-06-10',
      label: 'chart viewport',
    });
  });

  it('resolveStructuralCandleLoadWindow prefers structural context over case window', () => {
    expect(resolveStructuralCandleLoadWindow({
      rangeWindow: { start: '2025-01-01T00:00:00.000Z', end: '2025-12-31T00:00:00.000Z' },
      contextFit: {
        start: '2025-06-01T00:00:00.000Z',
        end: '2025-06-10T00:00:00.000Z',
        label: 'Daily #12',
      },
      pinStructuralEnd: true,
    })).toEqual({
      start: '2025-06-01',
      end: '2025-06-10',
      label: 'Daily #12',
    });
  });

  it('resolveStructuralCandleLoadWindow does not extend structural end to today when pinned', () => {
    const out = resolveStructuralCandleLoadWindow({
      rangeWindow: {},
      liveTail: true,
      pinStructuralEnd: true,
      contextFit: {
        start: '2025-06-01T00:00:00.000Z',
        end: '2025-06-10T00:00:00.000Z',
        label: 'Daily #12',
      },
    });
    expect(out?.end).toBe('2025-06-10');
  });

  it('resolveStructuralDataLoadWindow widens range span for H1 without live tail', () => {
    const out = resolveStructuralDataLoadWindow({
      rangeSpan: { start: '2025-06-01T00:00:00.000Z', end: '2025-06-10T00:00:00.000Z' },
      chartTf: 'H1',
      structureLayer: 'DAILY',
      label: 'Daily #12 context',
    });
    expect(out).not.toBeNull();
    expect(out!.start < '2025-06-01').toBe(true);
    expect(out!.end > '2025-06-10').toBe(true);
    expect(out!.label).toBe('Daily #12 context');
    const spanDays = Math.round(
      (new Date(`${out!.end}T00:00:00.000Z`).getTime() - new Date(`${out!.start}T00:00:00.000Z`).getTime()) / 86400000,
    );
    expect(spanDays).toBeLessThanOrEqual(45);
  });

  it('structuralDataLoadPadding caps intraday spans', () => {
    const pad = structuralDataLoadPadding('M15', 'MICRO');
    expect(pad.maxSpanDays).toBeLessThanOrEqual(28);
  });

  it('resolveStructuralCandleLoadWindow uses range window when no structural context', () => {
    expect(resolveStructuralCandleLoadWindow({
      rangeWindow: { start: '2025-01-06T00:00:00.000Z', end: '2025-01-12T00:00:00.000Z' },
    })).toEqual({
      start: '2025-01-06',
      end: '2025-01-12',
      label: 'active case window',
    });
  });

  it('shouldUseWindowedCandleLoad blocks full history when window exists', () => {
    const window = { start: '2025-01-06', end: '2025-01-12', label: 'x' };
    expect(shouldUseWindowedCandleLoad(window)).toBe(true);
    expect(shouldUseWindowedCandleLoad(window, { forceFullHistory: true })).toBe(false);
  });

  it('isCurrentCandleLoadRequest rejects stale window key', () => {
    const started = {
      requestId: 2,
      symbol: 'XAUUSD',
      caseId: 'a',
      tf: 'D1',
      activeRangeId: '12',
      loadWindowKey: '2025-06-01|2025-06-10',
    };
    expect(isCurrentCandleLoadRequest(started, started, 'D1')).toBe(true);
    expect(isCurrentCandleLoadRequest(started, { ...started, loadWindowKey: 'full' }, 'D1')).toBe(false);
  });

  it('shouldBlockQuietFullHistoryReload blocks background stomp during structural mapping', () => {
    expect(shouldBlockQuietFullHistoryReload({
      quiet: true,
      forceFullHistory: true,
      activeRangeId: '44',
      incomingWindowKey: 'full',
    })).toBe(true);
    expect(shouldBlockQuietFullHistoryReload({
      quiet: true,
      activeRangeId: '',
      selectedParentRangeId: '7',
      incomingWindowKey: 'full',
    })).toBe(true);
    expect(shouldBlockQuietFullHistoryReload({
      quiet: true,
      activeRangeId: '',
      incomingWindowKey: 'full',
    })).toBe(false);
  });

  it('loadWindowKey encodes window or full', () => {
    expect(loadWindowKey(null)).toBe('full');
    expect(loadWindowKey({ start: '2025-06-01', end: '2025-06-10', label: 'x' })).toBe('2025-06-01|2025-06-10');
  });

  it('shouldApplyParsedCandles rejects suspicious single-bar window load with diagnostic', () => {
    const out = shouldApplyParsedCandles({
      parsedCount: 1,
      previousCount: 120,
      hadLoadWindow: true,
      requestedTf: 'H4',
      windowStart: '2025-06-01',
      windowEnd: '2025-06-10',
    });
    expect(out.apply).toBe(false);
    expect(out.statusMessage).toMatch(/H4 load returned 1 candle/i);
    expect(out.statusMessage).toMatch(/2025-06-01 → 2025-06-10/);
  });

  it('resolveTimeframeSwitchDataLoadWindow widens parent span for H4 instead of camera viewport', () => {
    const out = resolveTimeframeSwitchDataLoadWindow({
      targetTf: 'H4',
      contextRange: {
        start: '2025-06-01T00:00:00.000Z',
        end: '2025-06-10T00:00:00.000Z',
        structure_layer: 'DAILY',
      },
    });
    expect(out).not.toBeNull();
    expect(out!.start < '2025-06-01').toBe(true);
    expect(out!.end > '2025-06-10').toBe(true);
    expect(out!.label).toBe('timeframe-switch context');
  });

  it('resolveTimeframeSwitchDataLoadWindow requests M15 candles for micro switch not daily viewport', () => {
    const out = resolveTimeframeSwitchDataLoadWindow({
      targetTf: 'M15',
      contextRange: {
        start: '2025-06-01T00:00:00.000Z',
        end: '2025-06-03T00:00:00.000Z',
        structure_layer: 'MICRO',
      },
    });
    expect(out).not.toBeNull();
    expect(out!.start).toBeTruthy();
    expect(out!.end >= '2025-06-03').toBe(true);
  });

  it('shouldPreserveTradingViewMappingCandleUniverse blocks structural reload on TV Map On', () => {
    const base = {
      chartRenderer: 'tradingview',
      mappingInputEnabled: true,
      targetTf: 'H1',
      activeChartTf: 'H1',
      candleCount: 240,
    };
    expect(shouldPreserveTradingViewMappingCandleUniverse({
      ...base,
      structuralNavigation: true,
      reason: 'feed-mismatch-reload',
    })).toBe(true);
    expect(shouldPreserveTradingViewMappingCandleUniverse({
      ...base,
      timeframeSwitch: true,
      structuralNavigation: true,
    })).toBe(false);
    expect(shouldPreserveTradingViewMappingCandleUniverse({
      ...base,
      mappingInputEnabled: false,
      structuralNavigation: true,
    })).toBe(false);
    expect(shouldPreserveTradingViewMappingCandleUniverse({
      ...base,
      candleCount: 0,
      structuralNavigation: true,
    })).toBe(false);
  });

  it('shouldClearCandlesOnLoadStart clears on explicit timeframe switch', () => {
    expect(shouldClearCandlesOnLoadStart({
      quiet: false,
      timeframeSwitch: true,
      targetTf: 'H4',
      loadedChartTf: 'H1',
    })).toBe(true);
    expect(shouldClearCandlesOnLoadStart({
      quiet: true,
      timeframeSwitch: true,
      targetTf: 'H4',
      loadedChartTf: 'H1',
    })).toBe(false);
  });

  it('isCurrentCandleLoadRequest rejects stale H4 result when active tab is M15', () => {
    const started = {
      requestId: 2,
      symbol: 'XAUUSD',
      caseId: 'a',
      tf: 'H4',
      activeRangeId: '12',
      loadWindowKey: '2025-06-01|2025-06-10',
    };
    expect(isCurrentCandleLoadRequest(started, started, 'M15')).toBe(false);
    expect(isCurrentCandleLoadRequest(started, { ...started, requestId: 3 }, 'M15')).toBe(false);
  });

  it('filterCandlesToLoadWindow trims out-of-window bars', () => {
    const candles = [
      { time: '2025-05-01T00:00:00.000Z' },
      { time: '2025-06-05T12:00:00.000Z' },
      { time: '2025-07-01T00:00:00.000Z' },
    ];
    const out = filterCandlesToLoadWindow(candles, { start: '2025-06-01', end: '2025-06-10', label: 'x' });
    expect(out).toHaveLength(1);
    expect(out[0].time).toContain('2025-06-05');
  });

  it('resolveStructuralContextAndReplayWindows separates visual context from padded data load', () => {
    const out = resolveStructuralContextAndReplayWindows({
      rangeSpan: { start: '2025-06-01T00:00:00.000Z', end: '2025-06-10T00:00:00.000Z' },
      chartTf: 'D1',
      structureLayer: 'WEEKLY',
      label: 'Weekly #3 context',
    });
    expect(out).not.toBeNull();
    expect(out!.visualContext.start).toBe('2025-06-01');
    expect(out!.visualContext.end).toBe('2025-06-10');
    expect(out!.dataLoad.start < out!.visualContext.start).toBe(true);
    expect(out!.dataLoad.end > out!.visualContext.end).toBe(true);
  });

  it('resolveStructuralDataLoadWindow trims oldest history first when span exceeds maxSpanDays', () => {
    const out = resolveStructuralDataLoadWindow({
      rangeSpan: { start: '2020-01-01T00:00:00.000Z', end: '2025-06-10T00:00:00.000Z' },
      chartTf: 'D1',
      structureLayer: 'WEEKLY',
      label: 'Weekly context',
    });
    expect(out).not.toBeNull();
    expect(out!.end >= '2025-06-10').toBe(true);
    const spanDays = Math.round(
      (new Date(`${out!.end}T00:00:00.000Z`).getTime() - new Date(`${out!.start}T00:00:00.000Z`).getTime()) / 86400000,
    );
    expect(spanDays).toBeLessThanOrEqual(180);
  });

  it('trimStructuralCandlesToMaxBars keeps newest bars', () => {
    const candles = Array.from({ length: 10 }, (_, i) => ({ time: `2025-01-${String(i + 1).padStart(2, '0')}T00:00:00.000Z` }));
    const out = trimStructuralCandlesToMaxBars(candles, 4);
    expect(out).toHaveLength(4);
    expect(out[0].time).toContain('2025-01-07');
    expect(out[3].time).toContain('2025-01-10');
  });

  it('trimStructuralCandlesToHorizon keeps lookback before visual context and lookahead after', () => {
    const candles = Array.from({ length: 300 }, (_, i) => ({
      time: new Date(Date.UTC(2025, 0, 1 + i)).toISOString(),
    }));
    const visualContext = { start: '2025-06-01', end: '2025-06-10' };
    const out = trimStructuralCandlesToHorizon(candles, 80, visualContext, 'D1');
    expect(out.length).toBeLessThanOrEqual(80);
    expect(out[0].time < `${visualContext.start}T00:00:00.000Z`).toBe(true);
    expect(out[out.length - 1].time > `${visualContext.end}T23:59:59.999Z`).toBe(true);
  });
});
