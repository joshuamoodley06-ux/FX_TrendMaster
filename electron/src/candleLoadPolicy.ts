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
  let loadStart = addIsoDays(startDay, -pad.beforeDays);
  let loadEnd = addIsoDays(endDay, pad.afterDays);
  const spanDays = Math.max(
    1,
    Math.round((new Date(`${loadEnd}T00:00:00.000Z`).getTime() - new Date(`${loadStart}T00:00:00.000Z`).getTime()) / 86400000),
  );
  if (spanDays > pad.maxSpanDays) {
    const trim = spanDays - pad.maxSpanDays;
    const trimBefore = Math.ceil(trim * 0.65);
    const trimAfter = trim - trimBefore;
    loadStart = addIsoDays(loadStart, trimBefore);
    loadEnd = addIsoDays(loadEnd, -trimAfter);
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

export function shouldApplyParsedCandles(args: {
  parsedCount: number;
  previousCount: number;
  hadLoadWindow: boolean;
}): { apply: boolean; statusMessage?: string; detail?: string } {
  if (args.parsedCount <= 0 && args.hadLoadWindow) {
    return {
      apply: false,
      statusMessage: args.previousCount > 0
        ? 'No candles for this timeframe/window — keeping prior chart. Sync local cache or widen parent range dates.'
        : 'No candles for this timeframe/window — load a parent timeframe first or sync cache.',
      detail: 'empty-window-load',
    };
  }
  if (
    args.hadLoadWindow
    && args.parsedCount < MIN_TRUSTED_WINDOW_BARS
    && args.previousCount >= MIN_TRUSTED_WINDOW_BARS
  ) {
    return {
      apply: false,
      statusMessage: `Window load returned only ${args.parsedCount} bar(s) — keeping prior ${args.previousCount} bars. Check local cache or VPS sync.`,
      detail: 'suspicious-window-load',
    };
  }
  return { apply: true };
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
