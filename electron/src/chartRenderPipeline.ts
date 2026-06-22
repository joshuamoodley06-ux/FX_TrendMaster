import * as d3 from 'd3';
import type { MappingPoint, MappingPointKind } from './types';
import {
  focusYExtentsWithParent,
  FOCUS_Y_PAD_RATIO,
  shouldUseCandleOnlyYScale,
  type FocusOverlayTier,
} from './chartFocusMode';

export const CHART_LAYER_BG = 'chart-bg';
export const CHART_LAYER_CANDLES = 'chart-layer-candles';
export const CHART_LAYER_OVERLAYS = 'chart-layer-overlays';
export const CHART_LAYER_DRAFT_POINTS = 'chart-layer-draft-points';
export const CHART_LAYER_UI = 'chart-layer-ui';

export type PipelineCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type ChartSurfaceMetrics = {
  width: number;
  height: number;
  margin: { top: number; right: number; bottom: number; left: number };
  innerW: number;
  innerH: number;
};

export type ChartViewportState = {
  renderData: PipelineCandle[];
  visible: PipelineCandle[];
  x0: d3.ScaleTime<number, number>;
  zx: d3.ScaleTime<number, number>;
  y: d3.ScaleLinear<number, number>;
  domain: [Date, Date];
  yDomain: [number, number];
  barSpacingPx: number;
  candleW: number;
  replayCutMs: number | null;
  metrics: ChartSurfaceMetrics;
  baseLo: number;
  baseHi: number;
};

export type SavedRangeOverlayRow = {
  rangeId: string;
  high: number;
  low: number;
  start?: string | null;
  end?: string | null;
  status?: string;
  structureLayer: string;
  isActive?: boolean;
  isParentContext?: boolean;
  rangeScope?: string;
  overlayLabel?: string;
  focusTier?: FocusOverlayTier;
};

export type ParentOverlayRow = {
  kind: 'high' | 'low';
  price: number;
  label: string;
  structureLayer?: string;
  start?: string;
  end?: string;
  isGuidedParentContext?: boolean;
  focusTier?: FocusOverlayTier;
};

export type RangeLineRow = {
  id: string;
  kind: 'high' | 'low';
  price: number;
  label: string;
  color: string;
  style: { opacity: number; width: number; dash: string; showLabel?: boolean };
  x1: number;
  x2: number;
};

export type ChartRenderStyleFns = {
  snapChartStrokePx: (v: number) => number;
  snapChartPx: (v: number) => number;
  priceLineY: (y: d3.ScaleLinear<number, number>, price: number) => number;
  candleTimeDate: (t: string) => Date;
  candleTimeMs: (t?: string | null) => number;
  shortTime: (t: string, tf: string) => string;
  structureLayerLineColor: (layer: string) => string;
  guidedParentLineColor: (layer: string) => string;
  savedRangeLineStyle: (status: string, opts?: Record<string, unknown>) => { opacity: number; width: number; dash: string };
  draftRangeLineStyle: () => { opacity: number; width: number; dash: string };
  overlayLineStyleWithFocus: (
    base: { opacity: number; width: number; dash: string },
    focusMode: boolean,
    tier?: FocusOverlayTier,
    opts?: { isDraft?: boolean },
  ) => { opacity: number; width: number; dash: string; showLabel: boolean };
  rangeSpanX: (
    zx: d3.ScaleTime<number, number>,
    start: string | null | undefined,
    end: string | null | undefined,
    margin: ChartSurfaceMetrics['margin'],
    innerW: number,
    opts?: { strict?: boolean },
  ) => { x1: number; x2: number } | null;
};

export function applyChartSurfaceSize(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  metrics: ChartSurfaceMetrics,
  snapChartPx: (v: number) => number,
  chartDevicePixelRatio: () => number,
) {
  const dpr = chartDevicePixelRatio();
  svg
    .style('width', `${metrics.width}px`)
    .style('height', `${metrics.height}px`)
    .attr('width', snapChartPx(metrics.width * dpr))
    .attr('height', snapChartPx(metrics.height * dpr))
    .attr('viewBox', `0 0 ${metrics.width} ${metrics.height}`);
}

