/** Per-case/symbol/timeframe chart viewport memory + routine TF switch anchors. */

import { fxtmTimeToTradingViewTime } from './tradingView/candleAdapter';
import type { TradingViewFitRequest } from './tradingView/types';

export type ChartTimeframeMemory = {
  start: string;
  end: string;
  priceLow?: number;
  priceHigh?: number;
  visibleBars?: number;
  tvFrom?: string | number;
  tvTo?: string | number;
};

export type VisibleDomainSnapshot = {
  start: string;
  end: string;
  priceLow?: number;
  priceHigh?: number;
  visibleBars?: number;
};

export type MemoryFitWindow = {
  start: string;
  end: string;
  low: number;
  high: number;
  padRatio: number;
};

export type RoutineTfCameraPlan = {
  intent: 'PRESERVE_OR_NEAREST_TIME' | 'RESTORE_LOCKED' | 'LATEST';
  reason: string;
  targetTime: string | null;
  fitWindow: MemoryFitWindow | null;
  priceDomain: { low: number; high: number } | null;
  anchorSource?: RoutineAnchorSource;
};

export type RoutineAnchorSource =
  | 'sourceViewport'
  | 'savedH1SameTf'
  | 'savedDest'
  | 'locked'
  | 'replay'
  | 'selectedCandle'
  | 'globalReplay'
  | 'nearest'
  | 'latest';

export function chartMemoryKey(caseId: string, symbol: string, timeframe: string): string {
  return `${String(caseId || 'global')}|${String(symbol || '').toUpperCase()}|${String(timeframe || '').toUpperCase()}`;
}

export function legacyChartMemoryKey(caseId: string, timeframe: string): string {
  return `${String(caseId || 'global')}_${String(timeframe || '').toUpperCase()}`;
}

export function globalReplayCursorKey(caseId: string, symbol: string): string {
  return `${String(caseId || 'global')}|${String(symbol || '').toUpperCase()}`;
}

export function parseChartTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const mt5 = raw.match(/^(\d{4})\.(\d{2})\.(\d{2})(?:\s+(\d{2}):(\d{2}))?/);
  if (mt5) {
    const ms = Date.UTC(
      Number(mt5[1]),
      Number(mt5[2]) - 1,
      Number(mt5[3]),
      Number(mt5[4] || 0),
      Number(mt5[5] || 0),
    );
    return Number.isFinite(ms) ? ms : null;
  }
  const isoish = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const ms = Date.parse(isoish.endsWith('Z') ? isoish : `${isoish.replace(/\.\d{3}$/, '')}Z`);
  return Number.isFinite(ms) ? ms : null;
}

export function viewportCenterMs(start: string, end: string): number | null {
  const a = parseChartTimeMs(start);
  const b = parseChartTimeMs(end);
  if (a === null || b === null) return null;
  return Math.round((a + b) / 2);
}

export function snapshotMemoryFromVisibleDomain(dom: VisibleDomainSnapshot): ChartTimeframeMemory {
  return {
    start: dom.start,
    end: dom.end,
    priceLow: dom.priceLow,
    priceHigh: dom.priceHigh,
    visibleBars: dom.visibleBars,
  };
}

export function memoryFitWindowFromChartMemory(
  memory: ChartTimeframeMemory | null | undefined,
  priceDomain?: { low: number; high: number } | null,
): MemoryFitWindow | null {
  if (!memory?.start || !memory?.end) return null;
  if (!Number.isFinite(parseChartTimeMs(memory.start)) || !Number.isFinite(parseChartTimeMs(memory.end))) {
    return null;
  }
  const price = priceDomain
    && Number.isFinite(priceDomain.low)
    && Number.isFinite(priceDomain.high)
    && priceDomain.high > priceDomain.low
    ? priceDomain
    : null;
  return {
    start: memory.start,
    end: memory.end,
    low: price?.low ?? 0,
    high: price?.high ?? 0,
    padRatio: 0,
  };
}

