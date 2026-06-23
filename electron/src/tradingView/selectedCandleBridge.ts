import type { Time } from 'lightweight-charts';
import { fxtmTimeToTradingViewTime, timeSortKey } from './candleAdapter';
import type { FxtmCandleRow, TradingViewBosMarker, TradingViewSelectedCandle } from './types';

function tvTimeKey(time: Time | string | number | null | undefined): string {
  if (time == null) return '';
  if (typeof time === 'number') return String(time);
  if (typeof time === 'string') return time;
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
}

function tvTimePayload(time: Time): string | number {
  if (typeof time === 'number' || typeof time === 'string') return time;
  return tvTimeKey(time);
}

function finiteOhlc(candle: FxtmCandleRow): boolean {
  return Number.isFinite(Number(candle.open))
    && Number.isFinite(Number(candle.high))
    && Number.isFinite(Number(candle.low))
    && Number.isFinite(Number(candle.close));
}

export function resolveFxtmCandleFromTvTime(
  candles: FxtmCandleRow[],
  timeframe: string,
  tvTime: Time | string | number | null | undefined,
): { candle: FxtmCandleRow; barIndex: number; tvTime: Time } | null {
  const targetKey = tvTimeKey(tvTime);
  if (!targetKey) return null;

  for (let index = 0; index < (candles || []).length; index += 1) {
    const candle = candles[index];
    if (!candle?.time || !finiteOhlc(candle)) continue;
    const adaptedTime = fxtmTimeToTradingViewTime(candle.time, timeframe);
    if (!adaptedTime) continue;
    if (tvTimeKey(adaptedTime) === targetKey) {
      return { candle, barIndex: index, tvTime: adaptedTime };
    }
  }

  return null;
}

export function buildTradingViewSelectedCandle(args: {
  symbol: string;
  chartTimeframe: string;
  sourceTimeframe?: string;
  candles: FxtmCandleRow[];
  tvTime: Time | string | number | null | undefined;
}): TradingViewSelectedCandle | null {
  const match = resolveFxtmCandleFromTvTime(args.candles, args.chartTimeframe, args.tvTime);
  if (!match) return null;
  return {
    source: 'tradingview',
    symbol: String(args.symbol || '').toUpperCase(),
    chartTimeframe: String(args.chartTimeframe || '').toUpperCase(),
    sourceTimeframe: args.sourceTimeframe ? String(args.sourceTimeframe).toUpperCase() : undefined,
    time: String(match.candle.time),
    tvTime: tvTimePayload(match.tvTime),
    open: Number(match.candle.open),
    high: Number(match.candle.high),
    low: Number(match.candle.low),
    close: Number(match.candle.close),
    volume: match.candle.volume === undefined ? undefined : Number(match.candle.volume),
    barIndex: match.barIndex,
  };
}

export function buildTradingViewSelectedCandleFromBarIndex(args: {
  symbol: string;
  chartTimeframe: string;
  sourceTimeframe?: string;
  candles: FxtmCandleRow[];
  barIndex: number;
}): TradingViewSelectedCandle | null {
  const targetIndex = Math.round(Number(args.barIndex));
  if (!Number.isInteger(targetIndex) || targetIndex < 0) return null;
  const byTime = new Map<string, { candle: FxtmCandleRow; tvTime: Time }>();
  for (const candle of args.candles || []) {
    if (!candle?.time || !finiteOhlc(candle)) continue;
    const adaptedTime = fxtmTimeToTradingViewTime(candle.time, args.chartTimeframe);
    if (!adaptedTime) continue;
    byTime.set(tvTimeKey(adaptedTime), { candle, tvTime: adaptedTime });
  }
  const rendered = Array.from(byTime.values()).sort((a, b) => timeSortKey(a.tvTime) - timeSortKey(b.tvTime));
  const match = rendered[targetIndex];
  if (match) {
    const candle = match.candle;
    return {
      source: 'tradingview',
      symbol: String(args.symbol || '').toUpperCase(),
      chartTimeframe: String(args.chartTimeframe || '').toUpperCase(),
      sourceTimeframe: args.sourceTimeframe ? String(args.sourceTimeframe).toUpperCase() : undefined,
      time: String(candle.time),
      tvTime: tvTimePayload(match.tvTime),
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close),
      volume: candle.volume === undefined ? undefined : Number(candle.volume),
      barIndex: targetIndex,
    };
  }
  return null;
}

export type MappingInputCandle = {
  symbol: string;
  timeframe: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export function tradingViewSelectedCandleToCandle(
  selected: TradingViewSelectedCandle | null | undefined,
  fallbackSymbol?: string,
  fallbackTimeframe?: string,
): MappingInputCandle | null {
  if (!selected?.time) return null;
  const open = Number(selected.open);
  const high = Number(selected.high);
  const low = Number(selected.low);
  const close = Number(selected.close);
  if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
    return null;
  }
  return {
    symbol: String(selected.symbol || fallbackSymbol || '').toUpperCase(),
    timeframe: String(selected.chartTimeframe || fallbackTimeframe || '').toUpperCase(),
    time: String(selected.time),
    open,
    high,
    low,
    close,
    volume: selected.volume === undefined ? undefined : Number(selected.volume),
  };
}

export function selectionMarkerFromSelectedCandle(selected: TradingViewSelectedCandle | null): TradingViewBosMarker | null {
  if (!selected) return null;
  const time = fxtmTimeToTradingViewTime(selected.time, selected.chartTimeframe);
  if (!time) return null;
  return {
    id: `tv-selected:${selected.chartTimeframe}:${selected.time}`,
    time,
    position: 'inBar',
    shape: 'circle',
    color: '#facc15',
    text: 'SEL',
    size: 2,
  };
}
