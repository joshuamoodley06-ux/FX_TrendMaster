import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  createSeriesMarkers,
  createChart,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts';
import {
  adaptCandlesForTradingView,
  computeReplayAnchorLogicalRange,
} from './candleAdapter';
import {
  buildTradingViewSelectedCandle,
  resolveTradingViewSelectionAtX,
  selectionMarkerFromSelectedCandle,
  type TradingViewSelectionResolve,
} from './selectedCandleBridge';
import { tradingViewDarkTheme } from './tradingViewTheme';
import type { FxtmCandleRow, TradingViewChartMode, TradingViewFitRequest, TradingViewOverlaySet, TradingViewRangeLine, TradingViewSelectedCandle, TradingViewSelectionDebugEvent } from './types';

type TradingViewChartProps = {
  candles: FxtmCandleRow[];
  timeframe: string;
  chartMode?: TradingViewChartMode;
  revision?: number;
  overlays?: TradingViewOverlaySet;
  fitRequest?: TradingViewFitRequest | null;
  symbol: string;
  sourceTimeframe?: string;
  selectedCandle?: TradingViewSelectedCandle | null;
  selectionBridgeEnabled?: boolean;
  onCrosshairCandle?: (candle: TradingViewSelectedCandle | null) => void;
  onCandleClick?: (candle: TradingViewSelectedCandle) => void;
  onSelectionDebug?: (event: TradingViewSelectionDebugEvent) => void;
  onStats?: (stats: { rendered: number; dropped: number }) => void;
};

function lineStyleValue(style: TradingViewRangeLine['lineStyle']): LineStyle {
  if (style === 'dashed') return LineStyle.Dashed;
  if (style === 'dotted') return LineStyle.Dotted;
  return LineStyle.Solid;
}

function timeDebugKey(time: Time | null | undefined): string {
  if (time == null) return '';
  if (typeof time === 'number' || typeof time === 'string') return String(time);
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
}

type ActivationStart = {
  x: number;
  y: number;
  timeMs: number;
  pointerType: string;
};

function pointerSummary(event: MouseEvent | PointerEvent | TouchEvent, source: string): string {
  if ('changedTouches' in event) {
    const touch = event.changedTouches[0] || event.touches[0];
    return `${source}:${event.type}:x=${Math.round(touch?.clientX ?? -1)}:y=${Math.round(touch?.clientY ?? -1)}`;
  }
  const pointerType = 'pointerType' in event ? `:${event.pointerType}` : '';
  return `${source}:${event.type}${pointerType}:x=${Math.round(event.clientX)}:y=${Math.round(event.clientY)}`;
}

function clientXFromActivation(event: MouseEvent | PointerEvent | TouchEvent): number | null {
  if ('changedTouches' in event) {
    const touch = event.changedTouches[0] || event.touches[0];
    return touch ? touch.clientX : null;
  }
  return event.clientX;
}

function clientPointFromActivation(event: MouseEvent | PointerEvent | TouchEvent): { x: number; y: number } | null {
  if ('changedTouches' in event) {
    const touch = event.changedTouches[0] || event.touches[0];
    return touch ? { x: touch.clientX, y: touch.clientY } : null;
  }
  return { x: event.clientX, y: event.clientY };
}

