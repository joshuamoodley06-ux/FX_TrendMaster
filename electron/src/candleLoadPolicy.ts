/** Candle load window + stale-load guards for Map Studio boot/TF/case switches. */

export type CandleLoadWindow = { start: string; end: string; label: string };

export type CandleLoadContext = {
  requestId: number;
  symbol: string;
  caseId: string;
  tf: string;
  activeRangeId: string;
  loadWindowKey: string;
};

export type CandleLoadDiagnostics = {
  at: string;
  rangeId: string;
  parentRangeId: string;
  layer: string;
  requestedTf: string;
  windowStart: string;
  windowEnd: string;
  mode: 'windowed' | 'full';
  liveTail: boolean;
  navigationPath: string;
  returnedCount: number;
  filteredCount: number;
  previousCount: number;
  accepted: boolean;
  cameraIntent: string;
  reason: string;
  replayIndex: number;
  playForwardEnabled: boolean;
  playForwardReason: string;
  detail?: string;
};

export const MIN_TRUSTED_WINDOW_BARS = 3;

export type StructuralLoadPadding = { beforeDays: number; afterDays: number; maxSpanDays: number };

export function isoDay(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(String(value));
  if (!Number.isFinite(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

export function todayIsoDay(): string {
  return new Date().toISOString().slice(0, 10);
}

export function addIsoDays(day: string, deltaDays: number): string {
  const d = new Date(`${day}T00:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}

export function loadWindowKey(loadWindow: CandleLoadWindow | null | undefined): string {
  if (!loadWindow?.start || !loadWindow?.end) return 'full';
  return `${loadWindow.start}|${loadWindow.end}`;
}

/** Timeframe-aware padding for DATA loads (wider than camera fit). */
export function structuralDataLoadPadding(chartTf: string, structureLayer?: string | null): StructuralLoadPadding {
  const tf = String(chartTf || 'D1').toUpperCase();
  const layer = String(structureLayer || '').toUpperCase();
  if (tf === 'M5' || tf === 'M15') {
    return { beforeDays: 12, afterDays: 6, maxSpanDays: 28 };
  }
  if (tf === 'H1') {
    return { beforeDays: 28, afterDays: 12, maxSpanDays: 45 };
  }
  if (tf === 'H4') {
    return { beforeDays: 45, afterDays: 18, maxSpanDays: 75 };
  }
  if (tf === 'D1') {
    return { beforeDays: layer === 'WEEKLY' || layer === 'MACRO' ? 90 : 45, afterDays: 21, maxSpanDays: 180 };
  }
  if (tf === 'W1') {
    return { beforeDays: 180, afterDays: 60, maxSpanDays: 420 };
  }
  if (tf === 'MN1') {
    return { beforeDays: 365, afterDays: 120, maxSpanDays: 730 };
  }
  return { beforeDays: 45, afterDays: 21, maxSpanDays: 120 };
}

/** Forward replay horizon beyond parent visual context end — not a live tail. */
export function structuralReplayLookaheadDays(chartTf: string, structureLayer?: string | null): number {
  const tf = String(chartTf || 'D1').toUpperCase();
  const layer = String(structureLayer || '').toUpperCase();
  if (tf === 'M5' || tf === 'M15') return 10;
  if (tf === 'H1') return 14;
  if (tf === 'H4') return 21;
  if (tf === 'D1') return layer === 'WEEKLY' || layer === 'MACRO' ? 60 : 45;
  if (tf === 'W1') return 90;
  if (tf === 'MN1') return 180;
  return 30;
}

/** Chunk size when replay reaches loaded horizon and needs more bars. */
export function structuralReplayChunkDays(chartTf: string): number {
  const tf = String(chartTf || 'D1').toUpperCase();
  if (tf === 'M5' || tf === 'M15') return 5;
  if (tf === 'H1') return 7;
  if (tf === 'H4') return 10;
  if (tf === 'D1') return 21;
  if (tf === 'W1') return 60;
  return 14;
}

export type StructuralWindowPair = {
  /** Parent/visual context span — overlays, focus, camera fit. */
  visualContext: CandleLoadWindow;
  /** Padded data load window — replay may continue into forward buffer. */
  dataLoad: CandleLoadWindow;
};

export function resolveStructuralContextAndReplayWindows(args: {
  rangeSpan: { start?: string; end?: string };
  chartTf: string;
  structureLayer?: string | null;
  label?: string;
}): StructuralWindowPair | null {
  const startDay = isoDay(args.rangeSpan.start || args.rangeSpan.end);
  const endDay = isoDay(args.rangeSpan.end || args.rangeSpan.start);
  if (!startDay || !endDay) return null;
  const visualContext: CandleLoadWindow = {
    start: startDay,
    end: endDay,
    label: args.label || 'structural context',
  };
  const dataLoad = resolveStructuralDataLoadWindow({
    rangeSpan: { start: startDay, end: endDay },
    chartTf: args.chartTf,
    structureLayer: args.structureLayer,
    label: args.label || 'structural context',
  });
  if (!dataLoad) return null;
  return { visualContext, dataLoad };
}

/** DATA load window — padded around saved range span, never pinned to live tail. */
export function loadWindowEndInclusiveIsoDay(day: string): string {
  return `${day}T23:59:59.999Z`;
}

export function loadWindowStartIsoDay(day: string): string {
  return `${day}T00:00:00.000Z`;
}

export function filterCandlesToLoadWindow<T extends { time: string }>(
  candles: T[],
  loadWindow: CandleLoadWindow,
): T[] {
  if (!candles.length || !loadWindow.start || !loadWindow.end) return candles;
  const startMs = new Date(loadWindowStartIsoDay(loadWindow.start)).getTime();
  const endMs = new Date(loadWindowEndInclusiveIsoDay(loadWindow.end)).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return candles;
  return candles.filter((c) => {
    const ms = new Date(String(c.time)).getTime();
    return Number.isFinite(ms) && ms >= startMs && ms <= endMs;
  });
}

export function maxBarsForStructuralWindow(chartTf: string): number {
  const tf = String(chartTf || 'D1').toUpperCase();
  if (tf === 'M5') return 600;
  if (tf === 'M15') return 500;
  if (tf === 'H1') return 1200;
  if (tf === 'H4') return 600;
  if (tf === 'D1') return 260;
  if (tf === 'W1') return 120;
  return 800;
}

/** Trim oldest bars first — preserve forward replay horizon beyond parent context. */
export function trimStructuralCandlesToMaxBars<T>(candles: T[], maxBars: number): T[] {
  if (!Number.isFinite(maxBars) || maxBars <= 0 || candles.length <= maxBars) return candles;
  return candles.slice(candles.length - maxBars);
}

function candleIndexAtOrBeforePolicy<T extends { time: string }>(candles: T[], timeMs: number): number {
  if (!candles.length || !Number.isFinite(timeMs)) return 0;
  let idx = 0;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(ms) && ms <= timeMs) idx = i;
    if (Number.isFinite(ms) && ms > timeMs) break;
  }
  return idx;
}

/**
 * Trim to maxBars while keeping historic lookback before visual context and replay lookahead after it.
 * Parent visual context is NOT the data universe.
 */
export function trimStructuralCandlesToHorizon<T extends { time: string }>(
  candles: T[],
  maxBars: number,
  visualContext: { start?: string | null; end?: string | null } | null | undefined,
  chartTf: string,
): T[] {
  if (!Number.isFinite(maxBars) || maxBars <= 0 || candles.length <= maxBars) return candles;
  const ctxStartDay = isoDay(visualContext?.start);
  const ctxEndDay = isoDay(visualContext?.end || visualContext?.start);
  if (!ctxStartDay && !ctxEndDay) return trimStructuralCandlesToMaxBars(candles, maxBars);

  const ctxStartMs = ctxStartDay
    ? new Date(loadWindowStartIsoDay(ctxStartDay)).getTime()
    : new Date(String(candles[0].time)).getTime();
  const ctxEndMs = ctxEndDay
    ? new Date(loadWindowEndInclusiveIsoDay(ctxEndDay)).getTime()
    : new Date(String(candles[candles.length - 1].time)).getTime();

  const anchorLo = candleIndexAtOrBeforePolicy(candles, ctxStartMs);
  const anchorHi = candleIndexAtOrBeforePolicy(candles, ctxEndMs);
  const pad = structuralDataLoadPadding(chartTf);
  const replayLookahead = structuralReplayLookaheadDays(chartTf);
  const lookbackBars = Math.max(8, Math.min(Math.floor(maxBars * 0.4), pad.beforeDays));
  const lookaheadBars = Math.max(8, Math.min(Math.floor(maxBars * 0.4), pad.afterDays + replayLookahead));

  let lo = Math.max(0, anchorLo - lookbackBars);
  let hi = Math.min(candles.length - 1, anchorHi + lookaheadBars);
  if (hi - lo + 1 > maxBars) {
    const excess = (hi - lo + 1) - maxBars;
    const trimBefore = Math.min(excess, lo);
    lo += trimBefore;
    const remaining = excess - trimBefore;
    hi = Math.max(lo, hi - remaining);
  }
  if (hi - lo + 1 > maxBars) {
    return trimStructuralCandlesToMaxBars(candles.slice(lo, hi + 1), maxBars);
  }
  return candles.slice(lo, hi + 1);
}

export function mergeCandleSeriesByTime<T extends { time: string }>(left: T[], right: T[]): T[] {
  const byTime = new Map<string, T>();
  for (const row of left) byTime.set(String(row.time), row);
  for (const row of right) byTime.set(String(row.time), row);
  return Array.from(byTime.values()).sort(
    (a, b) => new Date(String(a.time)).getTime() - new Date(String(b.time)).getTime(),
  );
}

export function extendStructuralDataLoadWindow(
  window: CandleLoadWindow,
  extendDays: number,
): CandleLoadWindow | null {
  if (!window?.end || !Number.isFinite(extendDays) || extendDays <= 0) return null;
  return {
    ...window,
    end: addIsoDays(window.end, extendDays),
    label: window.label || 'structural context',
  };
}

export function resolveStructuralDataLoadWindow(args: {
  rangeSpan: { start?: string; end?: string };
  chartTf: string;
  structureLayer?: string | null;
  label?: string;
}): CandleLoadWindow | null {
  const startDay = isoDay(args.rangeSpan.start || args.rangeSpan.end);
  const endDay = isoDay(args.rangeSpan.end || args.rangeSpan.start);
  if (!startDay || !endDay) return null;
  const pad = structuralDataLoadPadding(args.chartTf, args.structureLayer);
  const replayLookahead = structuralReplayLookaheadDays(args.chartTf, args.structureLayer);
  let loadStart = addIsoDays(startDay, -pad.beforeDays);
  let loadEnd = addIsoDays(endDay, pad.afterDays + replayLookahead);
  const spanDays = Math.max(
    1,
    Math.round((new Date(`${loadEnd}T00:00:00.000Z`).getTime() - new Date(`${loadStart}T00:00:00.000Z`).getTime()) / 86400000),
  );
  if (spanDays > pad.maxSpanDays) {
    // Preserve forward replay horizon; trim oldest history first.
    const cappedStart = addIsoDays(loadEnd, -(pad.maxSpanDays - 1));
    const paddedStart = addIsoDays(startDay, -pad.beforeDays);
    loadStart = paddedStart < cappedStart ? cappedStart : paddedStart;
  }
  if (loadEnd < loadStart) loadEnd = loadStart;
  return {
    start: loadStart,
    end: loadEnd,
    label: args.label || 'structural context',
  };
}

/** preferred → structural context → generic case window */
export function resolveStructuralCandleLoadWindow(args: {
  rangeWindow: { start?: string; end?: string };
  preferredWindow?: { start?: string | null; end?: string | null } | null;
  liveTail?: boolean;
  contextFit?: { start?: string | null; end?: string | null; label?: string } | null;
  /** When true, never extend structural context end to today. */
  pinStructuralEnd?: boolean;
}): CandleLoadWindow | null {
  const liveEnd = args.liveTail && !args.pinStructuralEnd ? todayIsoDay() : null;
  const preferredStart = isoDay(args.preferredWindow?.start);
  const preferredEnd = liveEnd || isoDay(args.preferredWindow?.end || args.preferredWindow?.start);
  if (preferredStart && preferredEnd) {
    return { start: preferredStart, end: preferredEnd, label: 'chart viewport' };
  }
  if (args.contextFit?.start && args.contextFit?.end) {
    const start = isoDay(args.contextFit.start);
    const end = (args.liveTail && !args.pinStructuralEnd ? todayIsoDay() : null)
      || isoDay(args.contextFit.end);
    if (start && end) {
      return { start, end, label: args.contextFit.label || 'structural range' };
    }
  }
  const rangeStart = isoDay(args.rangeWindow.start);
  const rangeEnd = liveEnd || isoDay(args.rangeWindow.end || args.rangeWindow.start);
  if (rangeStart && rangeEnd) {
    return { start: rangeStart, end: rangeEnd, label: 'active case window' };
  }
  return null;
}

export function shouldUseWindowedCandleLoad(
  loadWindow: CandleLoadWindow | null,
  opts?: { forceFullHistory?: boolean },
): boolean {
  return !!loadWindow && !opts?.forceFullHistory;
}

export function isCurrentCandleLoadRequest(
  started: CandleLoadContext,
  latest: CandleLoadContext,
  activeTf: string,
): boolean {
  return started.requestId === latest.requestId
    && started.tf === latest.tf
    && started.symbol === latest.symbol
    && started.caseId === latest.caseId
    && started.loadWindowKey === latest.loadWindowKey
    && activeTf === started.tf;
}

export function formatWindowLoadDiagnostic(args: {
  requestedTf: string;
  parsedCount: number;
  windowStart?: string;
  windowEnd?: string;
}): string {
  const win = args.windowStart && args.windowEnd
    ? `${args.windowStart} → ${args.windowEnd}`
    : 'full history';
  return `${args.requestedTf} load returned ${args.parsedCount} candle${args.parsedCount === 1 ? '' : 's'} · window ${win}`;
}

export function shouldClearCandlesOnLoadStart(args: {
  quiet: boolean;
  timeframeSwitch?: boolean;
  targetTf: string;
  loadedChartTf?: string | null;
}): boolean {
  if (args.quiet) return false;
  if (args.timeframeSwitch) return true;
  const loaded = String(args.loadedChartTf || '').toUpperCase();
  const target = String(args.targetTf || '').toUpperCase();
  return !!loaded && loaded !== target;
}

export function shouldDiscardDisplayedCandles(args: {
  activeChartTf: string;
  loadedChartTf?: string | null;
  candleCount: number;
}): boolean {
  const active = String(args.activeChartTf || '').toUpperCase();
  const loaded = String(args.loadedChartTf || '').toUpperCase();
  return args.candleCount > 0 && !!loaded && loaded !== active;
}

/** Timeframe tab switch — never derive load window from camera viewport timestamps. */
export function resolveTimeframeSwitchDataLoadWindow(args: {
  targetTf: string;
  contextRange?: { start?: string; end?: string; structure_layer?: string; layer?: string } | null;
  caseWindow?: { start?: string; end?: string };
}): CandleLoadWindow | null {
  const targetTf = String(args.targetTf || '').toUpperCase();
  if (args.contextRange && (args.contextRange.start || args.contextRange.end)) {
    return resolveStructuralDataLoadWindow({
      rangeSpan: {
        start: args.contextRange.start || args.contextRange.end,
        end: args.contextRange.end || args.contextRange.start,
      },
      chartTf: targetTf,
      structureLayer: args.contextRange.structure_layer || args.contextRange.layer,
      label: 'timeframe-switch context',
    });
  }
  const caseWin = args.caseWindow;
  if (caseWin?.start || caseWin?.end) {
    return resolveStructuralDataLoadWindow({
      rangeSpan: { start: caseWin.start || caseWin.end, end: caseWin.end || caseWin.start },
      chartTf: targetTf,
      label: 'timeframe-switch case window',
    });
  }
  return null;
}

export function shouldApplyParsedCandles(args: {
  parsedCount: number;
  previousCount: number;
  hadLoadWindow: boolean;
  requestedTf?: string;
  windowStart?: string;
  windowEnd?: string;
}): { apply: boolean; statusMessage?: string; detail?: string } {
  const tf = String(args.requestedTf || '').toUpperCase() || 'candles';
  const windowDiag = formatWindowLoadDiagnostic({
    requestedTf: tf,
    parsedCount: args.parsedCount,
    windowStart: args.windowStart,
    windowEnd: args.windowEnd,
  });
  if (args.parsedCount <= 0 && args.hadLoadWindow) {
    return {
      apply: false,
      statusMessage: `${windowDiag} — no valid ${tf} feed. Sync local cache or widen parent range dates.`,
      detail: 'empty-window-load',
    };
  }
  if (args.hadLoadWindow && args.parsedCount < MIN_TRUSTED_WINDOW_BARS) {
    return {
      apply: false,
      statusMessage: `${windowDiag} — too few bars for mapping. Check local cache, VPS sync, or parent range span.`,
      detail: args.parsedCount <= 1 ? 'suspicious-single-bar' : 'suspicious-window-load',
    };
  }
  return { apply: true };
}

/** TV Map On: structural/BOS side effects must not reload or clear the visible candle universe. */
export function shouldPreserveTradingViewMappingCandleUniverse(args: {
  chartRenderer: string;
  mappingInputEnabled: boolean;
  timeframeSwitch?: boolean;
  targetTf: string;
  activeChartTf: string;
  candleCount: number;
  structuralNavigation?: boolean;
  reason?: string;
  navigationPath?: string;
}): boolean {
  if (args.chartRenderer !== 'tradingview' || !args.mappingInputEnabled) return false;
  if (args.timeframeSwitch) return false;
  if (args.candleCount <= 0) return false;
  const targetTf = String(args.targetTf || '').toUpperCase();
  const activeTf = String(args.activeChartTf || '').toUpperCase();
  if (!targetTf || targetTf !== activeTf) return false;
  const reason = String(args.reason || '');
  const path = String(args.navigationPath || '');
  return !!(
    args.structuralNavigation
    || reason === 'feed-mismatch-reload'
    || reason === 'tradingview-hierarchy-range-fit'
    || path === 'tradingview-hierarchy-range-fit'
    || path.startsWith('navigateStructural:')
  );
}

export function shouldBlockQuietFullHistoryReload(args: {
  quiet: boolean;
  forceFullHistory?: boolean;
  activeRangeId: string;
  incomingWindowKey: string;
  selectedParentRangeId?: string;
}): boolean {
  if (!args.quiet) return false;
  const hasStructuralContext = !!(args.activeRangeId || args.selectedParentRangeId);
  if (!hasStructuralContext) return false;
  if (args.forceFullHistory) return true;
  return args.incomingWindowKey === 'full';
}

export function formatCandleLoadDiagnostic(d: CandleLoadDiagnostics): string {
  return [
    `Load ${d.requestedTf} ${d.mode}`,
    d.navigationPath || 'load',
    d.rangeId ? `#${d.rangeId}` : 'no-range',
    d.parentRangeId ? `parent #${d.parentRangeId}` : '',
    d.layer || '—',
    d.windowStart && d.windowEnd ? `${d.windowStart}→${d.windowEnd}` : 'full history',
    `liveTail=${d.liveTail ? 'Y' : 'N'}`,
    `${d.filteredCount || d.returnedCount} bars`,
    d.accepted ? 'accepted' : 'rejected',
    d.cameraIntent,
    `replay ${d.replayIndex}${d.playForwardEnabled ? '' : ` · ${d.playForwardReason}`}`,
  ].filter(Boolean).join(' · ');
}
