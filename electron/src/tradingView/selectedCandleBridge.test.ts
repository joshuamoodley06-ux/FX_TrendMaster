import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import {
  admitTradingViewSelection,
  buildTradingViewSelectedCandleFromBarIndex,
  buildTradingViewSelectedCandle,
  clearTvMappingSelection,
  commitTvMappingSelection,
  findDisplayedBarIndexUnderPointer,
  resolveFxtmCandleFromTvTime,
  resolveMappingInputCandle,
  resolveTradingViewSelectionAtX,
  resolveVisualTradingViewSelectedCandle,
  selectionMarkerFromSelectedCandle,
  tradingViewSelectedCandleToCandle,
  tradingViewSelectedMatchesDisplayedCandles,
  type TradingViewTimeScaleProbe,
} from './selectedCandleBridge';

const candles = [
  { symbol: 'XAUUSD', timeframe: 'H1', time: '2024.11.04 08:00', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
  { symbol: 'XAUUSD', timeframe: 'H1', time: '2024.11.04 09:00', open: 2, high: 3, low: 1.5, close: 2.5, volume: 11 },
];

function mockTimeScale(barCenters: number[], barTimes: Time[]): TradingViewTimeScaleProbe {
  const halfWidth = barCenters.length > 1
    ? Math.min(Math.abs(barCenters[1] - barCenters[0]), Math.abs(barCenters.at(-1)! - barCenters.at(-2)!)) / 2
    : 20;

  const findIndex = (x: number): number | null => {
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < barCenters.length; index += 1) {
      const distance = Math.abs(x - barCenters[index]);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    if (bestIndex < 0 || bestDistance > halfWidth) return null;
    return bestIndex;
  };

  return {
    coordinateToLogical: (x) => findIndex(x),
    logicalToCoordinate: (logical) => barCenters[Math.round(logical)] ?? null,
    coordinateToTime: (x) => {
      const index = findIndex(x);
      return index == null ? null : (barTimes[index] ?? null);
    },
    timeToCoordinate: (time) => {
      const index = barTimes.findIndex((entry) => String(entry) === String(time));
      return index >= 0 ? barCenters[index] : null;
    },
  };
}

describe('findDisplayedBarIndexUnderPointer', () => {
  it('returns the bar whose slot contains the pointer x', () => {
    const timeScale = mockTimeScale([100, 200], [1730707200, 1730710800]);
    expect(findDisplayedBarIndexUnderPointer(100, 2, timeScale)).toBe(0);
    expect(findDisplayedBarIndexUnderPointer(200, 2, timeScale)).toBe(1);
  });

  it('blocks loose logical rounding when pointer x is outside that bar slot', () => {
    const timeScale: TradingViewTimeScaleProbe = {
      coordinateToLogical: () => 0.49,
      logicalToCoordinate: (logical) => ([100, 200][Math.round(logical)] ?? null),
      coordinateToTime: () => null,
      timeToCoordinate: () => null,
    };
    expect(findDisplayedBarIndexUnderPointer(155, 2, timeScale)).toBeNull();
    expect(findDisplayedBarIndexUnderPointer(105, 2, timeScale)).toBe(0);
  });
});

describe('resolveTradingViewSelectionAtX', () => {
  it('resolves the exact displayed bar under the pointer', () => {
    const tvTimes = [
      Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
      Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    ] as Time[];
    const timeScale = mockTimeScale([100, 200], tvTimes);
    const resolved = resolveTradingViewSelectionAtX({
      x: 200,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      displayedBarCount: 2,
      timeScale,
    });

    expect(resolved.selected?.time).toBe('2024.11.04 09:00');
    expect(resolved.rawTvTime).toBe(tvTimes[1]);
    expect(resolved.normalizedTime).toBe(String(tvTimes[1]));
  });

  it('blocks selection when coordinateToTime disagrees with the bar under the pointer', () => {
    const tvTimes = [
      Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
      Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    ] as Time[];
    const base = mockTimeScale([100, 200], tvTimes);
    const timeScale: TradingViewTimeScaleProbe = {
      ...base,
      coordinateToTime: () => tvTimes[0],
    };
    const resolved = resolveTradingViewSelectionAtX({
      x: 200,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      displayedBarCount: 2,
      timeScale,
    });

    expect(resolved.selected).toBeNull();
    expect(resolved.rawTvTime).toBe(tvTimes[0]);
  });

  it('returns null instead of width-proportional neighbor guessing', () => {
    const tvTimes = [
      Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
      Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    ] as Time[];
    const timeScale: TradingViewTimeScaleProbe = {
      coordinateToTime: () => null,
      coordinateToLogical: () => null,
      logicalToCoordinate: () => null,
      timeToCoordinate: () => null,
    };
    const resolved = resolveTradingViewSelectionAtX({
      x: 150,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      displayedBarCount: 2,
      timeScale,
    });

    expect(resolved.selected).toBeNull();
  });
});

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

  it('uses rendered sorted order rather than raw input order', () => {
    const selected = buildTradingViewSelectedCandleFromBarIndex({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles: [candles[1], candles[0]],
      barIndex: 0,
    });

    expect(selected?.time).toBe('2024.11.04 08:00');
  });
});