export function readChartMemoryFromStore(
  store: Record<string, { start: string; end: string } | ChartTimeframeMemory>,
  caseId: string,
  symbol: string,
  timeframe: string,
  priceStore?: Record<string, { low: number; high: number }>,
): ChartTimeframeMemory | null {
  const key = chartMemoryKey(caseId, symbol, timeframe);
  const legacy = legacyChartMemoryKey(caseId, timeframe);
  const row = store[key] || store[legacy];
  if (!row?.start || !row?.end) return null;
  const price = priceStore?.[key] || priceStore?.[legacy];
  return sanitizeChartMemoryOnRead({
    start: row.start,
    end: row.end,
    priceLow: price?.low ?? (row as ChartTimeframeMemory).priceLow,
    priceHigh: price?.high ?? (row as ChartTimeframeMemory).priceHigh,
    visibleBars: (row as ChartTimeframeMemory).visibleBars,
    tvFrom: (row as ChartTimeframeMemory).tvFrom,
    tvTo: (row as ChartTimeframeMemory).tvTo,
  }, timeframe);
}

export function resolveNearestCandleIndex<T extends { time: string }>(
  candles: T[],
  targetTime: string | null | undefined,
): number {
  if (!candles.length || !targetTime) return -1;
  const targetMs = parseChartTimeMs(targetTime);
  if (targetMs === null) return -1;
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = parseChartTimeMs(candles[i].time);
    if (ms === null) continue;
    const dist = Math.abs(ms - targetMs);
    if (dist < bestDist) {
      best = i;
      bestDist = dist;
    }
  }
  return best;
}

export function resolveNearestCandleTime<T extends { time: string }>(
  candles: T[],
  targetTime: string | null | undefined,
): string | null {
  const idx = resolveNearestCandleIndex(candles, targetTime);
  return idx >= 0 ? String(candles[idx].time) : null;
}

export function resolveNearestCandle<T extends { time: string }>(
  candles: T[],
  targetTime: string | null | undefined,
): T | null {
  const idx = resolveNearestCandleIndex(candles, targetTime);
  return idx >= 0 ? candles[idx] : null;
}

export function routineTfMemoryReason(sourceTf: string, destTf: string): string {
  return `routine-tf-memory:${String(sourceTf).toUpperCase()}->${String(destTf).toUpperCase()}`;
}

/** Minimum visible bars routine TF memory may restore on the destination chart. */
export function minimumRoutineVisibleBarsForTimeframe(tf: string): number {
  const t = String(tf || 'D1').toUpperCase();
  if (t === 'M5') return 160;
  if (t === 'M15') return 120;
  if (t === 'H1') return 80;
  if (t === 'H4') return 60;
  if (t === 'D1') return 80;
  if (t === 'W1') return 40;
  if (t === 'MN1') return 36;
  return 80;
}

export function expandCandleIndexWindow(
  candleCount: number,
  i0: number,
  i1: number,
  minBars: number,
  centerIdx?: number,
): { i0: number; i1: number } {
  if (candleCount <= 0) return { i0: 0, i1: 0 };
  let lo = Math.min(i0, i1);
  let hi = Math.max(i0, i1);
  const span = hi - lo + 1;
  if (span >= minBars) return { i0: lo, i1: hi };
  const center = centerIdx !== undefined && centerIdx >= 0
    ? Math.max(lo, Math.min(hi, centerIdx))
    : Math.floor((lo + hi) / 2);
  const need = minBars - 1;
  lo = Math.max(0, center - Math.floor(need / 2));
  hi = Math.min(candleCount - 1, lo + need);
  if (hi - lo + 1 < minBars) {
    lo = Math.max(0, hi - need);
  }
  return { i0: lo, i1: hi };
}

export function countBarsInCandleWindow<T extends { time: string }>(
  candles: T[],
  startTime: string,
  endTime: string,
): number {
  const i0 = resolveNearestCandleIndex(candles, startTime);
  const i1 = resolveNearestCandleIndex(candles, endTime);
  if (i0 < 0 || i1 < 0) return 0;
  return Math.abs(i1 - i0) + 1;
}

export function shouldPersistChartMemory(dom: VisibleDomainSnapshot, tf: string): boolean {
  if (!dom?.start || !dom?.end) return false;
  const startMs = parseChartTimeMs(dom.start);
  const endMs = parseChartTimeMs(dom.end);
  if (startMs === null || endMs === null || startMs === endMs) return false;
  const minBars = minimumRoutineVisibleBarsForTimeframe(tf);
  const reported = Number(dom.visibleBars || 0);
  if (reported > 0 && reported < minBars) return false;
  return true;
}