/** One-time shell; never call selectAll('*').remove() on updates. */
export function ensureChartShell(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  metrics: ChartSurfaceMetrics,
  shellReady: { current: boolean },
) {
  if (!shellReady.current) {
    svg.selectAll('*').remove();
    svg.append('rect').attr('class', CHART_LAYER_BG).attr('fill', '#000');
    svg.append('g').attr('class', CHART_LAYER_CANDLES);
    svg.append('g').attr('class', CHART_LAYER_OVERLAYS);
    svg.append('g').attr('class', CHART_LAYER_DRAFT_POINTS);
    svg.append('g').attr('class', CHART_LAYER_UI);
    shellReady.current = true;
  }
  svg.select(`rect.${CHART_LAYER_BG}`)
    .attr('width', metrics.width)
    .attr('height', metrics.height);
}

export { targetVisibleBarsForTimeframe } from './chartViewportPolicy';

function medianBarSpacingPx(
  candles: PipelineCandle[],
  zx: d3.ScaleTime<number, number>,
  candleTimeDate: (t: string) => Date,
  snapChartStrokePx: (v: number) => number,
): number {
  if (candles.length < 2) return 10;
  const gaps: number[] = [];
  const step = Math.max(1, Math.floor(candles.length / 28));
  for (let i = step; i < candles.length; i += step) {
    const a = zx(candleTimeDate(candles[i - 1].time));
    const b = zx(candleTimeDate(candles[i].time));
    const gap = Math.abs(b - a);
    if (Number.isFinite(gap) && gap > 0.5) gaps.push(gap);
  }
  if (!gaps.length) return 10;
  gaps.sort((x, y) => x - y);
  return gaps[Math.floor(gaps.length / 2)] || 10;
}

export type ComputeViewportArgs = {
  candles: PipelineCandle[];
  replayCutTime?: string | null;
  timeframe: string;
  transform: d3.ZoomTransform;
  metrics: ChartSurfaceMetrics;
  scaleMode: string;
  chartFocusMode?: boolean;
  hasRange?: boolean;
  rangeHigh?: number;
  rangeLow?: number;
  parentHi?: number;
  parentLo?: number;
  savedHi?: number;
  savedLo?: number;
  draftPrices?: number[];
  candleWidthScale?: number;
  priorYDomain?: [number, number] | null;
  yPanPx: number;
  yZoom: number;
  style: Pick<ChartRenderStyleFns, 'candleTimeDate' | 'candleTimeMs' | 'snapChartStrokePx' | 'snapChartPx'>;
  onVisibleDomainChange?: (d: {
    start: string;
    end: string;
    priceLow: number;
    priceHigh: number;
    visibleBars: number;
    barSpacingPx: number;
  }) => void;
};

