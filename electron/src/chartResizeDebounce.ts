export const CHART_RESIZE_DEBOUNCE_MS = 200;

export type DebouncedResizeHandler = (() => void) & { cancel: () => void };

/** Debounce layout resize before triggering an expensive chart redraw. */
export function createDebouncedResizeHandler(
  onRedraw: () => void,
  debounceMs = CHART_RESIZE_DEBOUNCE_MS,
): DebouncedResizeHandler {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const handler = (() => {
    if (timer != null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      onRedraw();
    }, debounceMs);
  }) as DebouncedResizeHandler;

  handler.cancel = () => {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return handler;
}
