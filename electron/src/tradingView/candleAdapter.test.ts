import { describe, expect, it } from 'vitest';
import { adaptCandlesForTradingView } from './candleAdapter';

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
