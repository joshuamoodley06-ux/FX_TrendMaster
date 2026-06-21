/** Layout-state guard — skip chart tear-down when resize is from inspector panel toggle. */

export type InspectorLayoutResizeDecision = {
  ignore: boolean;
  nextInspectorState: boolean;
};

/**
 * When inspector open state changed since last resize, the canvas shift is
 * layout-only — do not trigger a D3 redraw.
 */
export function shouldIgnoreInspectorLayoutResize(
  isInspectorOpen: boolean,
  lastInspectorState: boolean | null,
): InspectorLayoutResizeDecision {
  if (lastInspectorState === null) {
    return { ignore: false, nextInspectorState: isInspectorOpen };
  }
  if (isInspectorOpen !== lastInspectorState) {
    return { ignore: true, nextInspectorState: isInspectorOpen };
  }
  return { ignore: false, nextInspectorState: lastInspectorState };
}

export type LayoutResizeGuard = {
  shouldIgnoreRedraw: (isInspectorOpen: boolean) => boolean;
  reset: () => void;
};

export function createLayoutResizeGuard(): LayoutResizeGuard {
  let lastInspectorState: boolean | null = null;

  return {
    shouldIgnoreRedraw(isInspectorOpen: boolean) {
      const decision = shouldIgnoreInspectorLayoutResize(isInspectorOpen, lastInspectorState);
      lastInspectorState = decision.nextInspectorState;
      return decision.ignore;
    },
    reset() {
      lastInspectorState = null;
    },
  };
}
