import { describe, expect, it } from 'vitest';
import {
  DEFAULT_TRADINGVIEW_MAPPING_INPUT,
  isTradingViewMappingInputEnabled,
  normalizeTradingViewMappingInputMode,
  TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY,
  USE_TRADINGVIEW_MAPPING_INPUT,
} from './chartRendererConfig';

describe('TradingView mapping input flag', () => {
  it('defaults OFF at compile time and in storage key default', () => {
    expect(USE_TRADINGVIEW_MAPPING_INPUT).toBe(false);
    expect(DEFAULT_TRADINGVIEW_MAPPING_INPUT).toBe('off');
    expect(TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY).toBe('fx_tm_tradingview_mapping_input_v1');
  });

  it('enables only when localStorage value is on', () => {
    expect(isTradingViewMappingInputEnabled('on')).toBe(true);
    expect(isTradingViewMappingInputEnabled('off')).toBe(false);
    expect(isTradingViewMappingInputEnabled(undefined)).toBe(false);
    expect(normalizeTradingViewMappingInputMode('on')).toBe('on');
    expect(normalizeTradingViewMappingInputMode('readonly')).toBe('off');
  });
});
