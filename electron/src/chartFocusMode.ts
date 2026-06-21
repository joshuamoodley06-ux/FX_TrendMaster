/** Chart Focus Mode — candle-first Y-scale and layered overlay priority. */

import { parseTimeMs } from './viewportController';

export type FocusOverlayTier = 'active' | 'parent' | 'ancestor' | 'hidden';

export type FocusVisualStyle = {
  opacity: number;
  width: number;
  dash: string;
  showLabel: boolean;
};

export type CandleLike = {
  time: string;
  high: number;
  low: number;
};

export type FocusFitWindow = {
  start: string;
  end: string;
  low: number;
  high: number;
  padRatio: number;
};

const LAYER_RANK: Record<string, number> = {
  MACRO: 0,
  WEEKLY: 1,
  DAILY: 2,
  INTRADAY: 3,
  MICRO: 4,
};

export const FOCUS_Y_PAD_RATIO = 0.1;

export function defaultFocusModeForGuided(guidedActive: boolean): boolean {
  return guidedActive;
}

export function shouldUseCandleOnlyYScale(focusMode: boolean): boolean {
  return focusMode;
}

export function candleOnlyYExtents(
  candles: CandleLike[],
  padRatio = FOCUS_Y_PAD_RATIO,
): { low: number; high: number; padRatio: number } | null {
  if (!candles.length) return null;
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of candles) {
    if (!Number.isFinite(c.high) || !Number.isFinite(c.low)) continue;
    lo = Math.min(lo, c.low);
    hi = Math.max(hi, c.high);
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return null;
  return { low: lo, high: hi, padRatio };
}

/** Focus Mode Y-domain: candles ∪ parent RH/RL so parent lines stay on-chart. */
export function focusYExtentsWithParent(
  candles: CandleLike[],
  parentHi?: number | null,
  parentLo?: number | null,
  padRatio = FOCUS_Y_PAD_RATIO,
): { low: number; high: number; padRatio: number } | null {
  const base = candleOnlyYExtents(candles, padRatio);
  const pHi = parentHi != null && Number.isFinite(parentHi) ? Number(parentHi) : null;
  const pLo = parentLo != null && Number.isFinite(parentLo) ? Number(parentLo) : null;
  if (!base && pHi === null && pLo === null) return null;
  let lo = base?.low ?? pLo ?? 0;
  let hi = base?.high ?? pHi ?? 1;
  if (pLo !== null) lo = Math.min(lo, pLo);
  if (pHi !== null) hi = Math.max(hi, pHi);
  if (hi <= lo) return null;
  return { low: lo, high: hi, padRatio };
}

export const CONTEXT_REPLAY_LOOKBACK_BARS = 100;

/** Replay context fit: [cursor − lookback, cursor], union parent span on X; future stays hidden. */
export function buildContextReplayFitWindow(args: {
  candles: CandleLike[];
  cursorTime: string;
  lookbackBars?: number;
  parentStart?: string | null;
  parentEnd?: string | null;
  parentHi?: number | null;
  parentLo?: number | null;
}): FocusFitWindow | null {
  const { candles, cursorTime } = args;
  if (!candles.length || !cursorTime) return null;
  const lookback = Math.max(8, args.lookbackBars ?? CONTEXT_REPLAY_LOOKBACK_BARS);
  const cursorIdx = candleIndexAtOrBefore(candles, cursorTime);
  const i0 = Math.max(0, cursorIdx - lookback + 1);
  const i1 = cursorIdx;
  let startMs = parseTimeMs(candles[i0].time) ?? 0;
  const cursorEndMs = parseTimeMs(cursorTime) ?? parseTimeMs(candles[i1].time) ?? startMs;
  let endMs = Math.min(parseTimeMs(candles[i1].time) ?? cursorEndMs, cursorEndMs);
  const pStart = args.parentStart ? parseTimeMs(args.parentStart) : null;
  if (pStart !== null) startMs = Math.min(startMs, pStart);
  const slice = candles.slice(
    candleIndexAtOrBefore(candles, new Date(startMs).toISOString()),
    i1 + 1,
  );
  const y = candleOnlyYExtents(slice.length ? slice : candles.slice(i0, i1 + 1));
  let lo = y?.low ?? 0;
  let hi = y?.high ?? 1;
  const pHi = args.parentHi != null && Number.isFinite(args.parentHi) ? Number(args.parentHi) : null;
  const pLo = args.parentLo != null && Number.isFinite(args.parentLo) ? Number(args.parentLo) : null;
  if (pLo !== null) lo = Math.min(lo, pLo);
  if (pHi !== null) hi = Math.max(hi, pHi);
  return {
    start: new Date(startMs).toISOString(),
    end: new Date(endMs).toISOString(),
    low: lo,
    high: hi,
    padRatio: FOCUS_Y_PAD_RATIO,
  };
}