export function sanitizeChartMemoryOnRead(
  memory: ChartTimeframeMemory | null | undefined,
  tf: string,
): ChartTimeframeMemory | null {
  if (!memory?.start || !memory?.end) return null;
  const startMs = parseChartTimeMs(memory.start);
  const endMs = parseChartTimeMs(memory.end);
  if (startMs === null || endMs === null || startMs === endMs) return null;
  const minBars = minimumRoutineVisibleBarsForTimeframe(tf);
  const reported = Number(memory.visibleBars || 0);
  if (reported > 0 && reported < minBars) return null;
  if (isH1RoutineDest(tf) && isDegenerateH1MemorySpan(memory)) return null;
  if (String(tf).toUpperCase() === 'H4' && memorySpanMs(memory)! < 3600000 * 4) return null;
  return memory;
}

export function buildRoutineMemoryFitWindow<T extends { time: string; high?: number; low?: number }>(
  candles: T[],
  centerTime: string | null | undefined,
  destTf: string,
): MemoryFitWindow | null {
  if (!candles.length || !centerTime) return null;
  const centerIdx = resolveNearestCandleIndex(candles, centerTime);
  if (centerIdx < 0) return null;
  const minBars = minimumRoutineVisibleBarsForTimeframe(destTf);
  const expanded = expandCandleIndexWindow(candles.length, centerIdx, centerIdx, minBars, centerIdx);
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = expanded.i0; i <= expanded.i1; i += 1) {
    const row = candles[i];
    if (Number.isFinite(row.low) && Number.isFinite(row.high)) {
      lo = Math.min(lo, Number(row.low));
      hi = Math.max(hi, Number(row.high));
    }
  }
  return {
    start: String(candles[expanded.i0].time),
    end: String(candles[expanded.i1].time),
    low: Number.isFinite(lo) ? lo : 0,
    high: Number.isFinite(hi) ? hi : 0,
    padRatio: 0,
  };
}

export function memoryOverlapsCandles<T extends { time: string }>(
  candles: T[],
  memory: { start?: string | null; end?: string | null } | null | undefined,
): boolean {
  if (!candles.length || !memory?.start || !memory?.end) return false;
  const memStart = parseChartTimeMs(memory.start);
  const memEnd = parseChartTimeMs(memory.end);
  const first = parseChartTimeMs(candles[0].time);
  const last = parseChartTimeMs(candles[candles.length - 1].time);
  if (memStart === null || memEnd === null || first === null || last === null) return false;
  const lo = Math.min(memStart, memEnd);
  const hi = Math.max(memStart, memEnd);
  return hi >= first && lo <= last;
}

export function isH1RoutineDest(tf: string): boolean {
  return String(tf || '').toUpperCase() === 'H1';
}

export function isLowerIntradayRoutineDest(tf: string): boolean {
  const t = String(tf || '').toUpperCase();
  return t === 'H4' || t === 'H1' || t === 'M15' || t === 'M5';
}

export function memorySpanMs(
  memory: { start?: string | null; end?: string | null } | null | undefined,
): number | null {
  if (!memory?.start || !memory?.end) return null;
  const startMs = parseChartTimeMs(memory.start);
  const endMs = parseChartTimeMs(memory.end);
  if (startMs === null || endMs === null) return null;
  return Math.abs(endMs - startMs);
}

/** H1 saved spans shorter than ~2 hours are usually stale cross-TF writeback — rebuild from center. */
export function isDegenerateH1MemorySpan(
  memory: { start?: string | null; end?: string | null } | null | undefined,
): boolean {
  const spanMs = memorySpanMs(memory);
  if (spanMs === null) return true;
  return spanMs < 3600000 * 2;
}

export function isPoisonedH1Memory(
  memory: ChartTimeframeMemory | null | undefined,
): boolean {
  if (!memory?.start || !memory?.end) return true;
  if (sanitizeChartMemoryOnRead(memory, 'H1') === null) return true;
  if (isDegenerateH1MemorySpan(memory)) return true;
  const reported = Number(memory.visibleBars || 0);
  if (reported > 0 && reported < minimumRoutineVisibleBarsForTimeframe('H1')) return true;
  return false;
}

export function parseRoutineTfMemoryReason(reason?: string | null): { sourceTf: string; destTf: string } | null {
  const match = String(reason || '').match(/routine-tf-memory:([A-Z0-9]+)->([A-Z0-9]+)/i);
  if (!match) return null;
  return { sourceTf: match[1].toUpperCase(), destTf: match[2].toUpperCase() };
}

