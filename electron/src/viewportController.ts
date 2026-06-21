/** Map Studio viewport state — preserve time focus across mapping actions. */

export type ViewportMoveReason =
  | 'fit-parent'
  | 'fit-child'
  | 'fit-cursor'
  | 'fit-replay'
  | 'fit-active'
  | 'fit-range'
  | 'fit-case'
  | 'fit-all'
  | 'jump'
  | 'continue-campaign'
  | 'explorer-jump'
  | 'open-child-mapping'
  | 'timeframe-switch'
  | 'initial-load'
  | 'user-pan-zoom';

export const EXPLICIT_VIEWPORT_MOVE_REASONS: ReadonlySet<ViewportMoveReason> = new Set([
  'fit-parent',
  'fit-child',
  'fit-cursor',
  'fit-replay',
  'fit-active',
  'fit-range',
  'fit-case',
  'fit-all',
  'jump',
  'continue-campaign',
  'explorer-jump',
  'open-child-mapping',
]);

export type ActiveViewConfig = {
  timeframe: string;
  center_time_ms: number | null;
  visible_start_ms: number | null;
  visible_end_ms: number | null;
  candle_window_size: number;
  last_user_controlled_view: boolean;
  last_move_reason: ViewportMoveReason | null;
};

export type TimeSpanMs = {
  startMs: number;
  endMs: number;
};

export type OverlaySpanInput = {
  range_start_time?: string | null;
  range_end_time?: string | null;
  range_high_time?: string | null;
  range_low_time?: string | null;
  active_from_time?: string | null;
};

export type SavedRangeOverlayRow = {
  rangeId: string;
  structureLayer: string;
  start?: string | null;
  end?: string | null;
  isActive?: boolean;
  isParentContext?: boolean;
};

export function createDefaultViewConfig(timeframe = 'D1'): ActiveViewConfig {
  return {
    timeframe,
    center_time_ms: null,
    visible_start_ms: null,
    visible_end_ms: null,
    candle_window_size: defaultCandleWindowSize(timeframe),
    last_user_controlled_view: false,
    last_move_reason: null,
  };
}

export function defaultCandleWindowSize(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M15' || tf === 'M5') return 40;
  if (tf === 'H1') return 48;
  if (tf === 'H4') return 52;
  if (tf === 'D1') return 72;
  if (tf === 'W1') return 64;
  if (tf === 'MN1') return 42;
  return 56;
}

export function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

export function shouldPreserveViewport(action: string): boolean {
  const preserveActions = [
    'save-range',
    'save-bos',
    'approve-candidate',
    'edit-candidate',
    'reject-candidate',
    'toggle-child-panel',
    'toggle-explorer',
    'change-mapping-layer',
    'update-session',
    'update-campaign-badges',
    'overlay-update',
    'quiet-candle-refresh',
  ];
  return preserveActions.includes(action);
}

export function isExplicitViewportMove(reason: string | null | undefined): boolean {
  if (!reason) return false;
  return EXPLICIT_VIEWPORT_MOVE_REASONS.has(reason as ViewportMoveReason);
}

export function shouldSuppressAutoViewportFit(config: ActiveViewConfig): boolean {
  if (isExplicitViewportMove(config.last_move_reason)) return true;
  return config.last_user_controlled_view;
}

export function visibleRangeFromCenter(
  centerMs: number,
  candleWindowSize: number,
  barDurationMs: number,
): TimeSpanMs {
  const half = Math.max(1, Math.floor(candleWindowSize / 2));
  const span = half * 2 * barDurationMs;
  const startMs = centerMs - half * barDurationMs;
  const endMs = startMs + span;
  return { startMs, endMs: Math.max(endMs, startMs + barDurationMs) };
}

export function barDurationMsForTimeframe(timeframe: string): number {
  const tf = String(timeframe || 'D1').toUpperCase();
  if (tf === 'M5') return 5 * 60 * 1000;
  if (tf === 'M15') return 15 * 60 * 1000;
  if (tf === 'H1') return 60 * 60 * 1000;
  if (tf === 'H4') return 4 * 60 * 60 * 1000;
  if (tf === 'D1') return 24 * 60 * 60 * 1000;
  if (tf === 'W1') return 7 * 24 * 60 * 60 * 1000;
  if (tf === 'MN1') return 30 * 24 * 60 * 60 * 1000;
  return 24 * 60 * 60 * 1000;
}

export function preserveCenterOnTimeframeSwitch(
  prev: ActiveViewConfig,
  nextTimeframe: string,
  fallbackCenterMs?: number | null,
): ActiveViewConfig {
  const center = prev.center_time_ms ?? fallbackCenterMs ?? null;
  const windowSize = defaultCandleWindowSize(nextTimeframe);
  if (center === null) {
    return {
      ...prev,
      timeframe: nextTimeframe,
      candle_window_size: windowSize,
      last_move_reason: 'timeframe-switch',
    };
  }
  const span = visibleRangeFromCenter(center, windowSize, barDurationMsForTimeframe(nextTimeframe));
  return {
    ...prev,
    timeframe: nextTimeframe,
    center_time_ms: center,
    visible_start_ms: span.startMs,
    visible_end_ms: span.endMs,
    candle_window_size: windowSize,
    last_move_reason: 'timeframe-switch',
  };
}

