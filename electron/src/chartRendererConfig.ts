import type { ChartRendererMode, TradingViewOverlayMode, TradingViewSelectedCandleMode } from './tradingView/types';

export const CHART_RENDERER_STORAGE_KEY = 'fx_tm_chart_renderer_v1';
export const DEFAULT_CHART_RENDERER: ChartRendererMode = 'd3';
export const TRADINGVIEW_OVERLAYS_STORAGE_KEY = 'fx_tm_tradingview_overlays_v1';
export const DEFAULT_TRADINGVIEW_OVERLAY_MODE: TradingViewOverlayMode = 'off';
export const TRADINGVIEW_SELECTED_CANDLE_STORAGE_KEY = 'fx_tm_tradingview_selected_candle_v1';
export const DEFAULT_TRADINGVIEW_SELECTED_CANDLE_MODE: TradingViewSelectedCandleMode = 'off';
export const TRADINGVIEW_DEBUG_STORAGE_KEY = 'fx_tm_tradingview_debug_v1';
export type TradingViewDebugMode = 'off' | 'dev';
export const DEFAULT_TRADINGVIEW_DEBUG_MODE: TradingViewDebugMode = 'off';
export const TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY = 'fx_tm_tradingview_mapping_input_v1';
export type TradingViewMappingInputMode = 'off' | 'on';
export const DEFAULT_TRADINGVIEW_MAPPING_INPUT: TradingViewMappingInputMode = 'off';
/** Compile-time default; runtime override via TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY. */
export const USE_TRADINGVIEW_MAPPING_INPUT = false;

export function normalizeChartRendererMode(value: unknown): ChartRendererMode {
  return value === 'tradingview' ? 'tradingview' : 'd3';
}

export function normalizeTradingViewOverlayMode(value: unknown): TradingViewOverlayMode {
  return value === 'readonly' ? 'readonly' : 'off';
}

export function normalizeTradingViewSelectedCandleMode(value: unknown): TradingViewSelectedCandleMode {
  return value === 'readonly' ? 'readonly' : 'off';
}

export function normalizeTradingViewDebugMode(value: unknown): TradingViewDebugMode {
  return value === 'dev' ? 'dev' : 'off';
}

export function normalizeTradingViewMappingInputMode(value: unknown): TradingViewMappingInputMode {
  return value === 'on' ? 'on' : 'off';
}

export function isTradingViewMappingInputEnabled(value: unknown): boolean {
  return normalizeTradingViewMappingInputMode(value) === 'on';
}
