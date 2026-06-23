import type { BusinessDay, Time, UTCTimestamp } from 'lightweight-charts';
import type { FxtmCandleRow, TradingViewAdapterResult, TradingViewCandle } from './types';

const DAILY_TIMEFRAMES = new Set(['W1', 'D1']);

function parseFxtmTime(raw: string): { timestampSeconds: number; businessDay: BusinessDay; key: string } | null {
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

function timeForTradingView(parsed: NonNullable<ReturnType<typeof parseFxtmTime>>, timeframe: string): Time {
  return DAILY_TIMEFRAMES.has(String(timeframe || '').toUpperCase())
    ? parsed.businessDay
    : parsed.timestampSeconds as UTCTimestamp;
}

function timeSortKey(time: Time): number {
  if (typeof time === 'number') return time;
  if (typeof time === 'string') return Date.parse(`${time}T00:00:00Z`) / 1000;
  return Math.floor(Date.UTC(time.year, time.month - 1, time.day) / 1000);
}

function timeDedupeKey(time: Time): string {
  if (typeof time === 'number') return String(time);
  if (typeof time === 'string') return time;
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
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