export function updateViewConfigFromVisibleDomain(
  prev: ActiveViewConfig,
  domain: { start: string; end: string; visibleBars?: number },
  opts?: { userControlled?: boolean; reason?: ViewportMoveReason | null },
): ActiveViewConfig {
  const startMs = parseTimeMs(domain.start);
  const endMs = parseTimeMs(domain.end);
  const center = startMs !== null && endMs !== null
    ? Math.round((startMs + endMs) / 2)
    : prev.center_time_ms;
  return {
    ...prev,
    center_time_ms: center,
    visible_start_ms: startMs ?? prev.visible_start_ms,
    visible_end_ms: endMs ?? prev.visible_end_ms,
    candle_window_size: domain.visibleBars && domain.visibleBars > 0
      ? domain.visibleBars
      : prev.candle_window_size,
    last_user_controlled_view: opts?.userControlled ?? prev.last_user_controlled_view,
    last_move_reason: opts?.reason ?? prev.last_move_reason,
  };
}

export function markExplicitViewportMove(
  prev: ActiveViewConfig,
  reason: ViewportMoveReason,
  patch?: Partial<Pick<ActiveViewConfig, 'center_time_ms' | 'visible_start_ms' | 'visible_end_ms'>>,
): ActiveViewConfig {
  return {
    ...prev,
    ...patch,
    last_user_controlled_view: false,
    last_move_reason: reason,
  };
}

export function overlaySpanMs(row: OverlaySpanInput): TimeSpanMs | null {
  const startMs = parseTimeMs(
    row.range_start_time || row.active_from_time || row.range_high_time || row.range_low_time,
  );
  const endMs = parseTimeMs(
    row.range_end_time || row.range_low_time || row.range_high_time || row.range_start_time,
  );
  if (startMs === null && endMs === null) return null;
  const s = startMs ?? endMs!;
  const e = endMs ?? startMs!;
  return { startMs: Math.min(s, e), endMs: Math.max(s, e) };
}

export type RangeSpanPx = { x1: number; x2: number };

export function rangeSpanPx(
  startMs: number | null,
  endMs: number | null,
  timeToX: (ms: number) => number,
  plotLeft: number,
  plotRight: number,
  opts?: { strict?: boolean; minWidthPx?: number },
): RangeSpanPx | null {
  const strict = !!opts?.strict;
  const minW = opts?.minWidthPx ?? 24;
  const clampX = (x: number) => Math.max(plotLeft, Math.min(plotRight, x));
  if (startMs !== null && endMs !== null) {
    const xA = timeToX(startMs);
    const xB = timeToX(endMs);
    if (Number.isFinite(xA) && Number.isFinite(xB)) {
      const x1 = clampX(Math.min(xA, xB));
      const x2 = clampX(Math.max(xA, xB));
      if (x2 - x1 >= minW) return { x1, x2 };
    }
  }
  if (strict) return null;
  return { x1: plotLeft, x2: plotRight };
}

export function filterGuidedModeRangeOverlays(
  overlays: SavedRangeOverlayRow[],
  ctx: {
    guidedActive: boolean;
    showAllRanges: boolean;
    parentRangeId: string | null;
    savedChildIds: string[];
    activeRangeId: string | null;
    ancestorIds: string[];
  },
): SavedRangeOverlayRow[] {
  if (!ctx.guidedActive || ctx.showAllRanges) return overlays;
  const allowed = new Set<string>([
    ...ctx.ancestorIds,
    ...ctx.savedChildIds,
    ...(ctx.activeRangeId ? [ctx.activeRangeId] : []),
    ...(ctx.parentRangeId ? [ctx.parentRangeId] : []),
  ]);
  return overlays.filter((row) => {
    if (row.isActive) return true;
    if (allowed.has(row.rangeId)) return true;
    return false;
  });
}

export function guidedMappingPlaybackWindowMs(cursor: {
  cursor_time_ms: number;
  parent_end_time_ms: number;
  coverage_gap_end_ms?: number | null;
}): { startMs: number; endMs: number } {
  const endMs = cursor.coverage_gap_end_ms != null
    ? Math.min(cursor.parent_end_time_ms, cursor.coverage_gap_end_ms)
    : cursor.parent_end_time_ms;
  return {
    startMs: cursor.cursor_time_ms,
    endMs: Math.max(endMs, cursor.cursor_time_ms),
  };
}

