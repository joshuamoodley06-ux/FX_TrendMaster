import { Candle } from '../types';
import { StructuralFitWindow } from './cameraTypes';

export function candleDataExtent(candles: Candle[]): { startMs: number; endMs: number; start: string; end: string } | null {
  if (!candles.length) return null;
  const startMs = new Date(String(candles[0].time)).getTime();
  const endMs = new Date(String(candles[candles.length - 1].time)).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return { startMs, endMs, start: candles[0].time, end: candles[candles.length - 1].time };
}

export function isPlausibleMarketTimeMs(ms: number | null, candles?: Candle[]): boolean {
  if (ms === null || !Number.isFinite(ms)) return false;
  const year = new Date(ms).getUTCFullYear();
  if (year < 1990 || year > 2035) return false;
  const ext = candles?.length ? candleDataExtent(candles) : null;
  if (ext) {
    const pad = Math.max((ext.endMs - ext.startMs) * 0.2, 86400000 * 14);
    return ms >= ext.startMs - pad && ms <= ext.endMs + pad;
  }
  return true;
}

export function parseStructuralTimeMs(value: any): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  const ms = new Date(raw.includes('T') ? raw : `${raw}T00:00:00.000Z`).getTime();
  return Number.isFinite(ms) ? ms : null;
}

export function clampFitTimesToCandles(startRaw: string, endRaw: string, candles: Candle[]): { start: string; end: string } {
  const ext = candleDataExtent(candles);
  if (!ext) return { start: startRaw, end: endRaw || startRaw };
  let startMs = parseStructuralTimeMs(startRaw);
  let endMs = parseStructuralTimeMs(endRaw);
  if (!isPlausibleMarketTimeMs(startMs, candles)) startMs = ext.startMs;
  if (!isPlausibleMarketTimeMs(endMs, candles)) endMs = ext.endMs;
  if (startMs === null) startMs = ext.startMs;
  if (endMs === null) endMs = ext.endMs;
  if (endMs < startMs) endMs = startMs;
  startMs = Math.max(ext.startMs, Math.min(ext.endMs, startMs));
  endMs = Math.max(startMs, Math.min(ext.endMs, endMs));
  return { start: new Date(startMs).toISOString(), end: new Date(endMs).toISOString() };
}

export function buildCandleWindowFit(candles: Candle[], centerTime: string, padBars = 40): StructuralFitWindow | null {
  if (!candles.length || !centerTime) return null;
  const centerMs = parseStructuralTimeMs(centerTime);
  if (!isPlausibleMarketTimeMs(centerMs, candles)) return null;
  const idx = candleIndexAtOrBefore(candles, centerTime);
  const pad = Math.max(8, padBars);
  const i0 = Math.max(0, idx - pad);
  const i1 = Math.min(candles.length - 1, idx + pad);
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = i0; i <= i1; i++) {
    lo = Math.min(lo, candles[i].low);
    hi = Math.max(hi, candles[i].high);
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  return { start: candles[i0].time, end: candles[i1].time, low: lo, high: hi, padRatio: 0.1 };
}

export function candleIndexNearest(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let best = 0;
  let dist = Math.abs(new Date(String(candles[0].time)).getTime() - cut);
  for (let i=1; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    const d = Math.abs(t - cut);
    if (Number.isFinite(d) && d < dist) { best = i; dist = d; }
  }
  return best;
}

export function candleIndexAtOrBefore(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let idx = -1;
  for (let i=0; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(t) && t <= cut) idx = i;
    if (Number.isFinite(t) && t > cut) break;
  }
  return Math.max(0, idx >= 0 ? idx : 0);
}
