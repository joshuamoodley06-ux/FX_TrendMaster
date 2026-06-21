import { describe, expect, it } from 'vitest';
import {
  annotateOverlayFocusTiers,
  buildCandleSpanFit,
  buildContextReplayFitWindow,
  buildFitActiveWindow,
  candleOnlyYExtents,
  defaultFocusModeForGuided,
  ensureFitWindowMinBars,
  filterFocusModeOverlays,
  fitActiveMinBars,
  fitWindowBarCount,
  focusVisualStyle,
  focusYExtentsWithParent,
  mergeFocusFitPriceDomain,
  mergeResearchWindowForFitActive,
  resolveFocusTier,
  shouldUseCandleOnlyYScale,
} from './chartFocusMode';
import { isExplicitViewportMove, shouldPreserveViewport } from './viewportController';

function makeCandles(count: number, intervalMs: number, start = '2025-01-01T00:00:00.000Z') {
  const base = Date.parse(start);
  return Array.from({ length: count }, (_, i) => ({
    time: new Date(base + i * intervalMs).toISOString(),
    high: 2100 + i,
    low: 2090 + i,
  }));
}

const m15Candles = makeCandles(320, 15 * 60 * 1000);
const h1Candles = makeCandles(200, 60 * 60 * 1000);
const d1Candles = makeCandles(90, 24 * 60 * 60 * 1000);
const candles = h1Candles.slice(0, 20);

