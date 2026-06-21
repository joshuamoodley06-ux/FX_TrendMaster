import type { ZoomTransform } from 'd3-zoom';
import { zoomIdentity } from 'd3-zoom';
import { parseTimeMs } from './viewportController';

export type ViewportClampSpan = {
  start: string;
  end: string;
};

export type StoredViewportClamp = {
  enabled: boolean;
  startTime: string | null;
  endTime: string | null;
  containerTimeframe: string | null;
  viewContext: 'parent' | 'child' | null;
};

export function normalizeViewportClampSpan(
  startTime?: string | null,
  endTime?: string | null,
): ViewportClampSpan | null {
  const startMs = parseTimeMs(startTime);
  const endMs = parseTimeMs(endTime);
  if (startMs == null || endMs == null || endMs <= startMs) return null;
  return { start: new Date(startMs).toISOString(), end: new Date(endMs).toISOString() };
}

export function intersectClampSpanWithCandles(
  span: ViewportClampSpan,
  candles: { time: string }[],
): ViewportClampSpan | null {
  if (!candles.length) return span;
  const startMs = parseTimeMs(span.start);
  const endMs = parseTimeMs(span.end);
  if (startMs == null || endMs == null) return null;
  const times = candles
    .map((c) => parseTimeMs(c.time))
    .filter((ms): ms is number => ms != null);
  if (!times.length) return span;
  const first = Math.min(...times);
  const last = Math.max(...times);
  const s = Math.max(startMs, first);
  const e = Math.min(endMs, last);
  if (e <= s) return null;
  return { start: new Date(s).toISOString(), end: new Date(e).toISOString() };
}

type TimeScale = {
  (value: Date): number;
  invert(value: number): Date;
};

/** Empty margin past first candle (fraction of visible span). */
export const CHART_CLAMP_EDGE_PADDING_LEFT = 0.08;
/** Empty margin past last candle — needs ~50% so the latest bar can reach chart centre. */
export const CHART_CLAMP_EDGE_PADDING_RIGHT = 0.52;
/** @deprecated use CHART_CLAMP_EDGE_PADDING_LEFT / _RIGHT */
export const CHART_CLAMP_EDGE_PADDING_RATIO = CHART_CLAMP_EDGE_PADDING_LEFT;

export function candleExtentSpan(candles: { time: string }[]): ViewportClampSpan | null {
  if (!candles.length) return null;
  const times = candles
    .map((c) => parseTimeMs(c.time))
    .filter((ms): ms is number => ms != null);
  if (!times.length) return null;
  return {
    start: new Date(Math.min(...times)).toISOString(),
    end: new Date(Math.max(...times)).toISOString(),
  };
}

/** Pan bounds = loaded candles, optionally narrowed by viewport drill-down clamp. */
export function resolveChartPanBounds(
  candles: { time: string }[],
  viewportClamp?: ViewportClampSpan | null,
): ViewportClampSpan | null {
  const dataSpan = candleExtentSpan(candles);
  if (!dataSpan) return null;
  if (!viewportClamp?.start || !viewportClamp?.end) return dataSpan;
  return intersectClampSpanWithCandles(viewportClamp, candles) ?? dataSpan;
}

function ensureDomainOverlapsBounds(d0: number, d1: number, minMs: number, maxMs: number): [number, number] {
  let start = d0;
  let end = d1;
  if (end < minMs) {
    const shift = minMs - end;
    start += shift;
    end += shift;
  }
  if (start > maxMs) {
    const shift = start - maxMs;
    start -= shift;
    end -= shift;
  }
  return [start, end];
}

/** Keep zoom/pan X domain inside bounds with candles always intersecting the viewport. */
export function clampChartTransformToTimeBounds(
  transform: ZoomTransform,
  x0: TimeScale,
  bounds: ViewportClampSpan,
  plotLeft: number,
  plotWidth: number,
  edgePaddingLeft = CHART_CLAMP_EDGE_PADDING_LEFT,
  edgePaddingRight = CHART_CLAMP_EDGE_PADDING_RIGHT,
): ZoomTransform {
  const minMs = parseTimeMs(bounds.start);
  const maxMs = parseTimeMs(bounds.end);
  if (minMs == null || maxMs == null || maxMs <= minMs) return transform;

  const maxSpanMs = maxMs - minMs;
  let d0 = transform.rescaleX(x0 as any).domain()[0].getTime();
  let d1 = transform.rescaleX(x0 as any).domain()[1].getTime();
  let span = d1 - d0;

  if (span > maxSpanMs) {
    span = maxSpanMs;
    const mid = (minMs + maxMs) / 2;
    d0 = mid - span / 2;
    d1 = mid + span / 2;
  }

  const edgePadLeftMs = Math.max(0, span * edgePaddingLeft);
  const edgePadRightMs = Math.max(0, span * edgePaddingRight);
  const panMinMs = minMs - edgePadLeftMs;
  const panMaxMs = maxMs + edgePadRightMs;

  if (d0 < panMinMs) {
    d1 += panMinMs - d0;
    d0 = panMinMs;
  }
  if (d1 > panMaxMs) {
    d0 -= d1 - panMaxMs;
    d1 = panMaxMs;
  }
  if (d0 < panMinMs) d0 = panMinMs;

  [d0, d1] = ensureDomainOverlapsBounds(d0, d1, minMs, maxMs);

  const startPx = x0(new Date(d0));
  const endPx = x0(new Date(d1));
  const spanPx = Math.max(1, endPx - startPx);
  const k = Math.max(0.35, plotWidth / spanPx);
  const tx = plotLeft - k * startPx;
  return zoomIdentity.translate(tx, 0).scale(k);
}