export function layerRank(layer: string): number {
  return LAYER_RANK[String(layer || '').toUpperCase()] ?? 99;
}

export function resolveFocusTier(
  activeMappingLayer: string,
  overlayLayer: string,
  ctx: {
    isActive?: boolean;
    isDraft?: boolean;
    isImmediateParent?: boolean;
    isAncestor?: boolean;
    overlayRangeId?: string;
    parentRangeId?: string | null;
    ancestorIds?: string[];
  },
): FocusOverlayTier {
  if (ctx.isActive || ctx.isDraft) return 'active';
  if (ctx.isImmediateParent || (ctx.parentRangeId && ctx.overlayRangeId === ctx.parentRangeId)) {
    return 'parent';
  }
  if (ctx.isAncestor || (ctx.ancestorIds || []).includes(String(ctx.overlayRangeId || ''))) {
    return 'ancestor';
  }
  const activeRank = layerRank(activeMappingLayer);
  const overlayRank = layerRank(overlayLayer);
  if (overlayRank === activeRank - 1) return 'parent';
  if (overlayRank < activeRank) return 'ancestor';
  return 'hidden';
}

export function focusVisualStyle(
  tier: FocusOverlayTier,
  opts?: { isDraft?: boolean; isParentEndMarker?: boolean },
): FocusVisualStyle {
  if (opts?.isParentEndMarker) {
    return { opacity: 0.35, width: 1.1, dash: '4 4', showLabel: false };
  }
  if (opts?.isDraft || tier === 'active') {
    return { opacity: 1.0, width: 3.6, dash: '', showLabel: true };
  }
  if (tier === 'parent' || tier === 'ancestor') {
    return { opacity: 0.3, width: 2.2, dash: '6 4', showLabel: true };
  }
  return { opacity: 0, width: 0, dash: '', showLabel: false };
}

export function filterFocusModeOverlays<T extends { rangeId: string; structureLayer: string; focusTier?: FocusOverlayTier }>(
  overlays: T[],
  ctx: {
    focusMode: boolean;
    showAllRanges: boolean;
    activeMappingLayer: string;
  },
): T[] {
  if (!ctx.focusMode) return overlays;
  return overlays
    .map((row) => ({
      ...row,
      focusTier: row.focusTier || resolveFocusTier(ctx.activeMappingLayer, row.structureLayer, {
        overlayRangeId: row.rangeId,
      }),
    }))
    .filter((row) => {
      if (ctx.showAllRanges) return row.focusTier !== 'hidden';
      if (row.focusTier === 'hidden') return false;
      return true;
    });
}

export function candleIndexAtOrBefore(candles: CandleLike[], time: string): number {
  const target = parseTimeMs(time);
  if (target === null || !candles.length) return 0;
  let best = 0;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = parseTimeMs(candles[i].time);
    if (ms !== null && ms <= target) best = i;
    else break;
  }
  return best;
}

export function candleIndexAtOrAfter(candles: CandleLike[], time: string): number {
  const target = parseTimeMs(time);
  if (target === null || !candles.length) return candles.length - 1;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = parseTimeMs(candles[i].time);
    if (ms !== null && ms >= target) return i;
  }
  return candles.length - 1;
}

export function buildCandleSpanFit(
  candles: CandleLike[],
  startTime: string,
  endTime: string,
  padBars = 8,
  padRatio = FOCUS_Y_PAD_RATIO,
): FocusFitWindow | null {
  if (!candles.length || !startTime) return null;
  const startIdx = candleIndexAtOrBefore(candles, startTime);
  const endIdx = endTime ? candleIndexAtOrAfter(candles, endTime) : startIdx;
  const i0 = Math.max(0, Math.min(startIdx, endIdx) - padBars);
  const i1 = Math.min(candles.length - 1, Math.max(startIdx, endIdx) + padBars);
  const y = candleOnlyYExtents(candles.slice(i0, i1 + 1), padRatio);
  if (!y) return null;
  return {
    start: candles[i0].time,
    end: candles[i1].time,
    low: y.low,
    high: y.high,
    padRatio: y.padRatio,
  };
}

export function fitCursorPadBars(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M15' || tf === 'M5') return 120;
  if (tf === 'H1' || tf === 'H4') return 72;
  if (tf === 'D1') return 30;
  return 40;
}

