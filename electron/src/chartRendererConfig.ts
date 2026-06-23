import type { ChartRendererMode, TradingViewOverlayMode } from './tradingView/types';

export const CHART_RENDERER_STORAGE_KEY = 'fx_tm_chart_renderer_v1';
export const DEFAULT_CHART_RENDERER: ChartRendererMode = 'd3';
export const TRADINGVIEW_OVERLAYS_STORAGE_KEY = 'fx_tm_tradingview_overlays_v1';
export const DEFAULT_TRADINGVIEW_OVERLAY_MODE: TradingViewOverlayMode = 'off';

export function normalizeChartRendererMode(value: unknown): ChartRendererMode {
  return value === 'tradingview' ? 'tradingview' : 'd3';
}

export function normalizeTradingViewOverlayMode(value: unknown): TradingViewOverlayMode {
  return value === 'readonly' ? 'readonly' : 'off';
}
