function structuralRangePaddingCandles(layer: StructureLayer | null, chartTf?: string): { before: number; after: number } {
  const base = (() => {
    if (layer === 'MACRO' || layer === 'WEEKLY') return 20;
    if (layer === 'DAILY') return 15;
    if (layer === 'INTRADAY') return 10;
    if (layer === 'MICRO') return 8;
    return 15;
  })();
  const tf = String(chartTf || 'D1').toUpperCase();
  if (tf === 'H1' || tf === 'H4') return { before: Math.max(base * 3, 36), after: Math.max(base, 12) };
  if (tf === 'M15' || tf === 'M5') return { before: Math.max(base * 2, 28), after: Math.max(base, 10) };
  return { before: Math.max(base * 2, 24), after: Math.max(base, 10) };
}
function structuralRangeFitPadRatio(layer: StructureLayer | null): number {
  if (layer === 'MACRO' || layer === 'WEEKLY') return 0.16;
  if (layer === 'DAILY') return 0.12;
  return 0.1;
}
function structuralRangeFitDomain(range: any, candles: Candle[], chartTf?: string): StructuralFitWindow | null {
  const hi = Number(range?.range_high_price ?? range?.range_high);
  const lo = Number(range?.range_low_price ?? range?.range_low);
  if (!Number.isFinite(hi) || !Number.isFinite(lo) || hi <= lo) return null;
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer);
  const status = String(range?.status || '').toUpperCase();
  const broken = status.includes('BROKEN');

  const timeCandidates = [
    range?.range_start_time,
    range?.active_from_time,
    range?.range_high_time,
    range?.range_low_time,
  ].map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  let startMs = parseStructuralTimeMs(range?.range_start_time || range?.active_from_time || range?.range_high_time);
  let endMs = parseStructuralTimeMs(range?.range_end_time || range?.range_low_time);
  if (broken) {
    const inactiveMs = parseStructuralTimeMs(range?.inactive_from_time);
    if (inactiveMs !== null) endMs = endMs === null ? inactiveMs : Math.max(endMs, inactiveMs);
  }
  if (startMs === null && timeCandidates.length) startMs = Math.min(...timeCandidates);
  if (endMs === null && timeCandidates.length) endMs = Math.max(...timeCandidates);
  if (startMs === null) return null;
  if (endMs === null || endMs < startMs) {
    endMs = startMs + (layer === 'INTRADAY' || layer === 'MICRO' ? 6 * 3600 * 1000 : 7 * 24 * 3600 * 1000);
  }

  const pad = structuralRangePaddingCandles(layer, chartTf);
  let priceLow = lo;
  let priceHigh = hi;
  let startTime = new Date(startMs).toISOString();
  let endTime = new Date(endMs).toISOString();

  if (candles.length) {
    const startIdx = candleIndexAtOrBefore(candles, startTime);
    const endIdx = candleIndexAtOrAfter(candles, endTime);
    const padStart = Math.max(0, startIdx - pad.before);
    const padEnd = Math.min(candles.length - 1, endIdx + pad.after);
    startTime = candles[padStart]?.time || startTime;
    endTime = candles[padEnd]?.time || endTime;
    for (let i = padStart; i <= padEnd; i++) {
      const c = candles[i];
      if (!c) continue;
      priceLow = Math.min(priceLow, c.low);
      priceHigh = Math.max(priceHigh, c.high);
    }
  } else {
    const spanMs = Math.max(endMs - startMs, 1);
    const leftPadMs = Math.max(spanMs * 0.42, 3600 * 1000);
    const rightPadMs = Math.max(spanMs * 0.14, 3600 * 1000);
    startTime = new Date(startMs - leftPadMs).toISOString();
    endTime = new Date(endMs + rightPadMs).toISOString();
  }

  return {
    start: startTime,
    end: endTime,
    low: priceLow,
    high: priceHigh,
    padRatio: structuralRangeFitPadRatio(layer),
  };
}
function structuralContextTargetTime(range: any): string | null {
  if (!range) return null;
  return String(
    range.range_start_time
    || range.active_from_time
    || range.range_high_time
    || range.range_low_time
    || '',
  ) || null;
}
function clampFitTimesToCandles(startRaw: string, endRaw: string, candles: Candle[]): { start: string; end: string } {
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
function buildCandleWindowFit(candles: Candle[], centerTime: string, padBars = 40): StructuralFitWindow | null {
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
function candleDataExtent(candles: Candle[]): { startMs: number; endMs: number; start: string; end: string } | null {
  if (!candles.length) return null;
  const startMs = new Date(String(candles[0].time)).getTime();
  const endMs = new Date(String(candles[candles.length - 1].time)).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return { startMs, endMs, start: candles[0].time, end: candles[candles.length - 1].time };
}
function isPlausibleMarketTimeMs(ms: number | null, candles?: Candle[]): boolean {
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
function parseStructuralTimeMs(value: any): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  const ms = candleTimeMs(raw);
  return Number.isFinite(ms) ? ms : null;
}
function candleIndexAtOrBefore(candles:Candle[], time?:string|null): number {
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
function candleIndexAtOrAfter(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  for (let i = 0; i < candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(t) && t >= cut) return i;
  }
  return candles.length - 1;
}