export function isPlaybackOutsideParentWindow(
  replayTimeMs: number | null,
  parentStartMs: number | null,
  parentEndMs: number | null,
  guidedCtx?: {
    cursor_time_ms?: number | null;
    coverage_gap_end_ms?: number | null;
  } | null,
): boolean {
  if (replayTimeMs === null || parentEndMs === null) return false;
  if (guidedCtx?.cursor_time_ms != null && Number.isFinite(guidedCtx.cursor_time_ms)) {
    const win = guidedMappingPlaybackWindowMs({
      cursor_time_ms: guidedCtx.cursor_time_ms,
      parent_end_time_ms: parentEndMs,
      coverage_gap_end_ms: guidedCtx.coverage_gap_end_ms ?? null,
    });
    return replayTimeMs < win.startMs || replayTimeMs > win.endMs;
  }
  if (parentStartMs === null) return false;
  return replayTimeMs < parentStartMs || replayTimeMs > parentEndMs;
}

export const PLAYBACK_OUTSIDE_PARENT_MESSAGE = 'Playback outside active parent window';

export const CONTEXT_REPLAY_LOOKBACK_BARS = 100;

export type CandleTimeLike = { time: string };

/** Viewport controller API — preserve center anchor across timeframe / mapping actions. */
export const ViewportController = {
  createDefault: createDefaultViewConfig,
  defaultCandleWindowSize,
  barDurationMsForTimeframe,
  visibleRangeFromCenter,
  preserveCenterOnTimeframeSwitch,
  updateViewConfigFromVisibleDomain,
  markExplicitViewportMove,
  shouldSuppressAutoViewportFit,
  buildFitWindowFromViewConfig,
  buildBaseTimeDomain,
  clampSpanToCandleExtent,
} as const;

export function clampSpanToCandleExtent(
  startMs: number,
  endMs: number,
  candles: CandleTimeLike[],
): { startMs: number; endMs: number } {
  if (!candles.length) return { startMs, endMs };
  const times = candles
    .map((c) => parseTimeMs(c.time))
    .filter((ms): ms is number => ms !== null);
  if (!times.length) return { startMs, endMs };
  const first = Math.min(...times);
  const last = Math.max(...times);
  let s = startMs;
  let e = endMs;
  if (s < first) {
    const shift = first - s;
    s = first;
    e = Math.min(last, e + shift);
  }
  if (e > last) {
    const shift = e - last;
    e = last;
    s = Math.max(first, s - shift);
  }
  if (e <= s) e = Math.min(last, s + barDurationMsForTimeframe('D1'));
  return { startMs: s, endMs: e };
}

export function buildBaseTimeDomain(
  config: Pick<ActiveViewConfig, 'center_time_ms' | 'visible_start_ms' | 'visible_end_ms' | 'candle_window_size' | 'timeframe'>,
  candles: CandleTimeLike[],
): { start: Date; end: Date } | null {
  let startMs = config.visible_start_ms;
  let endMs = config.visible_end_ms;
  if (startMs === null || endMs === null) {
    const center = config.center_time_ms;
    if (center === null || !Number.isFinite(center)) return null;
    const span = visibleRangeFromCenter(
      center,
      config.candle_window_size,
      barDurationMsForTimeframe(config.timeframe),
    );
    startMs = span.startMs;
    endMs = span.endMs;
  }
  const clamped = clampSpanToCandleExtent(startMs, endMs, candles);
  return { start: new Date(clamped.startMs), end: new Date(clamped.endMs) };
}

export function buildFitWindowFromViewConfig(
  config: ActiveViewConfig,
  candles: CandleTimeLike[],
): { start: string; end: string; low: number; high: number; padRatio: number } | null {
  const domain = buildBaseTimeDomain(config, candles);
  if (!domain) return null;
  return {
    start: domain.start.toISOString(),
    end: domain.end.toISOString(),
    low: 0,
    high: 0,
    padRatio: 0.12,
  };
}

/** Widen a bounded candle fetch window for replay / mapping context (left history + optional end). */
export function expandCandleLoadWindowForContext(
  window: { start: string; end: string; label: string },
  timeframe: string,
  opts?: { lookbackBars?: number; endDay?: string | null },
): { start: string; end: string; label: string } {
  const lookback = Math.max(8, opts?.lookbackBars ?? CONTEXT_REPLAY_LOOKBACK_BARS);
  const barMs = barDurationMsForTimeframe(timeframe);
  const startMs = parseTimeMs(window.start.includes('T') ? window.start : `${window.start}T00:00:00.000Z`);
  const endMs = parseTimeMs(window.end.includes('T') ? window.end : `${window.end}T23:59:59.000Z`);
  const expandedStart = startMs !== null
    ? new Date(startMs - lookback * barMs).toISOString().slice(0, 10)
    : window.start;
  let expandedEnd = window.end;
  if (opts?.endDay) {
    const cursorEnd = opts.endDay.slice(0, 10);
    const curMs = parseTimeMs(`${cursorEnd}T23:59:59.000Z`);
    if (curMs !== null && endMs !== null && curMs > endMs) {
      expandedEnd = cursorEnd;
    } else if (curMs !== null && endMs === null) {
      expandedEnd = cursorEnd;
    }
  }
  return {
    start: expandedStart,
    end: expandedEnd,
    label: `${window.label} +${lookback} ctx`,
  };
}
