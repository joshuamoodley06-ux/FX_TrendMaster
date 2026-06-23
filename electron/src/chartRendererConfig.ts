import type { ChartRendererMode } from './tradingView/types';

export const CHART_RENDERER_STORAGE_KEY = 'fx_tm_chart_renderer_v1';
export const DEFAULT_CHART_RENDERER: ChartRendererMode = 'd3';

export function normalizeChartRendererMode(value: unknown): ChartRendererMode {
  return value === 'tradingview' ? 'tradingview' : 'd3';
}
