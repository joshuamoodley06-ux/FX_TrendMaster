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
import { adaptCandlesForTradingView } from './candleAdapter';
import {
  buildTradingViewSelectedCandle,
  buildTradingViewSelectedCandleFromBarIndex,
  selectionMarkerFromSelectedCandle,
} from './selectedCandleBridge';
import { tradingViewDarkTheme } from './tradingViewTheme';
import type { FxtmCandleRow, TradingViewFitRequest, TradingViewOverlaySet, TradingViewRangeLine, TradingViewSelectedCandle } from './types';

type TradingViewChartProps = {
  candles: FxtmCandleRow[];
  timeframe: string;
  revision?: number;
  overlays?: TradingViewOverlaySet;
  fitRequest?: TradingViewFitRequest | null;
  symbol: string;
  sourceTimeframe?: string;
  selectedCandle?: TradingViewSelectedCandle | null;
  selectionBridgeEnabled?: boolean;
  onCrosshairCandle?: (candle: TradingViewSelectedCandle | null) => void;
  onCandleClick?: (candle: TradingViewSelectedCandle) => void;
  onStats?: (stats: { rendered: number; dropped: number }) => void;
};

function lineStyleValue(style: TradingViewRangeLine['lineStyle']): LineStyle {
  if (style === 'dashed') return LineStyle.Dashed;
  if (style === 'dotted') return LineStyle.Dotted;
  return LineStyle.Solid;
}

export function TradingViewChart({
  candles,
  timeframe,
  revision,
  overlays,
  fitRequest,
  symbol,
  sourceTimeframe,
  selectedCandle,
  selectionBridgeEnabled = false,
  onCrosshairCandle,
  onCandleClick,
  onStats,
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const captureLayerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const adaptedRef = useRef<ReturnType<typeof adaptCandlesForTradingView>>({ bars: [], dropped: 0 });
  const lastAutoFitTimeframeRef = useRef<string | null>(null);
  const lastFitTokenRef = useRef<number | null>(null);
  const selectionBridgeRef = useRef({
    candles,
    timeframe,
    symbol,
    sourceTimeframe,
    enabled: selectionBridgeEnabled,
    onCrosshairCandle,
    onCandleClick,
  });
  const [chartReady, setChartReady] = useState(false);

  const adapted = useMemo(
    () => adaptCandlesForTradingView(candles, timeframe),
    [candles, timeframe, revision],
  );
  adaptedRef.current = adapted;
  selectionBridgeRef.current = {
    candles,
    timeframe,
    symbol,
    sourceTimeframe,
    enabled: selectionBridgeEnabled,
    onCrosshairCandle,
    onCandleClick,
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

  const selectedFromClientX = (clientX: number): TradingViewSelectedCandle | null => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container) return null;
    const bounds = container.getBoundingClientRect();
    const x = clientX - bounds.left;
    const tvTime = chart.timeScale().coordinateToTime(x);
    const selected = selectedFromTime(tvTime);
    if (selected) return selected;

    const logical = chart.timeScale().coordinateToLogical(x);
    const latest = selectionBridgeRef.current;
    if (!latest.enabled) return null;
    if (logical != null) {
      const rounded = Math.round(Number(logical));
      if (Math.abs(Number(logical) - rounded) <= 0.5) {
        const byLogical = buildTradingViewSelectedCandleFromBarIndex({
          symbol: latest.symbol,
          chartTimeframe: latest.timeframe,
          sourceTimeframe: latest.sourceTimeframe,
          candles: latest.candles,
          barIndex: rounded,
        });
        if (byLogical) return byLogical;
      }
    }

    const latestAdapted = adaptedRef.current;
    if (!latestAdapted.bars.length || bounds.width <= 0) return null;
    const slot = Math.max(0, Math.min(latestAdapted.bars.length - 1, Math.round((x / bounds.width) * (latestAdapted.bars.length - 1))));
    return buildTradingViewSelectedCandle({
      symbol: latest.symbol,
      chartTimeframe: latest.timeframe,
      sourceTimeframe: latest.sourceTimeframe,
      candles: latest.candles,
      tvTime: latestAdapted.bars[slot].time,
    });
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
      selectionBridgeRef.current.onCrosshairCandle?.(selected);
    };
    const handleClick = (param: MouseEventParams<Time>) => {
      const selected = selectedFromTime(param.time);
      if (selected) selectionBridgeRef.current.onCandleClick?.(selected);
    };
    const handleSurfaceMouseMove = (event: MouseEvent) => {
      const selected = selectedFromClientX(event.clientX);
      selectionBridgeRef.current.onCrosshairCandle?.(selected);
    };
    const handleSurfaceClick = (event: MouseEvent) => {
      const selected = selectedFromClientX(event.clientX);
      if (selected) selectionBridgeRef.current.onCandleClick?.(selected);
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);
    chart.subscribeClick(handleClick);
    container.addEventListener('mousemove', handleSurfaceMouseMove, true);
    container.addEventListener('click', handleSurfaceClick, true);

    const resizeObserver = new ResizeObserver(() => {
      if (lastFitTokenRef.current == null) chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.unsubscribeClick(handleClick);
      container.removeEventListener('mousemove', handleSurfaceMouseMove, true);
      container.removeEventListener('click', handleSurfaceClick, true);
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
    if (adapted.bars.length && lastAutoFitTimeframeRef.current !== timeframe && lastFitTokenRef.current == null) {
      chartRef.current?.timeScale().fitContent();
      lastAutoFitTimeframeRef.current = timeframe;
    }
    onStats?.({ rendered: adapted.bars.length, dropped: adapted.dropped });
  }, [adapted, chartReady, onStats, timeframe]);

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
    markersRef.current?.setMarkers(selectionMarker ? [...(overlays?.markers || []), selectionMarker] : (overlays?.markers || []));
  }, [chartReady, overlays, selectedCandle]);

  useEffect(() => {
    if (!chartReady || !chartRef.current || !fitRequest) return;
    if (!fitRequest.token || lastFitTokenRef.current === fitRequest.token) return;
    if (fitRequest.from && fitRequest.to) {
      chartRef.current.timeScale().setVisibleRange({ from: fitRequest.from, to: fitRequest.to });
      lastFitTokenRef.current = fitRequest.token;
    }
  }, [chartReady, fitRequest]);

  useEffect(() => {
    const layer = captureLayerRef.current;
    if (!layer || !selectionBridgeEnabled) return;
    const handleMove = (event: MouseEvent) => {
      const selected = selectedFromClientX(event.clientX);
      selectionBridgeRef.current.onCrosshairCandle?.(selected);
    };
    const handleClick = (event: MouseEvent) => {
      const selected = selectedFromClientX(event.clientX);
      if (selected) selectionBridgeRef.current.onCandleClick?.(selected);
    };
    layer.addEventListener('mousemove', handleMove);
    layer.addEventListener('mousedown', handleClick);
    layer.addEventListener('click', handleClick);
    return () => {
      layer.removeEventListener('mousemove', handleMove);
      layer.removeEventListener('mousedown', handleClick);
      layer.removeEventListener('click', handleClick);
    };
  }, [selectionBridgeEnabled, chartReady]);

  return (
    <div className="tradingViewChartFrame" aria-label="TradingView Live View candle chart">
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