/** Minimum visible candle count for Fit Active per timeframe. */
export function fitActiveMinBars(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M15' || tf === 'M5') return 160;
  if (tf === 'H1' || tf === 'H4') return 72;
  if (tf === 'D1') return 30;
  return 40;
}

/** Extra padding when active span already exceeds minimum window. */
export function fitActiveSpanPadBars(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M15' || tf === 'M5') return 16;
  if (tf === 'H1' || tf === 'H4') return 12;
  if (tf === 'D1') return 8;
  return 10;
}

/** @deprecated Use fitActiveMinBars — kept for callers expecting pad helper name. */
export function fitActivePadBars(timeframe: string): number {
  return fitActiveMinBars(timeframe);
}

export function defaultBarMsForTimeframe(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M5') return 5 * 60 * 1000;
  if (tf === 'M15') return 15 * 60 * 1000;
  if (tf === 'H1') return 60 * 60 * 1000;
  if (tf === 'H4') return 4 * 60 * 60 * 1000;
  if (tf === 'D1') return 24 * 60 * 60 * 1000;
  if (tf === 'W1') return 7 * 24 * 60 * 60 * 1000;
  return 60 * 60 * 1000;
}

export function fitWindowBarCount(candles: CandleLike[], fit: FocusFitWindow): number {
  if (!candles.length || !fit.start) return 0;
  const i0 = candleIndexAtOrBefore(candles, fit.start);
  const i1 = candleIndexAtOrAfter(candles, fit.end || fit.start);
  return Math.max(1, i1 - i0 + 1);
}

export function fitActiveResearchWindowBounds(
  centerTimeMs: number,
  timeframe: string,
): { startMs: number; endMs: number } {
  const minBars = fitActiveMinBars(timeframe);
  const barMs = defaultBarMsForTimeframe(timeframe);
  const halfSpan = Math.ceil((minBars / 2) * barMs);
  return {
    startMs: centerTimeMs - halfSpan,
    endMs: centerTimeMs + halfSpan,
  };
}

export function mergeResearchWindowForFitActive(
  narrow: { start: string; end: string; dateFrom?: string | null; dateTo?: string | null },
  centerTimeMs: number,
  timeframe: string,
): { start: string; end: string; dateFrom: string; dateTo: string } {
  const bounds = fitActiveResearchWindowBounds(centerTimeMs, timeframe);
  const narrowStart = parseTimeMs(narrow.start) ?? bounds.startMs;
  const narrowEnd = parseTimeMs(narrow.end) ?? bounds.endMs;
  const startMs = Math.min(narrowStart, bounds.startMs);
  const endMs = Math.max(narrowEnd, bounds.endMs);
  const start = new Date(startMs).toISOString();
  const end = new Date(endMs).toISOString();
  return {
    start,
    end,
    dateFrom: (narrow.dateFrom || start.slice(0, 10)),
    dateTo: (narrow.dateTo || end.slice(0, 10)),
  };
}

export function resolveFitActiveIndices(
  candles: CandleLike[],
  startIdx: number,
  endIdx: number,
  minBars: number,
  extraPad: number,
): { i0: number; i1: number } {
  if (!candles.length) return { i0: 0, i1: 0 };
  const lo = Math.max(0, Math.min(startIdx, endIdx));
  const hi = Math.min(candles.length - 1, Math.max(startIdx, endIdx));
  const spanBars = hi - lo + 1;

  if (spanBars >= minBars) {
    return {
      i0: Math.max(0, lo - extraPad),
      i1: Math.min(candles.length - 1, hi + extraPad),
    };
  }

  const center = Math.round((lo + hi) / 2);
  const half = Math.floor(minBars / 2);
  let i0 = center - half;
  let i1 = i0 + minBars - 1;

  if (i0 < 0) {
    const shift = -i0;
    i0 = 0;
    i1 = Math.min(candles.length - 1, i1 + shift);
  }
  if (i1 >= candles.length) {
    const shift = i1 - (candles.length - 1);
    i1 = candles.length - 1;
    i0 = Math.max(0, i0 - shift);
  }

  if (candles.length <= minBars) {
    return { i0: 0, i1: candles.length - 1 };
  }

  const count = i1 - i0 + 1;
  if (count < minBars) {
    i1 = Math.min(candles.length - 1, i0 + minBars - 1);
    if (i1 - i0 + 1 < minBars) {
      i0 = Math.max(0, i1 - minBars + 1);
    }
  }

  return { i0, i1 };
}

