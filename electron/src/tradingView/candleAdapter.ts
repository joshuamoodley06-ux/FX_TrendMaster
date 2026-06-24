import type { BusinessDay, Time, UTCTimestamp } from 'lightweight-charts';
import type { FxtmCandleRow, TradingViewAdapterResult, TradingViewCandle, TradingViewChartWindow, TradingViewFitRequest } from './types';

const DAILY_TIMEFRAMES = new Set(['W1', 'D1']);
const LATEST_WINDOW_BY_TIMEFRAME: Record<string, number> = {
  MN1: 80,
  W1: 120,
  D1: 180,
  H4: 240,
  H1: 300,
  M15: 400,
};

export function parseFxtmTime(raw: string): { timestampSeconds: number; businessDay: BusinessDay; key: string } | null {
  const match = String(raw || '').trim().match(/^(\d{4})[.-](\d{2})[.-](\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] ?? 0);
  const minute = Number(match[5] ?? 0);
  const ms = Date.UTC(year, month - 1, day, hour, minute, 0);
  if (!Number.isFinite(ms)) return null;
  return {
    timestampSeconds: Math.floor(ms / 1000),
    businessDay: { year, month, day },
    key: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
  };
}

function isValidOhlc(candle: FxtmCandleRow): candle is Required<Pick<FxtmCandleRow, 'time' | 'open' | 'high' | 'low' | 'close'>> & FxtmCandleRow {
  return !!candle.time
    && Number.isFinite(Number(candle.open))
    && Number.isFinite(Number(candle.high))
    && Number.isFinite(Number(candle.low))
    && Number.isFinite(Number(candle.close));
}

export function timeForTradingView(parsed: NonNullable<ReturnType<typeof parseFxtmTime>>, timeframe: string): Time {
  return DAILY_TIMEFRAMES.has(String(timeframe || '').toUpperCase())
    ? parsed.businessDay
    : parsed.timestampSeconds as UTCTimestamp;
}

export function timeSortKey(time: Time): number {
  if (typeof time === 'number') return time;
  if (typeof time === 'string') return Date.parse(`${time}T00:00:00Z`) / 1000;
  return Math.floor(Date.UTC(time.year, time.month - 1, time.day) / 1000);
}

function timeDedupeKey(time: Time): string {
  if (typeof time === 'number') return String(time);
  if (typeof time === 'string') return time;
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
}

function candleTimeMs(candle: FxtmCandleRow | null | undefined): number {
  const parsed = parseFxtmTime(String(candle?.time || ''));
  return parsed ? parsed.timestampSeconds * 1000 : Number.NaN;
}

function rawTimeMs(raw: string | null | undefined): number {
  const parsed = parseFxtmTime(String(raw || ''));
  return parsed ? parsed.timestampSeconds * 1000 : Number.NaN;
}

export function latestWindowSizeForTimeframe(timeframe: string): number {
  return LATEST_WINDOW_BY_TIMEFRAME[String(timeframe || '').toUpperCase()] || 180;
}

export function fxtmTimeToTradingViewTime(raw: string | null | undefined, timeframe: string): Time | null {
  const parsed = parseFxtmTime(String(raw || ''));
  return parsed ? timeForTradingView(parsed, timeframe) : null;
}

export function adaptCandlesForTradingView(candles: FxtmCandleRow[], timeframe: string): TradingViewAdapterResult {
  const byTime = new Map<string, TradingViewCandle>();
  let dropped = 0;

  for (const candle of candles || []) {
    if (!isValidOhlc(candle)) {
      dropped += 1;
      continue;
    }
    const parsed = parseFxtmTime(candle.time);
    if (!parsed) {
      dropped += 1;
      continue;
    }
    const bar: TradingViewCandle = {
      time: timeForTradingView(parsed, timeframe),
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close),
    };
    byTime.set(timeDedupeKey(bar.time), bar);
  }

  const bars = Array.from(byTime.values()).sort((a, b) => timeSortKey(a.time) - timeSortKey(b.time));
  return { bars, dropped };
}

export type PaddedReplayFitWindow = {
  start: string;
  end: string;
};

function candleIndexAtOrBefore(rows: FxtmCandleRow[], rawTime: string): number {
  const cut = rawTimeMs(rawTime);
  if (!Number.isFinite(cut) || !rows.length) return 0;
  let best = 0;
  for (let i = 0; i < rows.length; i += 1) {
    const ms = candleTimeMs(rows[i]);
    if (!Number.isFinite(ms) || ms > cut) break;
    best = i;
  }
  return best;
}

/** Padded visible time window centered/ending near replay cursor (full candle rows). */
export function buildPaddedReplayFitWindow(
  candles: FxtmCandleRow[],
  cursorTime: string,
  padBars: number,
): PaddedReplayFitWindow | null {
  const rows = (candles || [])
    .filter((c) => !!c?.time && Number.isFinite(candleTimeMs(c)))
    .sort((a, b) => candleTimeMs(a) - candleTimeMs(b));
  if (!rows.length || !cursorTime) return null;
  const idx = candleIndexAtOrBefore(rows, cursorTime);
  const pad = Math.max(8, padBars);
  const forwardPad = Math.max(2, Math.round(pad * 0.2));
  const i0 = Math.max(0, idx - pad);
  const i1 = Math.min(rows.length - 1, idx + forwardPad);
  return { start: String(rows[i0].time), end: String(rows[i1].time) };
}

export function adaptReplayStepFitForTradingView(
  candles: FxtmCandleRow[],
  cursorTime: string,
  timeframe: string,
  token: number,
  padBars: number,
): TradingViewFitRequest | null {
  if (!Number.isFinite(token) || token <= 0) return null;
  const window = buildPaddedReplayFitWindow(candles, cursorTime, padBars);
  if (!window) return null;
  const from = fxtmTimeToTradingViewTime(window.start, timeframe);
  const to = fxtmTimeToTradingViewTime(window.end, timeframe);
  const target = fxtmTimeToTradingViewTime(cursorTime, timeframe);
  if (!from || !to) return null;
  return { token, from, to, target: target || undefined };
}

export function applyChartModeWindow(candles: FxtmCandleRow[], window: TradingViewChartWindow): FxtmCandleRow[] {
  const rows = (candles || [])
    .filter((c) => !!c?.time && Number.isFinite(candleTimeMs(c)))
    .sort((a, b) => candleTimeMs(a) - candleTimeMs(b));
  if (!rows.length) return rows;

  if (window.mode === 'replay') {
    const cut = rawTimeMs(window.replayCutTime);
    if (!Number.isFinite(cut)) return rows;
    return rows.filter((c) => candleTimeMs(c) <= cut);
  }

  if (window.mode === 'hierarchy') {
    const start = rawTimeMs(window.hierarchyStart);
    const end = rawTimeMs(window.hierarchyEnd);
    const bounded = rows.filter((c) => {
      const ms = candleTimeMs(c);
      if (Number.isFinite(start) && ms < start) return false;
      if (Number.isFinite(end) && ms > end) return false;
      return true;
    });
    return bounded.length ? bounded : rows.filter((c) => !Number.isFinite(end) || candleTimeMs(c) <= end);
  }

  const count = latestWindowSizeForTimeframe(window.timeframe);
  return rows.slice(Math.max(0, rows.length - count));
}
