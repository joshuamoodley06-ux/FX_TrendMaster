import type { Time } from 'lightweight-charts';
import { fxtmTimeToTradingViewTime, isReplaySelectableCandle, timeSortKey } from './candleAdapter';
import type { FxtmCandleRow, TradingViewBosMarker, TradingViewSelectedCandle } from './types';

export type TradingViewTimeScaleProbe = {
  coordinateToTime: (x: number) => Time | null;
  coordinateToLogical: (x: number) => number | null;
  timeToCoordinate: (time: Time) => number | null;
  logicalToCoordinate: (logical: number) => number | null;
};

export type TradingViewSelectionResolve = {
  selected: TradingViewSelectedCandle | null;
  rawTvTime: Time | null;
  normalizedTime: string;
};

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

function barSlotHalfWidth(
  timeScale: TradingViewTimeScaleProbe,
  barIndex: number,
  barCount: number,
): number | null {
  const center = timeScale.logicalToCoordinate(barIndex);
  if (center == null) return null;
  const prev = barIndex > 0 ? timeScale.logicalToCoordinate(barIndex - 1) : null;
  const next = barIndex < barCount - 1 ? timeScale.logicalToCoordinate(barIndex + 1) : null;
  if (prev != null && next != null) return Math.min(Math.abs(center - prev), Math.abs(next - center)) / 2;
  if (next != null) return Math.abs(next - center) / 2;
  if (prev != null) return Math.abs(center - prev) / 2;
  return 4;
}

export function findDisplayedBarIndexUnderPointer(
  x: number,
  displayedBarCount: number,
  timeScale: TradingViewTimeScaleProbe,
): number | null {
  if (displayedBarCount <= 0) return null;
  const logical = timeScale.coordinateToLogical(x);
  if (logical == null || !Number.isFinite(logical)) return null;
  const barIndex = Math.round(logical);
  if (barIndex < 0 || barIndex >= displayedBarCount) return null;
  const center = timeScale.logicalToCoordinate(barIndex);
  if (center == null) return null;
  const halfWidth = barSlotHalfWidth(timeScale, barIndex, displayedBarCount);
  if (halfWidth == null) return null;
  if (Math.abs(x - center) > halfWidth) return null;
  return barIndex;
}

