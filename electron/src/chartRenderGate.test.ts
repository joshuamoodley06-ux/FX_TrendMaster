import { describe, expect, it } from 'vitest';
import { CHART_RENDER_GATE_PX, createChartRenderGate } from './chartRenderGate';

describe('chartRenderGate', () => {
  it('allows first measure and blocks sub-pixel jitter', () => {
    const gate = createChartRenderGate(CHART_RENDER_GATE_PX);
    expect(gate.shouldRedraw(800, 620)).toBe(true);
    expect(gate.shouldRedraw(802, 621)).toBe(false);
    expect(gate.shouldRedraw(806, 620)).toBe(true);
  });

  it('blocks width-only jitter under threshold', () => {
    const gate = createChartRenderGate(5);
    gate.shouldRedraw(400, 300);
    expect(gate.shouldRedraw(404, 300)).toBe(false);
    expect(gate.shouldRedraw(406, 300)).toBe(true);
  });

  it('blocks height-only jitter under threshold', () => {
    const gate = createChartRenderGate(5);
    gate.shouldRedraw(400, 300);
    expect(gate.shouldRedraw(400, 303)).toBe(false);
    expect(gate.shouldRedraw(400, 306)).toBe(true);
  });

  it('noteDimensions syncs after data-driven redraw', () => {
    const gate = createChartRenderGate(5);
    gate.shouldRedraw(500, 400);
    gate.noteDimensions(503, 402);
    expect(gate.shouldRedraw(504, 403)).toBe(false);
  });
});
