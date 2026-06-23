import type { CandlestickData, SeriesMarker, Time } from 'lightweight-charts';

export type FxtmCandleRow = {
  symbol?: string;
  timeframe?: string;
  time?: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
};

export type TradingViewCandle = CandlestickData<Time>;

export type TradingViewAdapterResult = {
  bars: TradingViewCandle[];
  dropped: number;
};

export type TradingViewChartMode = 'latest' | 'hierarchy' | 'replay' | 'selection';

export type TradingViewChartWindow = {
  mode: TradingViewChartMode;
  timeframe: string;
  hierarchyStart?: string | null;
  hierarchyEnd?: string | null;
  replayCutTime?: string | null;
};

export type ChartRendererMode = 'd3' | 'tradingview';

export type TradingViewOverlayMode = 'off' | 'readonly';
export type TradingViewSelectedCandleMode = 'off' | 'readonly';

export type TradingViewSelectedCandle = {
  source: 'tradingview';
  symbol: string;
  chartTimeframe: string;
  sourceTimeframe?: string;
  time: string;
  tvTime: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  barIndex?: number;
};

export type TradingViewSelectionDebugEvent = {
  clickHandlerAttached?: boolean;
  crosshairReceived?: boolean;
  pointerOverChart?: boolean;
  chartContainerPointerEvents?: string;
  overlayPointerEvents?: string;
  lastClickEventObject?: string;
  clickReceived?: boolean;
  rawTvTime?: string;
  normalizedClickTime?: string;
  displayCandleCount?: number;
  matchedCandle?: boolean;
  matchedCandleTime?: string;
  markerCount?: number;
  selMarkerPresent?: boolean;
};

export type TradingViewRangeLine = {
  id: string;
  rangeId?: string | number | null;
  kind: 'RH' | 'RL';
  role: 'selected' | 'saved' | 'parent';
  label: string;
  price: number;
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
};

export type TradingViewBosMarker = SeriesMarker<Time> & {
  id: string;
};

export type TradingViewOverlaySet = {
  priceLines: TradingViewRangeLine[];
  markers: TradingViewBosMarker[];
  debug?: {
    rangeOverlayCount: number;
    rhRlLineCount: number;
    bosMarkerCount: number;
    selectedRangeFallbackUsed: boolean;
  };
};

export type TradingViewFitRequest = {
  token: number;
  from?: Time;
  to?: Time;
  target?: Time;
};
