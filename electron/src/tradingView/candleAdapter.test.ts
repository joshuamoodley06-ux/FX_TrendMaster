import { describe, expect, it } from 'vitest';
import {
  adaptCandlesForTradingView,
  adaptReplayStepFitForTradingView,
  applyChartModeWindow,
  buildPaddedReplayFitWindow,
  computeReplayAnchorLogicalRange,
  isReplaySelectableCandle,
} from './candleAdapter';

const makeCandles = (count: number, startHour = 0) => Array.from({ length: count }, (_, index) => ({
  time: `2024.11.${String(1 + Math.floor((startHour + index) / 24)).padStart(2, '0')} ${String((startHour + index) % 24).padStart(2, '0')}:00`,
  open: index,
  high: index + 1,
  low: index - 1,
  close: index + 0.5,
}));

describe('adaptCandlesForTradingView', () => {
  it('sorts intraday candles ascending and converts time to unix seconds', () => {
    const result = adaptCandlesForTradingView([
      { time: '2024.11.04 02:00', open: 2, high: 3, low: 1, close: 2.5 },
      { time: '2024.11.04 01:00', open: 1, high: 2, low: 0.5, close: 1.5 },
    ], 'H1');

    expect(result.dropped).toBe(0);
    expect(result.bars).toHaveLength(2);
    expect(typeof result.bars[0].time).toBe('number');
    expect(Number(result.bars[0].time)).toBeLessThan(Number(result.bars[1].time));
  });

  it('uses business-day time for W1 and D1 candles', () => {
    const result = adaptCandlesForTradingView([
      { time: '2024.11.04 00:00', open: 1, high: 2, low: 0.5, close: 1.5 },
    ], 'D1');

    expect(result.bars[0].time).toEqual({ year: 2024, month: 11, day: 4 });
  });

  it('drops invalid OHLC and invalid time rows', () => {
    const result = adaptCandlesForTradingView([
      { time: 'bad', open: 1, high: 2, low: 0.5, close: 1.5 },
      { time: '2024.11.04 01:00', open: 1, high: Number.NaN, low: 0.5, close: 1.5 },
      { time: '2024.11.04 02:00', open: 2, high: 3, low: 1, close: 2.5 },
    ], 'H1');

    expect(result.dropped).toBe(2);
    expect(result.bars).toHaveLength(1);
  });

  it('dedupes by TradingView time key with last row winning', () => {
    const result = adaptCandlesForTradingView([
      { time: '2024.11.04 01:00', open: 1, high: 2, low: 0.5, close: 1.5 },
      { time: '2024.11.04 01:00', open: 10, high: 20, low: 5, close: 15 },
    ], 'H1');

    expect(result.bars).toHaveLength(1);
    expect(result.bars[0].open).toBe(10);
    expect(result.bars[0].close).toBe(15);
  });

  it('does not synthesize missing candles', () => {
    const result = adaptCandlesForTradingView([
      { time: '2024.11.04 01:00', open: 1, high: 2, low: 0.5, close: 1.5 },
      { time: '2024.11.04 04:00', open: 4, high: 5, low: 3, close: 4.5 },
    ], 'H1');

    expect(result.bars).toHaveLength(2);
  });
});