describe('tradingViewSelectedCandleToCandle', () => {
  it('maps a TradingView selected candle into the FXTM candle shape', () => {
    const selected = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });
    const candle = tradingViewSelectedCandleToCandle(selected);

    expect(candle).toMatchObject({
      symbol: 'XAUUSD',
      timeframe: 'H1',
      time: '2024.11.04 09:00',
      open: 2,
      high: 3,
      low: 1.5,
      close: 2.5,
      volume: 11,
    });
  });

  it('returns null for invalid or missing OHLC rows', () => {
    expect(tradingViewSelectedCandleToCandle(null)).toBeNull();
    expect(tradingViewSelectedCandleToCandle({
      source: 'tradingview',
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      time: '2024.11.04 09:00',
      tvTime: 1,
      open: Number.NaN,
      high: 3,
      low: 1.5,
      close: 2.5,
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
      color: '#facc15',
      text: 'SEL',
      position: 'inBar',
      size: 2,
    });
  });

  it('does not resolve candles outside the displayed candle set', () => {
    const displayedCandles = candles.slice(0, 1);

    const selected = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles: displayedCandles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });

    expect(selected).toBeNull();
  });
});

describe('commitTvMappingSelection', () => {
  it('derives SEL visual from the admitted row OHLC/time, not a separate candidate', () => {
    const row = {
      symbol: 'XAUUSD',
      timeframe: 'H1',
      time: '2024.11.04 09:00',
      open: 2,
      high: 3,
      low: 1.5,
      close: 2.5,
      volume: 11,
    };
    const candidate = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles: [{ ...candles[0], high: 99 }],
      tvTime: Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
    });
    const committed = commitTvMappingSelection({ row, sourceTimeframe: 'W1' });
    expect(committed?.mappingInputCandle).toEqual(row);
    expect(committed?.tradingViewSelectedCandle?.high).toBe(3);
    expect(committed?.tradingViewSelectedCandle?.time).toBe('2024.11.04 09:00');
    expect(committed?.tradingViewSelectedCandle?.high).not.toBe(candidate?.high);
    expect(selectionMarkerFromSelectedCandle(committed?.tradingViewSelectedCandle ?? null)?.text).toBe('SEL');
  });
});

describe('clearTvMappingSelection', () => {
  it('clears admitted row and SEL visual together', () => {
    expect(clearTvMappingSelection()).toEqual({
      mappingInputCandle: null,
      tradingViewSelectedCandle: null,
    });
  });
});

describe('resolveMappingInputCandle', () => {
  it('uses admitted canonical row for TV Map On mapping actions', () => {
    const admitted = {
      symbol: 'XAUUSD',
      timeframe: 'H1',
      time: '2024.11.04 09:00',
      open: 2,
      high: 3,
      low: 1.5,
      close: 2.5,
    };
    const candle = resolveMappingInputCandle({
      chartRenderer: 'tradingview',
      mappingInputEnabled: true,
      admittedMappingInputCandle: admitted,
      selectedCandle: candles[0],
      replayCandle: candles[1],
    });
    expect(candle).toEqual(admitted);
  });

  it('keeps D3 selectedCandle path when TV Map is off', () => {
    const candle = resolveMappingInputCandle({
      chartRenderer: 'd3',
      mappingInputEnabled: false,
      admittedMappingInputCandle: null,
      selectedCandle: candles[0],
      replayCandle: candles[1],
    });
    expect(candle?.time).toBe('2024.11.04 08:00');
  });
});