function buildFitActiveFromIndices(
  candles: CandleLike[],
  i0: number,
  i1: number,
  padRatio = FOCUS_Y_PAD_RATIO,
): FocusFitWindow | null {
  const lo = Math.max(0, Math.min(i0, i1));
  const hi = Math.min(candles.length - 1, Math.max(i0, i1));
  const y = candleOnlyYExtents(candles.slice(lo, hi + 1), padRatio);
  if (!y) return null;
  return {
    start: candles[lo].time,
    end: candles[hi].time,
    low: y.low,
    high: y.high,
    padRatio: y.padRatio,
  };
}

export function ensureFitWindowMinBars(
  candles: CandleLike[],
  fit: FocusFitWindow,
  timeframe: string,
): FocusFitWindow {
  const minBars = fitActiveMinBars(timeframe);
  const count = fitWindowBarCount(candles, fit);
  if (count >= minBars || !candles.length) return fit;
  const startIdx = candleIndexAtOrBefore(candles, fit.start);
  const endIdx = candleIndexAtOrAfter(candles, fit.end || fit.start);
  const { i0, i1 } = resolveFitActiveIndices(
    candles,
    startIdx,
    endIdx,
    minBars,
    fitActiveSpanPadBars(timeframe),
  );
  const y = candleOnlyYExtents(candles.slice(i0, i1 + 1), fit.padRatio);
  return {
    start: candles[i0].time,
    end: candles[i1].time,
    low: y?.low ?? fit.low,
    high: y?.high ?? fit.high,
    padRatio: y?.padRatio ?? fit.padRatio,
  };
}

export function buildFitActiveWindow(args: {
  candles: CandleLike[];
  timeframe: string;
  cursorTimeMs?: number | null;
  gapEndMs?: number | null;
  childStart?: string | null;
  childEnd?: string | null;
  draftStart?: string | null;
  draftEnd?: string | null;
}): FocusFitWindow | null {
  const candles = args.candles;
  if (!candles.length) return null;

  const minBars = fitActiveMinBars(args.timeframe);
  const extraPad = fitActiveSpanPadBars(args.timeframe);

  if (args.draftStart || args.childStart) {
    const start = args.draftStart || args.childStart || '';
    const end = args.draftEnd || args.childEnd || start;
    const startIdx = candleIndexAtOrBefore(candles, start);
    const endIdx = candleIndexAtOrAfter(candles, end);
    const { i0, i1 } = resolveFitActiveIndices(candles, startIdx, endIdx, minBars, extraPad);
    return buildFitActiveFromIndices(candles, i0, i1);
  }

  if (args.cursorTimeMs != null && Number.isFinite(args.cursorTimeMs)) {
    const start = new Date(args.cursorTimeMs).toISOString();
    const gapEndMs = args.gapEndMs ?? args.cursorTimeMs;
    const end = new Date(gapEndMs).toISOString();
    const startIdx = candleIndexAtOrBefore(candles, start);
    const endIdx = candleIndexAtOrAfter(candles, end);
    const gapBars = Math.abs(endIdx - startIdx) + 1;

    if (gapBars > minBars) {
      const segmentEndIdx = Math.min(candles.length - 1, startIdx + minBars - 1);
      const { i0, i1 } = resolveFitActiveIndices(candles, startIdx, segmentEndIdx, minBars, extraPad);
      return buildFitActiveFromIndices(candles, i0, i1);
    }

    const { i0, i1 } = resolveFitActiveIndices(candles, startIdx, endIdx, minBars, extraPad);
    return buildFitActiveFromIndices(candles, i0, i1);
  }

  return null;
}

export function mergeFocusFitPriceDomain(
  fit: FocusFitWindow | null,
  focusMode: boolean,
): FocusFitWindow | null {
  if (!fit || !focusMode) return fit;
  return { ...fit, padRatio: FOCUS_Y_PAD_RATIO };
}

export function annotateOverlayFocusTiers<T extends {
  rangeId: string;
  structureLayer: string;
  isActive?: boolean;
  isParentContext?: boolean;
}>(
  overlays: T[],
  ctx: {
    activeMappingLayer: string;
    parentRangeId: string | null;
    ancestorIds: string[];
    hasDraft: boolean;
  },
): Array<T & { focusTier: FocusOverlayTier }> {
  return overlays.map((row) => {
    const tier = resolveFocusTier(ctx.activeMappingLayer, row.structureLayer, {
      isActive: !!row.isActive,
      isDraft: ctx.hasDraft && !!row.isActive,
      overlayRangeId: row.rangeId,
      parentRangeId: ctx.parentRangeId,
      ancestorIds: ctx.ancestorIds,
      isImmediateParent: ctx.parentRangeId ? row.rangeId === ctx.parentRangeId : !!row.isParentContext,
      isAncestor: ctx.ancestorIds.includes(row.rangeId),
    });
    return { ...row, focusTier: tier };
  });
}