describe('applyChartModeWindow', () => {
  it('returns the latest N candles for W1/D1 latest mode', () => {
    const result = applyChartModeWindow(makeCandles(350), { mode: 'latest', timeframe: 'D1' });

    expect(result).toHaveLength(180);
    expect(result[0].time).toBe(makeCandles(350)[170].time);
    expect(result.at(-1)?.time).toBe(makeCandles(350)[349].time);
  });

  it('returns full loaded history for lower-timeframe latest display mode', () => {
    const full = makeCandles(350);
    const result = applyChartModeWindow(full, { mode: 'latest', timeframe: 'H4' });

    expect(result).toHaveLength(full.length);
    expect(result[0].time).toBe(full[0].time);
  });

  it('returns full loaded history in explicit full mode', () => {
    const full = makeCandles(120);
    const result = applyChartModeWindow(full, { mode: 'full', timeframe: 'H1' });

    expect(result).toHaveLength(full.length);
  });

  it('keeps full loaded history in hierarchy mode (camera fit only)', () => {
    const full = makeCandles(12);
    const result = applyChartModeWindow(full, {
      mode: 'hierarchy',
      timeframe: 'H1',
      hierarchyStart: '2024.11.01 03:00',
      hierarchyEnd: '2024.11.01 06:00',
    });

    expect(result).toHaveLength(full.length);
    expect(result[0].time).toBe(full[0].time);
    expect(result.at(-1)?.time).toBe(full.at(-1)?.time);
  });

  it('caps replay mode at the replay cursor', () => {
    const result = applyChartModeWindow(makeCandles(8), {
      mode: 'replay',
      timeframe: 'H1',
      replayCutTime: '2024.11.01 04:00',
    });

    expect(result).toHaveLength(5);
    expect(result.at(-1)?.time).toBe('2024.11.01 04:00');
  });

  it('removes future candles from the selection surface', () => {
    const displayed = applyChartModeWindow(makeCandles(8), {
      mode: 'replay',
      timeframe: 'H1',
      replayCutTime: '2024.11.01 04:00',
    });

    expect(displayed.some((c) => c.time === '2024.11.01 05:00')).toBe(false);
  });

  it('normal latest mode clears prior hierarchy and replay cutoffs', () => {
    const result = applyChartModeWindow(makeCandles(6), {
      mode: 'latest',
      timeframe: 'H1',
      hierarchyEnd: '2024.11.01 02:00',
      replayCutTime: '2024.11.01 02:00',
    });

    expect(result).toHaveLength(6);
    expect(result.at(-1)?.time).toBe('2024.11.01 05:00');
  });

  it('latest mode ignores replayCutTime when not in replay mode', () => {
    const result = applyChartModeWindow(makeCandles(8), {
      mode: 'latest',
      timeframe: 'H1',
      replayCutTime: '2024.11.01 04:00',
    });

    expect(result).toHaveLength(8);
    expect(result.some((c) => c.time === '2024.11.01 07:00')).toBe(true);
  });

  it('replay mode cuts display slice without requiring explicit Bar Replay flag', () => {
    const full = makeCandles(8);
    const result = applyChartModeWindow(full, {
      mode: 'replay',
      timeframe: 'H1',
      replayCutTime: '2024.11.01 04:00',
    });

    expect(result.length).toBeLessThan(full.length);
    expect(result.some((c) => c.time === '2024.11.01 07:00')).toBe(false);
    expect(full).toHaveLength(8);
  });
});

describe('buildPaddedReplayFitWindow', () => {
  it('pads before cursor and ends near cursor', () => {
    const candles = makeCandles(20);
    const fit = buildPaddedReplayFitWindow(candles, '2024.11.01 10:00', 4);

    expect(fit?.start).toBe('2024.11.01 02:00');
    expect(fit?.end).toBe('2024.11.01 12:00');
  });
});

describe('computeReplayAnchorLogicalRange', () => {
  it('skips when cursor remains inside the visible logical window', () => {
    expect(computeReplayAnchorLogicalRange({
      cursorLogical: 25,
      visible: { from: 20, to: 40 },
      barCount: 50,
    })).toEqual({ action: 'skip' });
  });

  it('pans right while preserving span when cursor exits the right edge', () => {
    const result = computeReplayAnchorLogicalRange({
      cursorLogical: 45,
      visible: { from: 20, to: 40 },
      barCount: 50,
    });
    expect(result.action).toBe('pan');
    if (result.action === 'pan') {
      expect(result.range.to - result.range.from).toBeCloseTo(20, 0);
      expect(result.range.to).toBeGreaterThanOrEqual(45);
    }
  });

  it('requests initial fit when no visible range exists yet', () => {
    expect(computeReplayAnchorLogicalRange({
      cursorLogical: 10,
      visible: null,
      barCount: 50,
    })).toEqual({ action: 'initial' });
  });
});

describe('adaptReplayStepFitForTradingView', () => {
  it('returns a fit request with padded from/to around cursor', () => {
    const fit = adaptReplayStepFitForTradingView(makeCandles(12), '2024.11.01 06:00', 'H1', 7, 4);

    expect(fit?.token).toBe(7);
    expect(typeof fit?.from).toBe('number');
    expect(typeof fit?.to).toBe('number');
    expect(Number(fit?.from)).toBeLessThan(Number(fit?.to));
  });

  it('fits within replay display slice so to does not extend past cursor', () => {
    const full = makeCandles(12);
    const sliced = applyChartModeWindow(full, {
      mode: 'replay',
      timeframe: 'H1',
      replayCutTime: '2024.11.01 06:00',
    });
    const fit = adaptReplayStepFitForTradingView(sliced, '2024.11.01 06:00', 'H1', 8, 4);

    expect(fit?.to).toBeDefined();
    expect(Number(fit?.to)).toBeLessThanOrEqual(Number(fit?.from) + 86400 * 7);
  });
});

describe('isReplaySelectableCandle', () => {
  it('allows any candle when replay mode is off', () => {
    expect(isReplaySelectableCandle('2024.11.04 09:00', '2024.11.04 08:00', false)).toBe(true);
  });

  it('allows historical bars at or before replay cursor', () => {
    expect(isReplaySelectableCandle('2024.11.04 08:00', '2024.11.04 09:00', true)).toBe(true);
    expect(isReplaySelectableCandle('2024.11.04 09:00', '2024.11.04 09:00', true)).toBe(true);
  });

  it('blocks future bars after replay cursor', () => {
    expect(isReplaySelectableCandle('2024.11.04 10:00', '2024.11.04 09:00', true)).toBe(false);
  });
});