export function isCrossTfH1Entry(sourceTf: string, destTf: string): boolean {
  const src = String(sourceTf || '').toUpperCase();
  const dst = String(destTf || '').toUpperCase();
  return dst === 'H1' && src !== 'H1';
}

export function shouldPersistH1ChartMemory<T extends { time: string }>(
  dom: VisibleDomainSnapshot,
  candles: T[],
): boolean {
  if (!shouldPersistChartMemory(dom, 'H1')) return false;
  if (isDegenerateH1MemorySpan(dom)) return false;
  if (!memoryOverlapsCandles(candles, dom)) return false;
  return true;
}

export function purgePoisonedH1MemoryKeys(
  store: Record<string, { start: string; end: string } | ChartTimeframeMemory>,
  caseId: string,
  symbol: string,
): { key: string; legacy: string } | null {
  const key = chartMemoryKey(caseId, symbol, 'H1');
  const legacy = legacyChartMemoryKey(caseId, 'H1');
  const row = store[key] || store[legacy];
  if (!row) return null;
  const sanitized = sanitizeChartMemoryOnRead({
    start: row.start,
    end: row.end,
    visibleBars: (row as ChartTimeframeMemory).visibleBars,
  }, 'H1');
  if (sanitized && !isPoisonedH1Memory(sanitized)) return null;
  return { key, legacy };
}

export function isMemoryAnchorPlausibleForCandles<T extends { time: string }>(
  candles: T[],
  targetTime: string | null | undefined,
  padMs = 86400000 * 14,
): boolean {
  if (!candles.length || !targetTime) return false;
  const targetMs = parseChartTimeMs(targetTime);
  const first = parseChartTimeMs(candles[0].time);
  const last = parseChartTimeMs(candles[candles.length - 1].time);
  if (targetMs === null || first === null || last === null) return false;
  return targetMs >= first - padMs && targetMs <= last + padMs;
}

/** After destination candles load — drop invalid memory anchors; never leave camera without a valid target. */
export function sanitizeRoutineMemoryCameraAfterLoad<T extends { time: string; high?: number; low?: number }>(
  plan: RoutineTfCameraPlan,
  candles: T[],
  destTf: string,
): RoutineTfCameraPlan {
  const minBars = minimumRoutineVisibleBarsForTimeframe(destTf);
  if (!candles.length) {
    return {
      ...plan,
      intent: 'LATEST',
      targetTime: null,
      fitWindow: null,
      priceDomain: null,
    };
  }
  const latestTime = String(candles[candles.length - 1].time);
  let intent = plan.intent;
  let targetTime = plan.targetTime;
  let fitWindow = plan.fitWindow;
  let priceDomain = plan.priceDomain;

  if (targetTime) {
    if (isMemoryAnchorPlausibleForCandles(candles, targetTime)) {
      targetTime = resolveNearestCandleTime(candles, targetTime);
    } else {
      targetTime = null;
    }
  }

  const centerIdx = targetTime ? resolveNearestCandleIndex(candles, targetTime) : -1;

  if (fitWindow && !memoryOverlapsCandles(candles, fitWindow)) {
    fitWindow = null;
  }
  if (isH1RoutineDest(destTf) && fitWindow && isDegenerateH1MemorySpan(fitWindow)) {
    fitWindow = null;
  }
  if (String(destTf).toUpperCase() === 'H4' && fitWindow && memorySpanMs(fitWindow) !== null && memorySpanMs(fitWindow)! < 3600000 * 4) {
    fitWindow = null;
  }
  if (fitWindow) {
    const startIdx = resolveNearestCandleIndex(candles, fitWindow.start);
    const endIdx = resolveNearestCandleIndex(candles, fitWindow.end);
    if (startIdx < 0 || endIdx < 0) {
      fitWindow = null;
    } else {
      const expanded = expandCandleIndexWindow(
        candles.length,
        startIdx,
        endIdx,
        minBars,
        centerIdx >= 0 ? centerIdx : undefined,
      );
      const windowCenterIdx = centerIdx >= 0
        ? centerIdx
        : Math.floor((expanded.i0 + expanded.i1) / 2);
      fitWindow = buildRoutineMemoryFitWindow(
        candles,
        String(candles[windowCenterIdx].time),
        destTf,
      );
    }
  }

  if (!fitWindow && targetTime) {
    fitWindow = buildRoutineMemoryFitWindow(candles, targetTime, destTf);
  }

  if (fitWindow && countBarsInCandleWindow(candles, fitWindow.start, fitWindow.end) < minBars) {
    fitWindow = buildRoutineMemoryFitWindow(candles, targetTime || fitWindow.start, destTf);
  }

  const parsedReason = parseRoutineTfMemoryReason(plan.reason);
  const crossTfH1 = parsedReason ? isCrossTfH1Entry(parsedReason.sourceTf, parsedReason.destTf) : false;
  if (isH1RoutineDest(destTf) && crossTfH1 && targetTime && !fitWindow) {
    fitWindow = buildRoutineMemoryFitWindow(candles, targetTime, destTf);
  }
  if (isH1RoutineDest(destTf) && crossTfH1 && fitWindow && countBarsInCandleWindow(candles, fitWindow.start, fitWindow.end) < minBars) {
    fitWindow = buildRoutineMemoryFitWindow(candles, targetTime || fitWindow.start, destTf);
  }

  if (fitWindow) {
    intent = intent === 'RESTORE_LOCKED' ? 'RESTORE_LOCKED' : 'PRESERVE_OR_NEAREST_TIME';
  } else if (targetTime) {
    intent = intent === 'RESTORE_LOCKED' ? 'RESTORE_LOCKED' : 'PRESERVE_OR_NEAREST_TIME';
  } else {
    intent = 'LATEST';
    targetTime = latestTime;
    fitWindow = buildRoutineMemoryFitWindow(candles, latestTime, destTf);
    priceDomain = null;
  }

  return {
    reason: plan.reason,
    intent,
    targetTime,
    fitWindow,
    priceDomain,
    anchorSource: plan.anchorSource,
  };
}