export function resolveTradingViewSelectionAtX(args: {
  x: number;
  symbol: string;
  chartTimeframe: string;
  sourceTimeframe?: string;
  candles: FxtmCandleRow[];
  displayedBarCount: number;
  timeScale: TradingViewTimeScaleProbe;
}): TradingViewSelectionResolve {
  const rawTvTime = args.timeScale.coordinateToTime(args.x);
  const normalizedFromRaw = tvTimeKey(rawTvTime);
  const barIndex = findDisplayedBarIndexUnderPointer(args.x, args.displayedBarCount, args.timeScale);
  if (barIndex == null) {
    return { selected: null, rawTvTime, normalizedTime: normalizedFromRaw };
  }

  const selected = buildTradingViewSelectedCandleFromBarIndex({
    symbol: args.symbol,
    chartTimeframe: args.chartTimeframe,
    sourceTimeframe: args.sourceTimeframe,
    candles: args.candles,
    barIndex,
  });
  if (!selected) {
    return { selected: null, rawTvTime, normalizedTime: normalizedFromRaw };
  }

  return {
    selected,
    rawTvTime,
    normalizedTime: tvTimeKey(selected.tvTime),
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

export function tradingViewSelectedMatchesDisplayedCandles(
  selected: TradingViewSelectedCandle | null | undefined,
  displayedCandles: FxtmCandleRow[],
): boolean {
  if (!selected?.time) return false;
  const targetTime = String(selected.time);
  return (displayedCandles || []).some((c) => String(c?.time || '') === targetTime);
}

export type TradingViewSelectionAdmissionResult = {
  admitted: boolean;
  message: string;
  mappingInputCandle: MappingInputCandle | null;
};

function mappingInputCandleFromDisplayRow(
  row: FxtmCandleRow,
  symbol: string,
  chartTimeframe: string,
): MappingInputCandle | null {
  if (!row?.time || !finiteOhlc(row)) return null;
  return {
    symbol: String(symbol || row.symbol || '').toUpperCase(),
    timeframe: String(chartTimeframe || row.timeframe || '').toUpperCase(),
    time: String(row.time),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: row.volume === undefined ? undefined : Number(row.volume),
  };
}

export type TvMappingSelectionState = {
  mappingInputCandle: MappingInputCandle | null;
  tradingViewSelectedCandle: TradingViewSelectedCandle | null;
};

/** Derive SEL visual payload from the admitted canonical row — never from a separate click candidate. */
export function mappingInputCandleToTradingViewSelectedCandle(
  row: MappingInputCandle,
  sourceTimeframe?: string,
): TradingViewSelectedCandle | null {
  if (!row?.time || !finiteOhlc(row)) return null;
  const adaptedTime = fxtmTimeToTradingViewTime(row.time, row.timeframe);
  if (!adaptedTime) return null;
  return {
    source: 'tradingview',
    symbol: String(row.symbol || '').toUpperCase(),
    chartTimeframe: String(row.timeframe || '').toUpperCase(),
    sourceTimeframe: sourceTimeframe ? String(sourceTimeframe).toUpperCase() : undefined,
    time: String(row.time),
    tvTime: tvTimePayload(adaptedTime),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: row.volume === undefined ? undefined : Number(row.volume),
  };
}

/** Sync Architect commit — one admitted row drives mapping input + SEL visual together. */
export function commitTvMappingSelection(args: {
  row: MappingInputCandle;
  sourceTimeframe?: string;
}): TvMappingSelectionState | null {
  const tradingViewSelectedCandle = mappingInputCandleToTradingViewSelectedCandle(args.row, args.sourceTimeframe);
  if (!tradingViewSelectedCandle) return null;
  return { mappingInputCandle: args.row, tradingViewSelectedCandle };
}

/** Paired clear — visual + admitted row must invalidate together. */
export function clearTvMappingSelection(): TvMappingSelectionState {
  return { mappingInputCandle: null, tradingViewSelectedCandle: null };
}

/** Sync Architect admission — exact displayed row only; returns canonical MappingInputCandle from that row. */
export function admitTradingViewSelection(args: {
  candidate: TradingViewSelectedCandle | null | undefined;
  displayedCandles: FxtmCandleRow[];
  symbol: string;
  chartTimeframe: string;
  candleReplayMode?: boolean;
  replayCutTime?: string | null;
}): TradingViewSelectionAdmissionResult {
  if (!args.candidate?.time) {
    return { admitted: false, message: 'Click a visible TradingView candle first.', mappingInputCandle: null };
  }
  const targetTime = String(args.candidate.time);
  if (!isReplaySelectableCandle(targetTime, args.replayCutTime, !!args.candleReplayMode)) {
    return { admitted: false, message: 'Selection blocked — that candle is after the replay cursor.', mappingInputCandle: null };
  }
  const matchedRow = (args.displayedCandles || []).find((c) => String(c?.time || '') === targetTime);
  if (!matchedRow) {
    return { admitted: false, message: 'Selection blocked — click a visible candle on the chart.', mappingInputCandle: null };
  }
  const mappingInputCandle = mappingInputCandleFromDisplayRow(
    matchedRow,
    args.symbol,
    args.chartTimeframe,
  );
  if (!mappingInputCandle) {
    return { admitted: false, message: 'Selection blocked — invalid displayed candle row.', mappingInputCandle: null };
  }
  return { admitted: true, message: '', mappingInputCandle };
}

/** Replay SEL visual — click-admitted bar wins; replay cursor is fallback only. */
export function resolveVisualTradingViewSelectedCandle(args: {
  mappingInputEnabled: boolean;
  candleReplayMode: boolean;
  replayCandle: FxtmCandleRow | null | undefined;
  displayedCandles: FxtmCandleRow[];
  admittedSelectedCandle: TradingViewSelectedCandle | null;
  fallbackSelectedCandle: TradingViewSelectedCandle | null;
  symbol: string;
  chartTimeframe: string;
  sourceTimeframe?: string;
}): TradingViewSelectedCandle | null {
  const replayCutTime = args.replayCandle?.time ?? null;
  if (args.mappingInputEnabled && args.admittedSelectedCandle?.time
    && isReplaySelectableCandle(args.admittedSelectedCandle.time, replayCutTime, args.candleReplayMode)) {
    return args.admittedSelectedCandle;
  }
  if (args.mappingInputEnabled && args.candleReplayMode && args.replayCandle?.time) {
    const targetTime = String(args.replayCandle.time);
    const inDisplay = (args.displayedCandles || []).some((c) => String(c?.time || '') === targetTime);
    if (inDisplay) {
      const adaptedTime = fxtmTimeToTradingViewTime(args.replayCandle.time, args.chartTimeframe);
      const fromReplay = buildTradingViewSelectedCandle({
        symbol: args.symbol,
        chartTimeframe: args.chartTimeframe,
        sourceTimeframe: args.sourceTimeframe,
        candles: args.displayedCandles,
        tvTime: adaptedTime,
      });
      if (fromReplay) return fromReplay;
    }
  }
  if (args.mappingInputEnabled) return args.admittedSelectedCandle;
  return args.fallbackSelectedCandle;
}

/** TV Map On uses click-admitted canonical row; D3 prefers explicit selection before replay cursor fallback. */
export function resolveMappingInputCandle(args: {
  chartRenderer: string;
  mappingInputEnabled: boolean;
  admittedMappingInputCandle: MappingInputCandle | null | undefined;
  selectedCandle: FxtmCandleRow | null | undefined;
  replayCandle: FxtmCandleRow | null | undefined;
  candleReplayMode?: boolean;
  allowSelectedFallbackWhenMappingInputEnabled?: boolean;
}): MappingInputCandle | null {
  const replayCutTime = args.replayCandle?.time ?? null;
  const replayMode = !!args.candleReplayMode;
  if (args.chartRenderer === 'tradingview' && args.mappingInputEnabled) {
    if (args.admittedMappingInputCandle?.time
      && isReplaySelectableCandle(args.admittedMappingInputCandle.time, replayCutTime, replayMode)) {
      return args.admittedMappingInputCandle;
    }
    if (args.allowSelectedFallbackWhenMappingInputEnabled
      && args.selectedCandle?.time
      && isReplaySelectableCandle(args.selectedCandle.time, replayCutTime, replayMode)) {
      return args.selectedCandle as MappingInputCandle;
    }
    return null;
  }
  if (args.selectedCandle?.time
    && isReplaySelectableCandle(args.selectedCandle.time, replayCutTime, replayMode)) {
    return args.selectedCandle as MappingInputCandle;
  }
  if (replayMode && args.replayCandle) {
    return args.replayCandle as MappingInputCandle;
  }
  return (args.replayCandle as MappingInputCandle | null) || null;
}

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