export function computeChartViewport(args: ComputeViewportArgs): ChartViewportState | null {
  const {
    candles, replayCutTime, timeframe, transform, metrics, scaleMode, chartFocusMode,
    hasRange, rangeHigh, rangeLow, parentHi, parentLo, savedHi, savedLo, draftPrices,
    candleWidthScale, priorYDomain, yPanPx, yZoom, style, onVisibleDomainChange,
  } = args;
  const { margin, innerW, innerH } = metrics;
  const replayCutMs = replayCutTime ? style.candleTimeMs(replayCutTime) : null;
  const renderData = replayCutMs && Number.isFinite(replayCutMs)
    ? candles.filter((d) => style.candleTimeMs(d.time) <= replayCutMs)
    : candles;
  if (!renderData.length) return null;

  const dates = renderData.map((d) => style.candleTimeDate(d.time)).filter((d) => Number.isFinite(d.getTime()));
  const x0 = d3.scaleTime()
    .domain(d3.extent(dates) as [Date, Date])
    .range([margin.left, margin.left + innerW]);
  let zx = transform.rescaleX(x0);
  let domain = zx.domain() as [Date, Date];
  const inDomain = (d: PipelineCandle) => {
    const dt = style.candleTimeDate(d.time);
    return Number.isFinite(dt.getTime()) && dt >= domain[0] && dt <= domain[1];
  };
  let visible = renderData.filter(inDomain);
  if (!visible.length && renderData.length) {
    const fitBars = targetVisibleBarsForTimeframe(timeframe) * 2;
    const tail = renderData.slice(-Math.min(renderData.length, fitBars));
    const tailDates = tail.map((d) => style.candleTimeDate(d.time)).filter((d) => Number.isFinite(d.getTime()));
    const ext = d3.extent(tailDates) as [Date, Date];
    if (ext[0] && ext[1] && Number.isFinite(ext[0].getTime()) && Number.isFinite(ext[1].getTime())) {
      x0.domain(ext);
      zx = d3.zoomIdentity.rescaleX(x0);
      domain = zx.domain() as [Date, Date];
      visible = renderData.filter(inDomain);
    }
  }
  const v = visible;
  const autoscaleLookback = Math.min(v.length, 72);
  const autoScaleSource = scaleMode === 'auto' ? v.slice(Math.max(0, v.length - autoscaleLookback)) : v;
  const hiData = d3.max(autoScaleSource, (d) => d.high)
    ?? (priorYDomain ? priorYDomain[1] : (d3.max(renderData.slice(-120), (d) => d.high) ?? 1));
  const loData = d3.min(autoScaleSource, (d) => d.low)
    ?? (priorYDomain ? priorYDomain[0] : (d3.min(renderData.slice(-120), (d) => d.low) ?? 0));
  const visibleHi = d3.max(v, (d) => d.high) ?? hiData;
  const visibleLo = d3.min(v, (d) => d.low) ?? loData;
  let yHi = hiData;
  let yLo = loData;
  const useCandleOnlyY = shouldUseCandleOnlyYScale(!!chartFocusMode);
  if (useCandleOnlyY && v.length) {
    const candleY = focusYExtentsWithParent(
      v.map((d) => ({ time: d.time, high: d.high, low: d.low })),
      parentHi,
      parentLo,
    );
    if (candleY) {
      yHi = candleY.high;
      yLo = candleY.low;
    }
  } else {
    if (hasRange && scaleMode === 'range' && v.length) {
      yHi = Math.max(rangeHigh ?? yHi, visibleHi);
      yLo = Math.min(rangeLow ?? yLo, visibleLo);
    }
    if (Number.isFinite(parentHi)) yHi = Math.max(yHi, Number(parentHi));
    if (Number.isFinite(parentLo)) yLo = Math.min(yLo, Number(parentLo));
    if (Number.isFinite(savedHi)) yHi = Math.max(yHi, Number(savedHi));
    if (Number.isFinite(savedLo)) yLo = Math.min(yLo, Number(savedLo));
    if (draftPrices?.length) {
      yHi = Math.max(yHi, ...draftPrices);
      yLo = Math.min(yLo, ...draftPrices);
    }
  }
  const padRatio = useCandleOnlyY ? FOCUS_Y_PAD_RATIO : 0.18;
  const pad = Math.max((yHi - yLo) * padRatio, 1);
  const baseLo = yLo - pad;
  const baseHi = yHi + pad;
  const zoomY = Math.max(0.25, Math.min(32, yZoom || 1));
  const baseSpan = Math.max(1e-9, baseHi - baseLo);
  const span = baseSpan / zoomY;
  const pricePerPx = span / Math.max(1, innerH);
  const center = ((baseLo + baseHi) / 2) + (yPanPx * pricePerPx);
  const yDomain: [number, number] = [center - span / 2, center + span / 2];
  const barSpacingPx = v.length >= 2
    ? medianBarSpacingPx(v, zx, style.candleTimeDate, style.snapChartStrokePx)
    : innerW / Math.max(8, v.length);
  onVisibleDomainChange?.({
    start: domain[0].toISOString(),
    end: domain[1].toISOString(),
    priceLow: yDomain[0],
    priceHigh: yDomain[1],
    visibleBars: v.length,
    barSpacingPx,
  });
  const y = d3.scaleLinear().domain(yDomain).range([margin.top + innerH, margin.top]).nice();
  const widthScale = Math.max(0.35, Math.min(4, Number(candleWidthScale || 1)));
  const candleW = Math.max(2, Math.min(48, style.snapChartPx(barSpacingPx * 0.8 * widthScale)));
  return {
    renderData,
    visible: v,
    x0,
    zx,
    y,
    domain,
    yDomain,
    barSpacingPx,
    candleW,
    replayCutMs,
    metrics,
    baseLo,
    baseHi,
  };
}

