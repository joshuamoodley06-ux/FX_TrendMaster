import { describe, expect, it } from 'vitest';
import {
  buildTradingViewSelectedCandleFromBarIndex,
  buildTradingViewSelectedCandle,
  resolveFxtmCandleFromTvTime,
  selectionMarkerFromSelectedCandle,
} from './selectedCandleBridge';

const candles = [
  { symbol: 'XAUUSD', timeframe: 'H1', time: '2024.11.04 08:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
  { symbol: 'XAUUSD', timeframe: 'H1', time: '2024.11.04 09:00', open: 2, high: 3, low: 1.5, close: 2.5, volume: 11 },
];

describe('resolveFxtmCandleFromTvTime', () => {
  it('returns the exact FXTM candle and bar index for matching intraday TV seconds', () => {
    const tvSeconds = Date.UTC(2024, 10, 4, 9, 0, 0) / 1000;
    const match = resolveFxtmCandleFromTvTime(candles, 'H1', tvSeconds);

    expect(match?.barIndex).toBe(1);
    expect(match?.candle.time).toBe('2024.11.04 09:00');
  });

  it('returns null instead of guessing nearest candle', () => {
    const nearButMissing = Date.UTC(2024, 10, 4, 9, 30, 0) / 1000;

    expect(resolveFxtmCandleFromTvTime(candles, 'H1', nearButMissing)).toBeNull();
  });

  it('uses exact business-day keys for W1/D1 candles', () => {
    const match = resolveFxtmCandleFromTvTime([
      { time: '2024.11.04 00:00', open: 1, high: 2, low: 0.5, close: 1.5 },
    ], 'D1', { year: 2024, month: 11, day: 4 });

    expect(match?.barIndex).toBe(0);
    expect(match?.candle.time).toBe('2024.11.04 00:00');
  });

  it('ignores invalid candle rows', () => {
    const match = resolveFxtmCandleFromTvTime([
      { time: '2024.11.04 09:00', open: 1, high: Number.NaN, low: 0.5, close: 1.5 },
    ], 'H1', Date.UTC(2024, 10, 4, 9, 0, 0) / 1000);

    expect(match).toBeNull();
  });
});

describe('buildTradingViewSelectedCandleFromBarIndex', () => {
  it('resolves an exact adapted bar index without synthesizing rows', () => {
    const selected = buildTradingViewSelectedCandleFromBarIndex({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      barIndex: 1,
    });

    expect(selected?.time).toBe('2024.11.04 09:00');
    expect(selected?.barIndex).toBe(1);
  });

  it('returns null for out-of-range bar indexes', () => {
    expect(buildTradingViewSelectedCandleFromBarIndex({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      barIndex: 10,
    })).toBeNull();
  });
});

describe('buildTradingViewSelectedCandle', () => {
  it('builds the canonical selected candle payload', () => {
    const selected = buildTradingViewSelectedCandle({
      symbol: 'xauusd',
      chartTimeframe: 'h1',
      sourceTimeframe: 'D1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
    });

    expect(selected).toMatchObject({
      source: 'tradingview',
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      sourceTimeframe: 'D1',
      time: '2024.11.04 08:00',
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
      volume: 10,
      barIndex: 0,
    });
  });

  it('creates a distinct selection marker from the selected candle', () => {
    const selected = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
    });
    const marker = selectionMarkerFromSelectedCandle(selected);

    expect(marker).toMatchObject({
      shape: 'circle',
      text: 'SEL',
      position: 'belowBar',
    });
  });
});
