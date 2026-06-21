/** Librarian render gate — block illegal sub-pixel SVG rebuilds from layout jitter. */

export const CHART_RENDER_GATE_PX = 5;

export type ChartDimensions = { w: number; h: number };

export type ChartRenderGate = {
  /** True when width or height shifted more than the threshold (or first measure). */
  shouldRedraw: (newW: number, newH: number) => boolean;
  /** Sync gate after a forced data-driven redraw. */
  noteDimensions: (w: number, h: number) => void;
  reset: () => void;
  peek: () => ChartDimensions;
};

export function createChartRenderGate(thresholdPx = CHART_RENDER_GATE_PX): ChartRenderGate {
  const lastDimensions: ChartDimensions = { w: 0, h: 0 };

  const noteDimensions = (w: number, h: number) => {
    lastDimensions.w = Math.round(w);
    lastDimensions.h = Math.round(h);
  };

  return {
    shouldRedraw(newW: number, newH: number) {
      const w = Math.round(newW);
      const h = Math.round(newH);
      if (lastDimensions.w === 0 && lastDimensions.h === 0) {
        noteDimensions(w, h);
        return true;
      }
      const dw = Math.abs(lastDimensions.w - w);
      const dh = Math.abs(lastDimensions.h - h);
      if (dw > thresholdPx || dh > thresholdPx) {
        noteDimensions(w, h);
        return true;
      }
      return false;
    },
    noteDimensions,
    reset() {
      lastDimensions.w = 0;
      lastDimensions.h = 0;
    },
    peek: () => ({ ...lastDimensions }),
  };
}