function drawRangeLineLabels(
  _container: d3.Selection<SVGGElement, unknown, null, undefined>,
  _rows: RangeLineRow[],
  _y: d3.ScaleLinear<number, number>,
  _margin: ChartSurfaceMetrics['margin'],
) {
  // Range RH/RL pill labels intentionally hidden — horizontal lines only.
}

export type RenderCandlesArgs = {
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  viewport: ChartViewportState;
  timeframe: string;
  replayCutTime?: string | null;
  style: ChartRenderStyleFns;
};

export function renderCandlesLayer(args: RenderCandlesArgs): void {
  const { svg, viewport, timeframe, replayCutTime, style } = args;
  const { metrics, visible: v, renderData, zx, y, domain, candleW, barSpacingPx, replayCutMs } = viewport;
  const { margin, innerW, innerH, height, width } = metrics;
  const layer = svg.select<SVGGElement>(`g.${CHART_LAYER_CANDLES}`);

  const grid = layer.selectAll<SVGGElement, number>('g.y-grid').data([0]).join('g').attr('class', 'y-grid');
  grid.selectAll<SVGLineElement, number>('line.ygrid').data(y.ticks(7)).join('line')
    .attr('class', 'ygrid')
    .attr('x1', margin.left)
    .attr('x2', margin.left + innerW)
    .attr('y1', (d) => style.snapChartStrokePx(y(d)))
    .attr('y2', (d) => style.snapChartStrokePx(y(d)))
    .attr('stroke', 'rgba(255,255,255,.08)')
    .attr('shape-rendering', 'crispEdges');
  grid.selectAll<SVGTextElement, number>('text.ytick').data(y.ticks(7)).join('text')
    .attr('class', 'ytick')
    .attr('x', 10)
    .attr('y', (d) => y(d) + 4)
    .attr('fill', 'rgba(226,232,240,.65)')
    .attr('font-size', 13)
    .text((d) => Number(d).toFixed(2));

  const slotW = barSpacingPx;
  const candlesG = layer.selectAll<SVGGElement, number>('g.candles').data([0]).join('g').attr('class', 'candles').attr('shape-rendering', 'crispEdges');
  candlesG.selectAll<SVGGElement, PipelineCandle>('g.candle')
    .data(v, (d) => d.time)
    .join(
      (enter) => enter.append('g').attr('class', 'candle'),
      (update) => update,
      (exit) => exit.remove(),
    )
    .each(function (d) {
      const g = d3.select(this);
      g.selectAll('*').remove();
      const up = d.close >= d.open;
      const color = up ? '#35e783' : '#ff5b6e';
      const xCenter = style.snapChartStrokePx(zx(style.candleTimeDate(d.time)));
      const yHigh = style.snapChartPx(y(d.high));
      const yLow = style.snapChartPx(y(d.low));
      const yOpen = style.snapChartPx(y(d.open));
      const yClose = style.snapChartPx(y(d.close));
      const bodyTop = Math.min(yOpen, yClose);
      const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
      const bodyLeft = style.snapChartPx(xCenter - candleW / 2);
      g.append('line')
        .attr('x1', xCenter).attr('x2', xCenter)
        .attr('y1', yHigh).attr('y2', yLow)
        .attr('stroke', color)
        .attr('stroke-width', slotW >= 6 ? 1.25 : 1)
        .attr('vector-effect', 'non-scaling-stroke');
      g.append('rect')
        .attr('x', bodyLeft)
        .attr('y', bodyTop)
        .attr('width', candleW)
        .attr('height', bodyHeight)
        .attr('fill', color);
    });

  const xAxisG = layer.selectAll<SVGGElement, number>('g.x-axis').data([0]).join('g').attr('class', 'x-axis')
    .attr('transform', `translate(0,${height - margin.bottom})`);
  const xAxis = d3.axisBottom(zx).ticks(8).tickFormat((d: Date | d3.NumberValue) => style.shortTime((d as Date).toISOString?.() || String(d), timeframe));
  xAxisG.call(xAxis as never);
  xAxisG.selectAll('text').attr('fill', 'rgba(226,232,240,.7)').attr('font-size', 12);
  svg.selectAll('.domain,.tick line').attr('stroke', 'rgba(226,232,240,.18)');

  layer.selectAll<SVGTextElement, string>('text.chart-status')
    .data(v.length ? [] : ['Replay cursor is outside the current camera view. Pan left/right or click Latest.'])
    .join(
      (enter) => enter.append('text').attr('class', 'chart-status'),
      (update) => update,
      (exit) => exit.remove(),
    )
    .attr('x', margin.left + innerW / 2)
    .attr('y', margin.top + 34)
    .attr('text-anchor', 'middle')
    .attr('fill', 'rgba(255,191,47,.75)')
    .attr('font-size', 12)
    .attr('font-weight', 900)
    .text((d) => d);

  layer.selectAll<SVGTextElement, string>('text.chart-empty')
    .data([])
    .join('text')
    .attr('class', 'chart-empty')
    .remove();
  clearChartEmptyMessage(svg);
}

