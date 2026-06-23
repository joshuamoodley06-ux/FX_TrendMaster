import type { DeepPartial, ChartOptions } from 'lightweight-charts';

export const tradingViewDarkTheme: DeepPartial<ChartOptions> = {
  layout: {
    background: { color: '#020617' },
    textColor: '#cbd5e1',
  },
  grid: {
    vertLines: { color: 'rgba(148, 163, 184, 0.12)' },
    horzLines: { color: 'rgba(148, 163, 184, 0.12)' },
  },
  crosshair: {
    mode: 1,
  },
  rightPriceScale: {
    borderColor: 'rgba(148, 163, 184, 0.25)',
  },
  timeScale: {
    borderColor: 'rgba(148, 163, 184, 0.25)',
    timeVisible: true,
    secondsVisible: false,
  },
};