describe('admitTradingViewSelection', () => {
  it('admits an exact displayed candle and returns canonical MappingInputCandle from that row', () => {
    const candidate = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });
    expect(admitTradingViewSelection({
      candidate,
      displayedCandles: candles,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    })).toEqual({
      admitted: true,
      message: '',
      mappingInputCandle: {
        symbol: 'XAUUSD',
        timeframe: 'H1',
        time: '2024.11.04 09:00',
        open: 2,
        high: 3,
        low: 1.5,
        close: 2.5,
        volume: 11,
      },
    });
  });

  it('rejects neighbor/offscreen rows outside the displayed set', () => {
    const candidate = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });
    expect(admitTradingViewSelection({
      candidate,
      displayedCandles: candles.slice(0, 1),
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    })).toEqual({
      admitted: false,
      message: 'Selection blocked — click a visible candle on the chart.',
      mappingInputCandle: null,
    });
  });
});

describe('resolveVisualTradingViewSelectedCandle', () => {
  const admitted = buildTradingViewSelectedCandle({
    symbol: 'XAUUSD',
    chartTimeframe: 'H1',
    candles,
    tvTime: Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
  })!;

  it('uses replay candle for SEL visual during arrow-only replay stepping', () => {
    const visual = resolveVisualTradingViewSelectedCandle({
      mappingInputEnabled: true,
      candleReplayMode: true,
      replayCandle: candles[1],
      displayedCandles: candles,
      admittedSelectedCandle: admitted,
      fallbackSelectedCandle: null,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    });
    expect(visual?.time).toBe('2024.11.04 09:00');
    expect(visual?.time).not.toBe(admitted.time);
  });

  it('uses replay candle visual during explicit Bar Replay', () => {
    const visual = resolveVisualTradingViewSelectedCandle({
      mappingInputEnabled: true,
      candleReplayMode: true,
      replayCandle: candles[1],
      displayedCandles: candles.slice(0, 2),
      admittedSelectedCandle: admitted,
      fallbackSelectedCandle: null,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    });
    expect(visual?.time).toBe('2024.11.04 09:00');
  });

  it('keeps admitted SEL when not in replay mode', () => {
    const visual = resolveVisualTradingViewSelectedCandle({
      mappingInputEnabled: true,
      candleReplayMode: false,
      replayCandle: candles[1],
      displayedCandles: candles,
      admittedSelectedCandle: admitted,
      fallbackSelectedCandle: null,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    });
    expect(visual).toEqual(admitted);
  });

  it('falls back to admitted when replay candle is outside displayed slice', () => {
    const visual = resolveVisualTradingViewSelectedCandle({
      mappingInputEnabled: true,
      candleReplayMode: true,
      replayCandle: candles[1],
      displayedCandles: candles.slice(0, 1),
      admittedSelectedCandle: admitted,
      fallbackSelectedCandle: null,
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
    });
    expect(visual).toEqual(admitted);
  });
});

describe('tradingViewSelectedMatchesDisplayedCandles', () => {
  it('matches when selected time exists in the displayed set', () => {
    const selected = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });

    expect(tradingViewSelectedMatchesDisplayedCandles(selected, candles)).toBe(true);
  });

  it('rejects when selected time is outside the displayed window', () => {
    const selected = buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 9, 0, 0) / 1000,
    });

    expect(tradingViewSelectedMatchesDisplayedCandles(selected, candles.slice(0, 1))).toBe(false);
  });

  it('rejects null or missing selection', () => {
    expect(tradingViewSelectedMatchesDisplayedCandles(null, candles)).toBe(false);
    expect(tradingViewSelectedMatchesDisplayedCandles({ ...buildTradingViewSelectedCandle({
      symbol: 'XAUUSD',
      chartTimeframe: 'H1',
      candles,
      tvTime: Date.UTC(2024, 10, 4, 8, 0, 0) / 1000,
    })!, time: '' }, candles)).toBe(false);
  });
});