export type RenderOverlaysArgs = {
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  viewport: ChartViewportState;
  savedRanges: SavedRangeOverlayRow[];
  parentOverlays: ParentOverlayRow[];
  draftRange?: {
    visible?: boolean;
    high: number;
    low: number;
    start?: string;
    end?: string;
    structureLayer: string;
  } | null;
  overlaySpanStrict?: boolean;
  chartFocusMode?: boolean;
  draftRangeVisible?: boolean;
  guidedCursorTimeMs?: number | null;
  guidedParentEndMs?: number | null;
  replayCutTime?: string | null;
  selectedCandleTime?: string | null;
  selectedCandlePrice?: number | null;
  style: ChartRenderStyleFns;
};

export function renderOverlaysLayer(args: RenderOverlaysArgs): void {
  const {
    svg, viewport, savedRanges, parentOverlays, draftRange, overlaySpanStrict,
    chartFocusMode, draftRangeVisible, guidedCursorTimeMs, guidedParentEndMs,
    replayCutTime, selectedCandleTime, selectedCandlePrice, style,
  } = args;
  const { metrics, zx, y, domain, candleW, renderData, replayCutMs } = viewport;
  const { margin, innerW, innerH } = metrics;
  const spanStrict = !!overlaySpanStrict;
  const layer = svg.select<SVGGElement>(`g.${CHART_LAYER_OVERLAYS}`);

  const savedRows: RangeLineRow[] = savedRanges.flatMap((r) => {
    const baseStyle = style.savedRangeLineStyle(r.status || 'ACTIVE', {
      isParentContext: r.isParentContext,
      isActive: r.isActive,
      rangeScope: r.rangeScope,
    });
    const lineStyle = style.overlayLineStyleWithFocus(
      baseStyle,
      !!chartFocusMode,
      r.focusTier,
      { isDraft: !!r.isActive && !!draftRangeVisible },
    );
    const color = style.structureLayerLineColor(r.structureLayer);
    const prefix = r.isParentContext ? 'ctx ' : '';
    const scopeLabel = r.rangeScope === 'MINOR' ? ' MINOR' : '';
    const name = r.overlayLabel || `#${r.rangeId}`;
    const span = style.rangeSpanX(zx, r.start, r.end, margin, innerW, { strict: spanStrict });
    if (!span) return [];
    const rowBase = { color, style: lineStyle, x1: span.x1, x2: span.x2 };
    return [
      { id: `${r.rangeId}-high`, kind: 'high' as const, price: r.high, label: `${prefix}${name}${scopeLabel} RH`, ...rowBase },
      { id: `${r.rangeId}-low`, kind: 'low' as const, price: r.low, label: `${prefix}${name}${scopeLabel} RL`, ...rowBase },
    ];
  });

  const sg = layer.selectAll<SVGGElement, number>('g.savedRangeLines').data([0]).join('g')
    .attr('class', 'savedRangeLines').attr('pointer-events', 'none');
  sg.selectAll<SVGLineElement, RangeLineRow>('line.savedRangeLine')
    .data(savedRows, (d) => d.id)
    .join('line')
    .attr('class', 'savedRangeLine')
    .attr('x1', (d) => Number(d.x1))
    .attr('x2', (d) => Number(d.x2))
    .attr('y1', (d) => style.priceLineY(y, Number(d.price)))
    .attr('y2', (d) => style.priceLineY(y, Number(d.price)))
    .attr('stroke', (d) => d.color)
    .attr('stroke-opacity', (d) => d.style.opacity)
    .attr('stroke-width', (d) => d.style.width)
    .attr('stroke-dasharray', (d) => d.style.dash || null);
  drawRangeLineLabels(sg, savedRows, y, margin);

  const savedPriceKeys = new Set(savedRanges.flatMap((r) => [Number(r.high).toFixed(2), Number(r.low).toFixed(2)]));
  const parentRows: RangeLineRow[] = parentOverlays
    .filter((x) => !savedPriceKeys.has(Number(x.price).toFixed(2)))
    .map((x) => {
      const layerName = x.structureLayer || 'WEEKLY';
      const color = x.isGuidedParentContext
        ? style.guidedParentLineColor(layerName)
        : style.structureLayerLineColor(layerName);
      const pStyle = style.overlayLineStyleWithFocus(
        style.savedRangeLineStyle('ACTIVE', { isParentContext: true, isGuidedParentContext: !!x.isGuidedParentContext }),
        !!chartFocusMode,
        x.focusTier || 'parent',
      );
      const span = style.rangeSpanX(zx, x.start, x.end, margin, innerW, { strict: spanStrict });
      if (!span) return null;
      return {
        id: `parent-${x.kind}-${Number(x.price).toFixed(2)}`,
        kind: x.kind,
        price: x.price,
        label: x.label,
        color,
        style: pStyle,
        x1: span.x1,
        x2: span.x2,
      };
    })
    .filter((row): row is RangeLineRow => row !== null);

  const pg = layer.selectAll<SVGGElement, number>('g.parentRangeLines').data([0]).join('g')
    .attr('class', 'parentRangeLines').attr('pointer-events', 'none');
  pg.selectAll<SVGLineElement, RangeLineRow>('line.parentRangeLine')
    .data(parentRows, (d) => d.id)
    .join('line')
    .attr('class', 'parentRangeLine')
    .attr('x1', (d) => Number(d.x1))
    .attr('x2', (d) => Number(d.x2))
    .attr('y1', (d) => style.priceLineY(y, Number(d.price)))
    .attr('y2', (d) => style.priceLineY(y, Number(d.price)))
    .attr('stroke', (d) => d.color)
    .attr('stroke-opacity', (d) => d.style.opacity)
    .attr('stroke-width', (d) => d.style.width)
    .attr('stroke-dasharray', (d) => d.style.dash || null);
  drawRangeLineLabels(pg, parentRows, y, margin);

  let draftRows: RangeLineRow[] = [];
  if (draftRange?.visible) {
    const draftStyle = style.overlayLineStyleWithFocus(style.draftRangeLineStyle(), !!chartFocusMode, 'active', { isDraft: true });
    const draftColor = style.structureLayerLineColor(draftRange.structureLayer);
    const draftSpan = style.rangeSpanX(zx, draftRange.start, draftRange.end, margin, innerW, { strict: spanStrict });
    if (draftSpan) {
      draftRows = [
        { id: 'draft-high', kind: 'high', price: draftRange.high, label: `Draft ${draftRange.structureLayer} RH`, color: draftColor, style: draftStyle, x1: draftSpan.x1, x2: draftSpan.x2 },
        { id: 'draft-low', kind: 'low', price: draftRange.low, label: `Draft ${draftRange.structureLayer} RL`, color: draftColor, style: draftStyle, x1: draftSpan.x1, x2: draftSpan.x2 },
      ];
    }
  }
  const dg = layer.selectAll<SVGGElement, number>('g.draftRangeLines').data([0]).join('g')
    .attr('class', 'draftRangeLines').attr('pointer-events', 'none');
  dg.selectAll<SVGLineElement, RangeLineRow>('line.draftRangeLine')
    .data(draftRows, (d) => d.id)
    .join('line')
    .attr('class', 'draftRangeLine')
    .attr('x1', (d) => Number(d.x1))
    .attr('x2', (d) => Number(d.x2))
    .attr('y1', (d) => style.priceLineY(y, Number(d.price)))
    .attr('y2', (d) => style.priceLineY(y, Number(d.price)))
    .attr('stroke', (d) => d.color)
    .attr('stroke-opacity', (d) => d.style.opacity)
    .attr('stroke-width', (d) => d.style.width)
    .attr('stroke-dasharray', (d) => d.style.dash || null);
  drawRangeLineLabels(dg, draftRows, y, margin);

  const guidedLines: { id: string; x: number; stroke: string; width: number; opacity?: number; dash: string }[] = [];
  if (guidedCursorTimeMs && Number.isFinite(guidedCursorTimeMs)) {
    const cx = style.snapChartStrokePx(zx(new Date(guidedCursorTimeMs)));
    if (Number.isFinite(cx) && cx >= margin.left && cx <= margin.left + innerW) {
      guidedLines.push({ id: 'guided-cursor', x: cx, stroke: '#38bdf8', width: 1.5, dash: '4 4' });
    }
  }
  if (guidedParentEndMs && Number.isFinite(guidedParentEndMs)) {
    const ex = style.snapChartStrokePx(zx(new Date(guidedParentEndMs)));
    if (Number.isFinite(ex) && ex >= margin.left && ex <= margin.left + innerW) {
      guidedLines.push({
        id: 'guided-parent-end',
        x: ex,
        stroke: '#f59e0b',
        width: chartFocusMode ? 1.1 : 1.25,
        opacity: chartFocusMode ? 0.35 : 1,
        dash: '6 3',
      });
    }
  }
  layer.selectAll<SVGLineElement, typeof guidedLines[0]>('line.guidedVLine')
    .data(guidedLines, (d) => d.id)
    .join('line')
    .attr('class', (d) => d.id === 'guided-cursor' ? 'guidedCursorVLine guidedVLine' : 'guidedParentEndVLine guidedVLine')
    .attr('pointer-events', 'none')
    .attr('x1', (d) => d.x)
    .attr('x2', (d) => d.x)
    .attr('y1', margin.top)
    .attr('y2', margin.top + innerH)
    .attr('stroke', (d) => d.stroke)
    .attr('stroke-width', (d) => d.width)
    .attr('stroke-opacity', (d) => d.opacity ?? 1)
    .attr('stroke-dasharray', (d) => d.dash);

  if (replayCutMs && Number.isFinite(replayCutMs) && replayCutTime) {
    const replayCandle = renderData.find((d) => style.candleTimeMs(d.time) === replayCutMs) || renderData[renderData.length - 1];
    const cutDate = style.candleTimeDate(replayCutTime);
    const showHighlight = replayCandle && Number.isFinite(cutDate.getTime()) && cutDate >= domain[0] && cutDate <= domain[1];
    layer.selectAll<SVGRectElement, number>('rect.replayCandleHighlight')
      .data(showHighlight ? [0] : [])
      .join('rect')
      .attr('class', 'replayCandleHighlight')
      .attr('pointer-events', 'none')
      .attr('x', () => {
        const cutX = style.snapChartStrokePx(zx(cutDate));
        return style.snapChartPx(cutX - candleW / 2 - 3);
      })
      .attr('y', () => style.snapChartPx(y(replayCandle!.high) - 3))
      .attr('width', candleW + 6)
      .attr('height', () => Math.max(4, style.snapChartPx(y(replayCandle!.low)) - style.snapChartPx(y(replayCandle!.high)) + 6))
      .attr('fill', 'rgba(0,212,170,.08)')
      .attr('stroke', '#00d4aa')
      .attr('stroke-width', 2);
  } else {
    layer.selectAll('rect.replayCandleHighlight').remove();
  }

  if (selectedCandleTime) {
    const selectedDate = style.candleTimeDate(selectedCandleTime);
    const isReplayBar = !!(replayCutTime && selectedCandleTime === replayCutTime);
    const show = !isReplayBar && selectedDate >= domain[0] && selectedDate <= domain[1];
    layer.selectAll<SVGCircleElement, number>('circle.selectedCandleDot')
      .data(show ? [0] : [])
      .join('circle')
      .attr('class', 'selectedCandleDot')
      .attr('pointer-events', 'none')
      .attr('cx', zx(selectedDate))
      .attr('cy', Number.isFinite(Number(selectedCandlePrice)) ? y(Number(selectedCandlePrice)) : margin.top + innerH / 2)
      .attr('r', 5)
      .attr('fill', '#ffbf2f')
      .attr('stroke', '#020308')
      .attr('stroke-width', 2);
  } else {
    layer.selectAll('circle.selectedCandleDot').remove();
  }
}

