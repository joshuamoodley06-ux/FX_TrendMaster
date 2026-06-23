import { describe, expect, it } from 'vitest';
import { adaptCandlesForTradingView, applyChartModeWindow } from './candleAdapter';

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
  it('returns the latest N candles for latest mode', () => {
    const result = applyChartModeWindow(makeCandles(350), { mode: 'latest', timeframe: 'H1' });

    expect(result).toHaveLength(300);
    expect(result[0].time).toBe(makeCandles(350)[50].time);
    expect(result.at(-1)?.time).toBe(makeCandles(350)[349].time);
  });

  it('caps hierarchy mode at the range display window', () => {
    const result = applyChartModeWindow(makeCandles(12), {
      mode: 'hierarchy',
      timeframe: 'H1',
      hierarchyStart: '2024.11.01 03:00',
      hierarchyEnd: '2024.11.01 06:00',
    });

    expect(result.map((c) => c.time)).toEqual([
      '2024.11.01 03:00',
      '2024.11.01 04:00',
      '2024.11.01 05:00',
      '2024.11.01 06:00',
    ]);
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
});