/** Routine chip switch — memory anchors only; never structural range fit. */
export function resolveRoutineTfSwitchCameraPlan(args: {
  cameraMode: string;
  sourceTf: string;
  destTf: string;
  savedDestMemory: ChartTimeframeMemory | null;
  sourceViewport: ChartTimeframeMemory | null;
  globalReplayTime: string | null;
  selectedCandleTime: string | null;
  savedDestPrice?: { low: number; high: number } | null;
  replayMode?: boolean;
  explicitReplayMode?: boolean;
}): RoutineTfCameraPlan {
  const reason = routineTfMemoryReason(args.sourceTf, args.destTf);
  const explicitReplay = !!(args.explicitReplayMode ?? args.replayMode);
  const priceDomain = args.savedDestPrice
    && Number.isFinite(args.savedDestPrice.low)
    && Number.isFinite(args.savedDestPrice.high)
    && args.savedDestPrice.high > args.savedDestPrice.low
    ? args.savedDestPrice
    : (args.savedDestMemory?.priceLow != null && args.savedDestMemory?.priceHigh != null
      && args.savedDestMemory.priceHigh > args.savedDestMemory.priceLow
      ? { low: args.savedDestMemory.priceLow, high: args.savedDestMemory.priceHigh }
      : null);

  if (args.cameraMode === 'LOCKED') {
    const fitWindow = memoryFitWindowFromChartMemory(args.savedDestMemory, priceDomain);
    return {
      intent: 'RESTORE_LOCKED',
      reason,
      targetTime: args.savedDestMemory?.start || (explicitReplay ? args.globalReplayTime : null) || args.selectedCandleTime || null,
      fitWindow,
      priceDomain,
      anchorSource: 'locked',
    };
  }

  if (explicitReplay && args.globalReplayTime) {
    return {
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason,
      targetTime: args.globalReplayTime,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'replay',
    };
  }

  const sameTf = String(args.sourceTf).toUpperCase() === String(args.destTf).toUpperCase();
  const savedFit = memoryFitWindowFromChartMemory(args.savedDestMemory, priceDomain);
  const sourceCenter = args.sourceViewport?.start && args.sourceViewport?.end
    ? viewportCenterIso(args.sourceViewport.start, args.sourceViewport.end)
    : null;

  if (isH1RoutineDest(args.destTf) && sameTf && args.savedDestMemory?.start && args.savedDestMemory?.end) {
    const center = viewportCenterIso(args.savedDestMemory.start, args.savedDestMemory.end)
      || args.savedDestMemory.start
      || null;
    if (center && savedFit && !isDegenerateH1MemorySpan(savedFit)) {
      return {
        intent: 'PRESERVE_OR_NEAREST_TIME',
        reason,
        targetTime: center,
        fitWindow: savedFit,
        priceDomain,
        anchorSource: 'savedH1SameTf',
      };
    }
  }

  if (isCrossTfH1Entry(args.sourceTf, args.destTf)) {
    if (sourceCenter) {
      return {
        intent: 'PRESERVE_OR_NEAREST_TIME',
        reason,
        targetTime: sourceCenter,
        fitWindow: null,
        priceDomain: null,
        anchorSource: 'sourceViewport',
      };
    }
    return {
      intent: 'LATEST',
      reason,
      targetTime: null,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'latest',
    };
  }

  if (isLowerIntradayRoutineDest(args.destTf) && !sameTf) {
    if (sourceCenter) {
      return {
        intent: 'PRESERVE_OR_NEAREST_TIME',
        reason,
        targetTime: sourceCenter,
        fitWindow: null,
        priceDomain: null,
        anchorSource: 'sourceViewport',
      };
    }
    if (savedFit && !(isH1RoutineDest(args.destTf) && isDegenerateH1MemorySpan(savedFit))) {
      const center = viewportCenterIso(args.savedDestMemory!.start, args.savedDestMemory!.end)
        || args.savedDestMemory?.start
        || null;
      return {
        intent: 'PRESERVE_OR_NEAREST_TIME',
        reason,
        targetTime: center,
        fitWindow: null,
        priceDomain,
        anchorSource: 'savedDest',
      };
    }
  }

  if (args.selectedCandleTime && !isLowerIntradayRoutineDest(args.destTf)) {
    return {
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason,
      targetTime: args.selectedCandleTime,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'selectedCandle',
    };
  }

  if (savedFit) {
    const center = viewportCenterIso(args.savedDestMemory!.start, args.savedDestMemory!.end)
      || args.savedDestMemory?.start
      || null;
    return {
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason,
      targetTime: center,
      fitWindow: sameTf ? savedFit : null,
      priceDomain,
      anchorSource: 'savedDest',
    };
  }

  if (sourceCenter) {
    return {
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason,
      targetTime: sourceCenter,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'sourceViewport',
    };
  }

  if (!explicitReplay && args.globalReplayTime && !isLowerIntradayRoutineDest(args.destTf)) {
    return {
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason,
      targetTime: args.globalReplayTime,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'globalReplay',
    };
  }

  return {
    intent: 'LATEST',
    reason,
    targetTime: null,
    fitWindow: null,
    priceDomain: null,
    anchorSource: 'latest',
  };
}

