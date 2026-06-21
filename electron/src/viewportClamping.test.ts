import { describe, expect, it } from 'vitest';
import * as d3 from 'd3';
import {
  clampChartTransformToTimeBounds,
  intersectClampSpanWithCandles,
  normalizeViewportClampSpan,
} from './viewportClamping';

describe('normalizeViewportClampSpan', () => {
  it('returns null for invalid spans', () => {
    expect(normalizeViewportClampSpan(null, null)).toBeNull();
    expect(normalizeViewportClampSpan('2024-06-01T00:00:00.000Z', '2024-01-01T00:00:00.000Z')).toBeNull();
  });

  it('normalizes valid spans', () => {
    expect(normalizeViewportClampSpan('2024-01-01T00:00:00.000Z', '2024-06-01T00:00:00.000Z')).toEqual({
      start: '2024-01-01T00:00:00.000Z',
      end: '2024-06-01T00:00:00.000Z',
    });
  });
});

describe('intersectClampSpanWithCandles', () => {
  it('intersects container span with candle extent', () => {
    const span = { start: '2024-01-01T00:00:00.000Z', end: '2024-12-31T00:00:00.000Z' };
    const candles = [
      { time: '2024-03-01T00:00:00.000Z' },
      { time: '2024-09-01T00:00:00.000Z' },
    ];
    expect(intersectClampSpanWithCandles(span, candles)).toEqual({
      start: '2024-03-01T00:00:00.000Z',
      end: '2024-09-01T00:00:00.000Z',
    });
  });
});

describe('clampChartTransformToTimeBounds', () => {
  it('prevents panning past container end', () => {
    const candles = [
      { time: '2024-01-01T00:00:00.000Z' },
      { time: '2024-06-01T00:00:00.000Z' },
      { time: '2024-12-01T00:00:00.000Z' },
    ];
    const bounds = { start: '2024-01-01T00:00:00.000Z', end: '2024-06-01T00:00:00.000Z' };
    const x0 = d3.scaleTime()
      .domain([new Date(bounds.start), new Date(bounds.end)])
      .range([80, 880]);
    const shifted = d3.zoomIdentity.translate(-4000, 0).scale(4);
    const clamped = clampChartTransformToTimeBounds(shifted, x0, bounds, 80, 800);
    const dom = clamped.rescaleX(x0).domain();
    expect(dom[0].getTime()).toBeGreaterThanOrEqual(new Date(bounds.start).getTime() - 1);
    expect(dom[0].getTime()).toBeLessThanOrEqual(new Date(bounds.end).getTime() + 1);
  });
});