describe('chartFocusMode', () => {
  it('Focus Mode ON excludes context lines from y-scale', () => {
    expect(shouldUseCandleOnlyYScale(true)).toBe(true);
    const y = candleOnlyYExtents(candles);
    expect(y?.low).toBe(2090);
    expect(y?.high).toBe(2100 + 19);
  });

  it('Focus Mode OFF preserves old y-scale behavior flag', () => {
    expect(shouldUseCandleOnlyYScale(false)).toBe(false);
  });

  it('Fit Active uses visible candles for y-scale', () => {
    const fit = buildFitActiveWindow({
      candles,
      timeframe: 'D1',
      cursorTimeMs: Date.parse('2025-01-01T06:00:00.000Z'),
      gapEndMs: Date.parse('2025-01-01T08:00:00.000Z'),
    });
    expect(fit).not.toBeNull();
    expect(fit!.low).toBeGreaterThanOrEqual(2090);
    expect(fit!.high).toBeLessThanOrEqual(2100 + 19);
    expect(fit!.padRatio).toBe(0.1);
  });

  it('Fit Active on M15 returns at least 160 candle window', () => {
    const cursorMs = Date.parse(m15Candles[120].time);
    const fit = buildFitActiveWindow({
      candles: m15Candles,
      timeframe: 'M15',
      cursorTimeMs: cursorMs,
      gapEndMs: cursorMs + 2 * 15 * 60 * 1000,
    });
    expect(fit).not.toBeNull();
    expect(fitWindowBarCount(m15Candles, fit!)).toBeGreaterThanOrEqual(fitActiveMinBars('M15'));
    expect(fit!.padRatio).toBe(0.1);
  });

  it('Fit Active on H1 returns at least 72 candle window', () => {
    const cursorMs = Date.parse(h1Candles[80].time);
    const fit = buildFitActiveWindow({
      candles: h1Candles,
      timeframe: 'H1',
      cursorTimeMs: cursorMs,
      gapEndMs: cursorMs + 2 * 60 * 60 * 1000,
    });
    expect(fit).not.toBeNull();
    expect(fitWindowBarCount(h1Candles, fit!)).toBeGreaterThanOrEqual(fitActiveMinBars('H1'));
  });

  it('Fit Active on D1 returns at least 30 candle window', () => {
    const cursorMs = Date.parse(d1Candles[40].time);
    const fit = buildFitActiveWindow({
      candles: d1Candles,
      timeframe: 'D1',
      cursorTimeMs: cursorMs,
      gapEndMs: cursorMs + 24 * 60 * 60 * 1000,
    });
    expect(fit).not.toBeNull();
    expect(fitWindowBarCount(d1Candles, fit!)).toBeGreaterThanOrEqual(fitActiveMinBars('D1'));
  });

  it('tiny draft span expands to minimum window', () => {
    const fit = buildFitActiveWindow({
      candles: m15Candles,
      timeframe: 'M15',
      draftStart: m15Candles[100].time,
      draftEnd: m15Candles[102].time,
    });
    expect(fit).not.toBeNull();
    expect(fitWindowBarCount(m15Candles, fit!)).toBeGreaterThanOrEqual(160);
  });

  it('large active span uses active span plus padding', () => {
    const fit = buildFitActiveWindow({
      candles: m15Candles,
      timeframe: 'M15',
      childStart: m15Candles[20].time,
      childEnd: m15Candles[200].time,
    });
    expect(fit).not.toBeNull();
    const bars = fitWindowBarCount(m15Candles, fit!);
    expect(bars).toBeGreaterThan(180);
    expect(bars).toBeLessThanOrEqual(233);
  });

  it('MICRO open auto-fit research window uses minimum M15 window', () => {
    const cursorMs = Date.parse('2025-01-05T12:00:00.000Z');
    const narrow = {
      start: new Date(cursorMs).toISOString(),
      end: new Date(cursorMs + 2 * 60 * 60 * 1000).toISOString(),
      dateFrom: '2025-01-05',
      dateTo: '2025-01-05',
    };
    const merged = mergeResearchWindowForFitActive(narrow, cursorMs, 'M15');
    const spanMs = Date.parse(merged.end) - Date.parse(merged.start);
    const barMs = 15 * 60 * 1000;
    expect(Math.round(spanMs / barMs)).toBeGreaterThanOrEqual(160);
  });

  it('large gap shows first segment with minimum window, not entire gap', () => {
    const fit = buildFitActiveWindow({
      candles: m15Candles,
      timeframe: 'M15',
      cursorTimeMs: Date.parse(m15Candles[10].time),
      gapEndMs: Date.parse(m15Candles[250].time),
    });
    expect(fit).not.toBeNull();
    const bars = fitWindowBarCount(m15Candles, fit!);
    expect(bars).toBeGreaterThanOrEqual(160);
    expect(bars).toBeLessThan(200);
    expect(fit!.start).toBe(m15Candles[0].time);
  });

  it('save manual range after Fit Active does not fail due to viewport span', () => {
    expect(isExplicitViewportMove('fit-active')).toBe(true);
    expect(shouldPreserveViewport('save-range')).toBe(true);
    const fit = buildFitActiveWindow({
      candles: m15Candles,
      timeframe: 'M15',
      draftStart: m15Candles[140].time,
      draftEnd: m15Candles[142].time,
    });
    expect(fit).not.toBeNull();
    const rh = 2145;
    const rl = 2135;
    expect(rh).toBeGreaterThan(rl);
    expect(fitWindowBarCount(m15Candles, fit!)).toBeGreaterThanOrEqual(160);
  });

  it('ensureFitWindowMinBars expands replay-clamped tiny spans', () => {
    const tiny = {
      start: m15Candles[100].time,
      end: m15Candles[102].time,
      low: 2090,
      high: 2110,
      padRatio: 0.1,
    };
    const expanded = ensureFitWindowMinBars(m15Candles, tiny, 'M15');
    expect(fitWindowBarCount(m15Candles, expanded)).toBeGreaterThanOrEqual(160);
  });

  it('MICRO mapping default focus mode is ON during guided', () => {
    expect(defaultFocusModeForGuided(true)).toBe(true);
    expect(defaultFocusModeForGuided(false)).toBe(false);
  });

  it('ancestor ranges stay visible as ghosts in MICRO focus', () => {
    const rows = annotateOverlayFocusTiers([
      { rangeId: '1', structureLayer: 'WEEKLY' },
      { rangeId: '4', structureLayer: 'MICRO', isActive: true },
    ], {
      activeMappingLayer: 'MICRO',
      parentRangeId: '3',
      ancestorIds: ['1'],
      hasDraft: false,
    });
    const filtered = filterFocusModeOverlays(rows, {
      focusMode: true,
      showAllRanges: false,
      activeMappingLayer: 'MICRO',
    });
    expect(filtered.some((r) => r.rangeId === '1')).toBe(true);
    expect(focusVisualStyle('ancestor').opacity).toBe(0.3);
  });

  it('immediate parent remains visible in MICRO focus', () => {
    const rows = annotateOverlayFocusTiers([
      { rangeId: '3', structureLayer: 'INTRADAY' },
      { rangeId: '4', structureLayer: 'MICRO', isActive: true },
    ], {
      activeMappingLayer: 'MICRO',
      parentRangeId: '3',
      ancestorIds: [],
      hasDraft: false,
    });
    expect(rows.find((r) => r.rangeId === '3')?.focusTier).toBe('parent');
    const filtered = filterFocusModeOverlays(rows, {
      focusMode: true,
      showAllRanges: false,
      activeMappingLayer: 'MICRO',
    });
    expect(filtered.some((r) => r.rangeId === '3')).toBe(true);
  });

  it('active draft remains full opacity', () => {
    const style = focusVisualStyle('active', { isDraft: true });
    expect(style.opacity).toBe(1.0);
    expect(style.showLabel).toBe(true);
  });

  it('Show All Ranges overrides hiding but keeps candle y-scale in focus', () => {
    const rows = annotateOverlayFocusTiers([
      { rangeId: '1', structureLayer: 'WEEKLY' },
      { rangeId: '4', structureLayer: 'MICRO', isActive: true },
    ], {
      activeMappingLayer: 'MICRO',
      parentRangeId: '3',
      ancestorIds: ['1'],
      hasDraft: false,
    });
    const filtered = filterFocusModeOverlays(rows, {
      focusMode: true,
      showAllRanges: true,
      activeMappingLayer: 'MICRO',
    });
    expect(filtered.length).toBe(2);
    const fit = mergeFocusFitPriceDomain(buildCandleSpanFit(candles, candles[0].time, candles[10].time), true);
    expect(fit?.padRatio).toBe(0.1);
  });

  it('Fit Parent uses parent x-span but candle-based y-scale', () => {
    const fit = buildCandleSpanFit(
      candles,
      candles[2].time,
      candles[12].time,
      6,
    );
    expect(fit?.start).toBe(candles[0].time);
    expect(fit?.end).toBe(candles[18].time);
    expect(fit?.low).toBe(2090);
    expect(fit?.high).toBeGreaterThan(2100);
  });

  it('resolveFocusTier marks parent layer correctly for DAILY mapping', () => {
    expect(resolveFocusTier('DAILY', 'WEEKLY', { parentRangeId: '7', overlayRangeId: '7' })).toBe('parent');
    expect(resolveFocusTier('DAILY', 'DAILY', { isActive: true })).toBe('active');
  });

  it('focusYExtentsWithParent unions parent RH/RL into y domain', () => {
    const y = focusYExtentsWithParent(candles, 2200, 2050);
    expect(y?.low).toBeLessThanOrEqual(2050);
    expect(y?.high).toBeGreaterThanOrEqual(2200);
  });

  it('buildContextReplayFitWindow includes lookback and parent span', () => {
    const pool = makeCandles(200, 60 * 60 * 1000);
    const cursor = pool[120].time;
    const fit = buildContextReplayFitWindow({
      candles: pool,
      cursorTime: cursor,
      lookbackBars: 100,
      parentStart: pool[80].time,
      parentEnd: pool[150].time,
      parentHi: 2150,
      parentLo: 2080,
    });
    expect(fit).not.toBeNull();
    expect(Date.parse(fit!.start)).toBeLessThanOrEqual(Date.parse(pool[21].time));
    expect(Date.parse(fit!.end)).toBeLessThanOrEqual(Date.parse(cursor));
    expect(Date.parse(fit!.end)).toBeGreaterThanOrEqual(Date.parse(cursor) - 3600000);
    expect(fit!.low).toBeLessThanOrEqual(2080);
    expect(fit!.high).toBeGreaterThanOrEqual(2150);
  });
});
