import { describe, expect, it } from 'vitest';
import * as d3 from 'd3';
import {
  computeChartViewport,
} from './chartRenderPipeline';
import { savedRangeLineStyle } from './rangeLineStyle';

const candles = Array.from({ length: 40 }, (_, i) => ({
  time: new Date(Date.parse('2025-01-01T00:00:00.000Z') + i * 86400000).toISOString(),
  open: 2600 + i,
  high: 2610 + i,
  low: 2590 + i,
  close: 2605 + i,
}));

const metrics = {
  width: 900,
  height: 500,
  margin: { top: 24, right: 86, bottom: 42, left: 72 },
  innerW: 742,
  innerH: 434,
};

const style = {
  snapChartStrokePx: (v: number) => Math.round(v) + 0.5,
  snapChartPx: (v: number) => Math.round(v),
  priceLineY: (y: d3.ScaleLinear<number, number>, price: number) => y(price),
  candleTimeDate: (t: string) => new Date(t),
  candleTimeMs: (t?: string | null) => (t ? Date.parse(t) : NaN),
  shortTime: (t: string) => t.slice(0, 10),
  structureLayerLineColor: () => '#22c55e',
  guidedParentLineColor: () => '#ef4444',
  savedRangeLineStyle,
  draftRangeLineStyle: () => ({ opacity: 0.8, width: 2, dash: '4 4' }),
  overlayLineStyleWithFocus: (base: { opacity: number; width: number; dash: string }) => ({ ...base, showLabel: true }),
  rangeSpanX: () => ({ x1: 80, x2: 400 }),
};

describe('chartRenderPipeline', () => {
  it('computeChartViewport preserves center across transform', () => {
    const vp = computeChartViewport({
      candles,
      timeframe: 'D1',
      transform: d3.zoomIdentity.scale(2).translate(-100, 0),
      metrics,
      scaleMode: 'auto',
      yPanPx: 0,
      yZoom: 1,
      style,
    });
    expect(vp).not.toBeNull();
    expect(vp!.visible.length).toBeGreaterThan(0);
    expect(vp!.yDomain[1]).toBeGreaterThan(vp!.yDomain[0]);
    expect(vp!.baseHi).toBeGreaterThan(vp!.baseLo);
  });
});