export function TradingViewChart({
  candles,
  timeframe,
  chartMode = 'latest',
  revision,
  overlays,
  fitRequest,
  symbol,
  sourceTimeframe,
  selectedCandle,
  selectionBridgeEnabled = false,
  onCrosshairCandle,
  onCandleClick,
  onSelectionDebug,
  onStats,
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const captureLayerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const adaptedRef = useRef<ReturnType<typeof adaptCandlesForTradingView>>({ bars: [], dropped: 0 });
  const fitRequestRef = useRef<TradingViewFitRequest | null>(fitRequest || null);
  const chartModeRef = useRef<TradingViewChartMode>(chartMode);
  const lastAutoFitTimeframeRef = useRef<string | null>(null);
  const lastRenderedBarCountRef = useRef(0);
  const lastFitTokenRef = useRef<number | null>(null);
  const activationStartRef = useRef<ActivationStart | null>(null);
  const lastTouchSelectionMsRef = useRef(0);
  const selectionBridgeRef = useRef({
    candles,
    timeframe,
    symbol,
    sourceTimeframe,
    enabled: selectionBridgeEnabled,
    onCrosshairCandle,
    onCandleClick,
    onSelectionDebug,
  });
  const [chartReady, setChartReady] = useState(false);
  const [fitDebugStatus, setFitDebugStatus] = useState('none');

  const adapted = useMemo(
    () => adaptCandlesForTradingView(candles, timeframe),
    [candles, timeframe, revision],
  );
  adaptedRef.current = adapted;
  fitRequestRef.current = fitRequest || null;
  chartModeRef.current = chartMode;
  selectionBridgeRef.current = {
    candles,
    timeframe,
    symbol,
    sourceTimeframe,
    enabled: selectionBridgeEnabled,
    onCrosshairCandle,
    onCandleClick,
    onSelectionDebug,
  };

  const selectedFromTime = (tvTime: Time | null | undefined): TradingViewSelectedCandle | null => {
    const latest = selectionBridgeRef.current;
    if (!latest.enabled || !tvTime) return null;
    return buildTradingViewSelectedCandle({
      symbol: latest.symbol,
      chartTimeframe: latest.timeframe,
      sourceTimeframe: latest.sourceTimeframe,
      candles: latest.candles,
      tvTime,
    });
  };

  const selectedFromClientX = (clientX: number): TradingViewSelectionResolve => {
    const chart = chartRef.current;
    const container = containerRef.current;
    const latest = selectionBridgeRef.current;
    if (!chart || !container || !latest.enabled) {
      return { selected: null, rawTvTime: null, normalizedTime: '' };
    }
    const x = clientX - container.getBoundingClientRect().left;
    const timeScale = chart.timeScale();
    return resolveTradingViewSelectionAtX({
      x,
      symbol: latest.symbol,
      chartTimeframe: latest.timeframe,
      sourceTimeframe: latest.sourceTimeframe,
      candles: latest.candles,
      displayedBarCount: adaptedRef.current.bars.length,
      timeScale: {
        coordinateToTime: (probeX) => timeScale.coordinateToTime(probeX),
        coordinateToLogical: (probeX) => timeScale.coordinateToLogical(probeX),
        timeToCoordinate: (time) => timeScale.timeToCoordinate(time),
        logicalToCoordinate: (logical) => timeScale.logicalToCoordinate(logical),
      },
    });
  };

  const reportSelectionClick = (args: TradingViewSelectionResolve) => {
    selectionBridgeRef.current.onSelectionDebug?.({
      clickReceived: true,
      rawTvTime: timeDebugKey(args.rawTvTime),
      normalizedClickTime: args.normalizedTime,
      displayCandleCount: adaptedRef.current.bars.length,
      matchedCandle: !!args.selected,
      matchedCandleTime: args.selected?.time || '',
    });
  };

  const reportPointerState = (event: MouseEvent | PointerEvent | TouchEvent, source: string, pointerOverChart = true) => {
    const container = containerRef.current;
    const layer = captureLayerRef.current;
    selectionBridgeRef.current.onSelectionDebug?.({
      pointerOverChart,
      chartContainerPointerEvents: container ? getComputedStyle(container).pointerEvents : 'missing',
      overlayPointerEvents: layer ? getComputedStyle(layer).pointerEvents : 'missing',
      lastClickEventObject: pointerSummary(event, source),
    });
  };

  const handleActivationEvent = (event: MouseEvent | PointerEvent | TouchEvent, source: string) => {
    reportPointerState(event, source);
    const clientX = clientXFromActivation(event);
    const resolved = clientX == null
      ? { selected: null, rawTvTime: null, normalizedTime: '' }
      : selectedFromClientX(clientX);
    reportSelectionClick(resolved);
    if (resolved.selected) selectionBridgeRef.current.onCandleClick?.(resolved.selected);
  };

  const rememberActivationStart = (event: MouseEvent | PointerEvent | TouchEvent, source: string) => {
    reportPointerState(event, source);
    const point = clientPointFromActivation(event);
    if (!point) return;
    const pointerType = 'pointerType' in event ? String(event.pointerType || 'mouse') : ('changedTouches' in event ? 'touch' : 'mouse');
    activationStartRef.current = {
      x: point.x,
      y: point.y,
      timeMs: Date.now(),
      pointerType,
    };
  };

  const commitTapIfStationary = (event: MouseEvent | PointerEvent | TouchEvent, source: string) => {
    reportPointerState(event, source);
    const start = activationStartRef.current;
    const point = clientPointFromActivation(event);
    activationStartRef.current = null;
    if (!start || !point) return;
    const elapsed = Date.now() - start.timeMs;
    const distance = Math.hypot(point.x - start.x, point.y - start.y);
    if (distance > 8 || elapsed > 800) return;
    if (start.pointerType === 'touch' && Date.now() - lastTouchSelectionMsRef.current < 350) return;
    if (start.pointerType === 'touch') lastTouchSelectionMsRef.current = Date.now();
    handleActivationEvent(event, source);
  };

  const hasPendingFitRequest = () => {
    const request = fitRequestRef.current;
    return !!(request?.token && lastFitTokenRef.current !== request.token);
  };

  const updateFitDebugStatus = (next: string) => {
    setFitDebugStatus((prev) => (prev === next ? prev : next));
  };

  const shouldAutoFitContent = () => chartModeRef.current !== 'replay';

  const logicalIndexForTime = (time: Time): number | null => {
    const targetKey = timeDebugKey(time);
    const index = adaptedRef.current.bars.findIndex((bar) => timeDebugKey(bar.time) === targetKey);
    return index >= 0 ? index : null;
  };

  const isReplayTargetVisible = (target: Time, edgePx = 48): boolean => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container) return false;
    const coord = chart.timeScale().timeToCoordinate(target);
    if (coord == null) return false;
    const width = container.getBoundingClientRect().width;
    return coord >= edgePx && coord <= width - edgePx;
  };

  const applyReplayAnchorFit = (request: TradingViewFitRequest): string => {
    const chart = chartRef.current;
    if (!chart) return `pending:${request.token}:no-chart`;

    const timeScale = chart.timeScale();
    const target = request.target;
    if (target && isReplayTargetVisible(target)) {
      return `skipped:${request.token}:cursor-visible`;
    }

    const bars = adaptedRef.current.bars;
    const cursorLogical = target ? logicalIndexForTime(target) : null;
    const decision = computeReplayAnchorLogicalRange({
      cursorLogical: cursorLogical ?? NaN,
      visible: timeScale.getVisibleLogicalRange(),
      barCount: bars.length,
    });

    if (decision.action === 'skip') {
      return `skipped:${request.token}:cursor-visible`;
    }
    if (decision.action === 'initial') {
      if (request.from && request.to) {
        timeScale.setVisibleRange({ from: request.from, to: request.to });
        return `initial:${request.token}:${timeDebugKey(request.from)}:${timeDebugKey(request.to)}`;
      }
      return `skipped:${request.token}:no-range`;
    }

    timeScale.setVisibleLogicalRange(decision.range);
    return `panned:${request.token}:${decision.range.from.toFixed(2)}:${decision.range.to.toFixed(2)}`;
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      ...tradingViewDarkTheme,
      autoSize: true,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#86efac',
      wickDownColor: '#fca5a5',
    });
    chartRef.current = chart;
    seriesRef.current = series;
    markersRef.current = createSeriesMarkers(series, [], { zOrder: 'top' });
    setChartReady(true);

    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const selected = selectedFromTime(param.time);
      selectionBridgeRef.current.onSelectionDebug?.({
        crosshairReceived: true,
        rawTvTime: timeDebugKey(param.time),
        normalizedClickTime: timeDebugKey(param.time),
        displayCandleCount: adaptedRef.current.bars.length,
      });
      selectionBridgeRef.current.onCrosshairCandle?.(selected);
    };
    const handleClick = (param: MouseEventParams<Time>) => {
      const selected = selectedFromTime(param.time);
      reportSelectionClick({
        selected,
        rawTvTime: param.time || null,
        normalizedTime: timeDebugKey(param.time),
      });
      if (selected) selectionBridgeRef.current.onCandleClick?.(selected);
    };
    const handleSurfaceMouseMove = (event: MouseEvent) => {
      const resolved = selectedFromClientX(event.clientX);
      selectionBridgeRef.current.onCrosshairCandle?.(resolved.selected);
    };
    const handleSurfaceClick = (event: MouseEvent) => handleActivationEvent(event, 'chart-container-click');
    const handleSurfacePointerDown = (event: PointerEvent) => rememberActivationStart(event, 'chart-container-pointerdown');
    const handleSurfacePointerUp = (event: PointerEvent) => {
      if (event.pointerType === 'mouse') return;
      commitTapIfStationary(event, 'chart-container-pointerup');
    };
    const handleSurfaceTouchStart = (event: TouchEvent) => rememberActivationStart(event, 'chart-container-touchstart');
    const handleSurfaceTouchEnd = (event: TouchEvent) => commitTapIfStationary(event, 'chart-container-touchend');
    chart.subscribeCrosshairMove(handleCrosshairMove);
    chart.subscribeClick(handleClick);
    selectionBridgeRef.current.onSelectionDebug?.({
      clickHandlerAttached: true,
      chartContainerPointerEvents: getComputedStyle(container).pointerEvents,
      overlayPointerEvents: captureLayerRef.current ? getComputedStyle(captureLayerRef.current).pointerEvents : 'missing',
    });
    container.addEventListener('mousemove', handleSurfaceMouseMove, true);
    container.addEventListener('click', handleSurfaceClick, true);
    container.addEventListener('pointerdown', handleSurfacePointerDown, true);
    container.addEventListener('pointerup', handleSurfacePointerUp, true);
    container.addEventListener('touchstart', handleSurfaceTouchStart, true);
    container.addEventListener('touchend', handleSurfaceTouchEnd, true);

    const resizeObserver = new ResizeObserver(() => {
      if (!shouldAutoFitContent()) return;
      if (!fitRequestRef.current?.token && !hasPendingFitRequest()) chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.unsubscribeClick(handleClick);
      container.removeEventListener('mousemove', handleSurfaceMouseMove, true);
      container.removeEventListener('click', handleSurfaceClick, true);
      container.removeEventListener('pointerdown', handleSurfacePointerDown, true);
      container.removeEventListener('pointerup', handleSurfacePointerUp, true);
      container.removeEventListener('touchstart', handleSurfaceTouchStart, true);
      container.removeEventListener('touchend', handleSurfaceTouchEnd, true);
      resizeObserver.disconnect();
      for (const line of priceLinesRef.current) series.removePriceLine(line);
      priceLinesRef.current = [];
      markersRef.current?.detach();
      markersRef.current = null;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      setChartReady(false);
    };
  }, []);

  useEffect(() => {
    if (!chartReady) return;
    seriesRef.current?.setData(adapted.bars);
    const prevBarCount = lastRenderedBarCountRef.current;
    const barCountShrunk = prevBarCount > 0 && adapted.bars.length > 0 && adapted.bars.length < prevBarCount;
    lastRenderedBarCountRef.current = adapted.bars.length;
    const firstTime = adapted.bars[0]?.time;
    const lastTime = adapted.bars.at(-1)?.time;
    const autoFitKey = chartMode === 'latest'
      ? `${chartMode}:${timeframe}:${timeDebugKey(firstTime)}:${timeDebugKey(lastTime)}`
      : `${chartMode}:${timeframe}`;
    const autoFitKeyChanged = lastAutoFitTimeframeRef.current !== autoFitKey;
    const skipReplayShrinkFit = chartMode === 'replay' && barCountShrunk && !autoFitKeyChanged;
    if (
      adapted.bars.length
      && chartMode !== 'hierarchy'
      && chartMode !== 'replay'
      && autoFitKeyChanged
      && !hasPendingFitRequest()
      && !skipReplayShrinkFit
    ) {
      chartRef.current?.timeScale().fitContent();
      lastAutoFitTimeframeRef.current = autoFitKey;
    }
    onStats?.({ rendered: adapted.bars.length, dropped: adapted.dropped });
  }, [adapted, chartMode, chartReady, fitRequest, onStats, timeframe]);

  useEffect(() => {
    if (!chartReady || !seriesRef.current) return;
    for (const line of priceLinesRef.current) {
      seriesRef.current.removePriceLine(line);
    }
    priceLinesRef.current = [];
    for (const line of overlays?.priceLines || []) {
      priceLinesRef.current.push(seriesRef.current.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: line.lineWidth as any,
        lineStyle: lineStyleValue(line.lineStyle),
        axisLabelVisible: true,
        title: line.label,
      }));
    }
    const selectionMarker = selectionMarkerFromSelectedCandle(selectedCandle || null);
    const nextMarkers = selectionMarker ? [...(overlays?.markers || []), selectionMarker] : (overlays?.markers || []);
    markersRef.current?.setMarkers(nextMarkers);
    selectionBridgeRef.current.onSelectionDebug?.({
      markerCount: nextMarkers.length,
      selMarkerPresent: !!selectionMarker,
    });
  }, [chartReady, overlays, selectedCandle]);

  useEffect(() => {
    if (!chartReady || !chartRef.current || !fitRequest) return;
    if (!fitRequest.token || lastFitTokenRef.current === fitRequest.token) return;
    if (!adapted.bars.length) {
      updateFitDebugStatus(`pending:${fitRequest.token}:no-bars`);
      return;
    }

    if (chartMode === 'replay') {
      const status = applyReplayAnchorFit(fitRequest);
      lastFitTokenRef.current = fitRequest.token;
      updateFitDebugStatus(status);
      return;
    }

    if (fitRequest.from && fitRequest.to) {
      chartRef.current.timeScale().setVisibleRange({ from: fitRequest.from, to: fitRequest.to });
      lastFitTokenRef.current = fitRequest.token;
      updateFitDebugStatus(`applied:${fitRequest.token}:${timeDebugKey(fitRequest.from)}:${timeDebugKey(fitRequest.to)}`);
    }
  }, [adapted.bars.length, chartMode, chartReady, fitRequest]);

  useEffect(() => {
    const layer = captureLayerRef.current;
    if (!layer || !selectionBridgeEnabled) return;
    const handleMove = (event: MouseEvent) => {
      reportPointerState(event, 'capture-layer-move');
      const resolved = selectedFromClientX(event.clientX);
      selectionBridgeRef.current.onCrosshairCandle?.(resolved.selected);
    };
    const handleClick = (event: MouseEvent) => handleActivationEvent(event, 'capture-layer-click');
    const handlePointerDown = (event: PointerEvent) => rememberActivationStart(event, 'capture-layer-pointerdown');
    const handlePointerUp = (event: PointerEvent) => {
      if (event.pointerType === 'mouse') return;
      commitTapIfStationary(event, 'capture-layer-pointerup');
    };
    const handleTouchStart = (event: TouchEvent) => rememberActivationStart(event, 'capture-layer-touchstart');
    const handleTouchEnd = (event: TouchEvent) => commitTapIfStationary(event, 'capture-layer-touchend');
    const handleEnter = (event: MouseEvent | PointerEvent) => reportPointerState(event, 'capture-layer-enter', true);
    const handleLeave = (event: MouseEvent | PointerEvent) => reportPointerState(event, 'capture-layer-leave', false);
    layer.addEventListener('mousemove', handleMove);
    layer.addEventListener('pointermove', handleMove);
    layer.addEventListener('mouseenter', handleEnter);
    layer.addEventListener('pointerenter', handleEnter);
    layer.addEventListener('mouseleave', handleLeave);
    layer.addEventListener('pointerleave', handleLeave);
    layer.addEventListener('mousedown', handleClick);
    layer.addEventListener('pointerdown', handlePointerDown);
    layer.addEventListener('pointerup', handlePointerUp);
    layer.addEventListener('touchstart', handleTouchStart);
    layer.addEventListener('touchend', handleTouchEnd);
    layer.addEventListener('click', handleClick);
    return () => {
      layer.removeEventListener('mousemove', handleMove);
      layer.removeEventListener('pointermove', handleMove);
      layer.removeEventListener('mouseenter', handleEnter);
      layer.removeEventListener('pointerenter', handleEnter);
      layer.removeEventListener('mouseleave', handleLeave);
      layer.removeEventListener('pointerleave', handleLeave);
      layer.removeEventListener('mousedown', handleClick);
      layer.removeEventListener('pointerdown', handlePointerDown);
      layer.removeEventListener('pointerup', handlePointerUp);
      layer.removeEventListener('touchstart', handleTouchStart);
      layer.removeEventListener('touchend', handleTouchEnd);
      layer.removeEventListener('click', handleClick);
    };
  }, [selectionBridgeEnabled, chartReady]);

  return (
    <div
      className="tradingViewChartFrame"
      aria-label="TradingView Live View candle chart"
      data-chart-mode={chartMode}
      data-fit-status={fitDebugStatus}
      data-fit-token={fitRequest?.token || ''}
      data-fit-from={timeDebugKey(fitRequest?.from)}
      data-fit-to={timeDebugKey(fitRequest?.to)}
      data-selected-marker={selectedCandle ? 'yellow-sel' : ''}
      data-selected-marker-color={selectedCandle ? '#facc15' : ''}
    >
      <div ref={containerRef} className="tradingViewChartCanvas" />
      {selectionBridgeEnabled && (
        <div
          ref={captureLayerRef}
          className="tradingViewSelectionCaptureLayer"
          aria-label="TradingView read-only candle selection layer"
        />
      )}
    </div>
  );
}
