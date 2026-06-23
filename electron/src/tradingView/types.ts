import type { CandlestickData, Time } from 'lightweight-charts';

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

export type ChartRendererMode = 'd3' | 'tradingview';