function draftPointColor(kind: MappingPointKind): string {
  if (kind === 'zone') return '#fbbf24';
  if (kind === 'anchor') return '#a78bfa';
  return '#38bdf8';
}

function draftPointLabel(kind: MappingPointKind): string {
  if (kind === 'zone') return 'Z';
  if (kind === 'anchor') return 'A';
  return 'P';
}

export type RenderDraftPointsArgs = {
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>;
  viewport: ChartViewportState;
  points: MappingPoint[];
  timeframe: string;
  style: ChartRenderStyleFns;
};

/** Dedicated layer for ephemeral mapping draft markers (pivots/zones). */
export function renderDraftPointsLayer(args: RenderDraftPointsArgs): void {
  const { svg, viewport, points, timeframe, style } = args;
  const { zx, y, domain } = viewport;
  let layer = svg.select<SVGGElement>(`g.${CHART_LAYER_DRAFT_POINTS}`);
  if (layer.empty()) {
    const uiLayer = svg.select(`g.${CHART_LAYER_UI}`);
    layer = uiLayer.empty()
      ? svg.append('g').attr('class', CHART_LAYER_DRAFT_POINTS)
      : svg.insert('g', `g.${CHART_LAYER_UI}`).attr('class', CHART_LAYER_DRAFT_POINTS);
  }

  const visible = points.filter((p) => {
    if (!p.time || !Number.isFinite(p.price)) return false;
    const t = style.candleTimeDate(p.time);
    return Number.isFinite(t.getTime()) && t >= domain[0] && t <= domain[1];
  });

  const root = layer.selectAll<SVGGElement, number>('g.mappingDraftPoints').data([0]).join('g')
    .attr('class', 'mappingDraftPoints')
    .attr('pointer-events', 'none');

  const nodes = root.selectAll<SVGGElement, MappingPoint>('g.mappingDraftPoint').data(visible, (d) => d.id).join(
    (enter) => {
      const g = enter.append('g').attr('class', 'mappingDraftPoint');
      g.append('line')
        .attr('class', 'mappingDraftPointStem')
        .attr('x1', 0).attr('x2', 14)
        .attr('y1', 0).attr('y2', 0)
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '3 3');
      g.append('circle')
        .attr('class', 'mappingDraftPointDot')
        .attr('stroke', '#020617')
        .attr('stroke-width', 1.5);
      g.append('text')
        .attr('class', 'mappingDraftPointLabel')
        .attr('x', 7)
        .attr('y', -5)
        .attr('fill', '#f8fafc')
        .attr('font-size', 8)
        .attr('font-weight', 800);
      g.append('title');
      return g;
    },
    (update) => update,
    (exit) => exit.remove(),
  );

  nodes.attr('transform', (d) => {
    const x = zx(style.candleTimeDate(d.time));
    const py = style.priceLineY(y, d.price);
    return `translate(${x},${py})`;
  });
  nodes.select('.mappingDraftPointStem').attr('stroke', (d) => draftPointColor(d.kind));
  nodes.select('.mappingDraftPointDot')
    .attr('r', (d) => (d.kind === 'zone' ? 3.5 : 4))
    .attr('fill', (d) => draftPointColor(d.kind));
  nodes.select('.mappingDraftPointLabel').text((d) => d.label || draftPointLabel(d.kind));
  nodes.select('title').text((d) => `${d.kind}${d.label ? ` · ${d.label}` : ''}\n${style.shortTime(d.time, timeframe)} · ${d.price.toFixed(2)}`);
}

export function clearChartEmptyMessage(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
) {
  svg.selectAll('text.chart-empty').remove();
}

export function renderChartEmptyState(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  metrics: ChartSurfaceMetrics,
  message: string,
  shellReady: { current: boolean },
) {
  ensureChartShell(svg, metrics, shellReady);
  svg.select(`g.${CHART_LAYER_CANDLES}`).selectAll('*').remove();
  svg.select(`g.${CHART_LAYER_OVERLAYS}`).selectAll('*').remove();
  svg.select(`g.${CHART_LAYER_DRAFT_POINTS}`).selectAll('*').remove();
  svg.selectAll('text.chart-empty')
    .data([message])
    .join('text')
    .attr('class', 'chart-empty')
    .attr('x', metrics.width / 2)
    .attr('y', metrics.height / 2)
    .attr('text-anchor', 'middle')
    .attr('fill', '#94a3b8')
    .attr('font-size', message.length > 40 ? 18 : 22)
    .text((d) => d);
}