function viewportCenterIso(start: string, end: string): string | null {
  const center = viewportCenterMs(start, end);
  return center === null ? null : new Date(center).toISOString();
}

export function buildTradingViewMemoryFitRequest(args: {
  token: number;
  timeframe: string;
  fitWindow?: { start?: string; end?: string } | null;
  targetTime?: string | null;
  requireFitRange?: boolean;
}): TradingViewFitRequest | null {
  const token = Number(args.token || 0);
  if (!Number.isFinite(token) || token <= 0) return null;
  const from = fxtmTimeToTradingViewTime(args.fitWindow?.start, args.timeframe);
  const to = fxtmTimeToTradingViewTime(args.fitWindow?.end, args.timeframe);
  const target = fxtmTimeToTradingViewTime(args.targetTime, args.timeframe);
  const fromMs = parseChartTimeMs(args.fitWindow?.start);
  const toMs = parseChartTimeMs(args.fitWindow?.end);
  const tf = String(args.timeframe || '').toUpperCase();
  const minSpanMs = tf === 'H1' ? 3600000 * 2 : 0;
  const spanOk = fromMs !== null && toMs !== null && Math.abs(toMs - fromMs) >= minSpanMs;
  if (from && to && spanOk && fromMs !== toMs) {
    return { token, from, to, target: target || undefined };
  }
  if (args.requireFitRange) return null;
  if (target) return { token, target };
  return null;
}

export function mergeTvVisibleRangeIntoMemory(
  memory: ChartTimeframeMemory,
  tvRange: { from: string | number; to: string | number } | null | undefined,
): ChartTimeframeMemory {
  if (!tvRange) return memory;
  return {
    ...memory,
    tvFrom: tvRange.from,
    tvTo: tvRange.to,
  };
}
