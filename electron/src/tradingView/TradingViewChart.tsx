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
  type Time,
} from 'lightweight-charts';
import { adaptCandlesForTradingView } from './candleAdapter';
import { tradingViewDarkTheme } from './tradingViewTheme';
import type { FxtmCandleRow, TradingViewFitRequest, TradingViewOverlaySet, TradingViewRangeLine } from './types';

type TradingViewChartProps = {
  candles: FxtmCandleRow[];
  timeframe: string;
  revision?: number;
  overlays?: TradingViewOverlaySet;
  fitRequest?: TradingViewFitRequest | null;
  onStats?: (stats: { rendered: number; dropped: number }) => void;
};

function lineStyleValue(style: TradingViewRangeLine['lineStyle']): LineStyle {
  if (style === 'dashed') return LineStyle.Dashed;
  if (style === 'dotted') return LineStyle.Dotted;
  return LineStyle.Solid;
}

export function TradingViewChart({ candles, timeframe, revision, overlays, fitRequest, onStats }: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lastAutoFitTimeframeRef = useRef<string | null>(null);
  const lastFitTokenRef = useRef<number | null>(null);
  const [chartReady, setChartReady] = useState(false);

  const adapted = useMemo(
    () => adaptCandlesForTradingView(candles, timeframe),
    [candles, timeframe, revision],
  );

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

    const resizeObserver = new ResizeObserver(() => {
      if (lastFitTokenRef.current == null) chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
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
    markersRef.current?.setMarkers(overlays?.markers || []);
  }, [chartReady, overlays]);

  useEffect(() => {
    if (!chartReady || !chartRef.current || !fitRequest) return;
    if (!fitRequest.token || lastFitTokenRef.current === fitRequest.token) return;
    if (fitRequest.from && fitRequest.to) {
      chartRef.current.timeScale().setVisibleRange({ from: fitRequest.from, to: fitRequest.to });
      lastFitTokenRef.current = fitRequest.token;
    }
  }, [chartReady, fitRequest]);

  return <div ref={containerRef} className="tradingViewChartCanvas" aria-label="TradingView Live View candle chart" />;
}
