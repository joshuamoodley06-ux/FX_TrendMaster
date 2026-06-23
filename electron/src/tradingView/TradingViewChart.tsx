import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts';
import { adaptCandlesForTradingView } from './candleAdapter';
import { tradingViewDarkTheme } from './tradingViewTheme';
import type { FxtmCandleRow } from './types';

type TradingViewChartProps = {
  candles: FxtmCandleRow[];
  timeframe: string;
  revision?: number;
  onStats?: (stats: { rendered: number; dropped: number }) => void;
};

export function TradingViewChart({ candles, timeframe, revision, onStats }: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick', Time> | null>(null);
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
    setChartReady(true);

    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      setChartReady(false);
    };
  }, []);

  useEffect(() => {
    if (!chartReady) return;
    seriesRef.current?.setData(adapted.bars);
    chartRef.current?.timeScale().fitContent();
    onStats?.({ rendered: adapted.bars.length, dropped: adapted.dropped });
  }, [adapted, chartReady, onStats]);

  return <div ref={containerRef} className="tradingViewChartCanvas" aria-label="TradingView Live View candle chart" />;
}
