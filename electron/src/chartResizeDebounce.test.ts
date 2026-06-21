import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  CHART_RESIZE_DEBOUNCE_MS,
  createDebouncedResizeHandler,
} from './chartResizeDebounce';

describe('chartResizeDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('defaults to 200ms debounce', () => {
    expect(CHART_RESIZE_DEBOUNCE_MS).toBe(200);
  });

  it('redraws only after resize settles', () => {
    const redraw = vi.fn();
    const debounced = createDebouncedResizeHandler(redraw);

    debounced();
    debounced();
    debounced();
    expect(redraw).not.toHaveBeenCalled();

    vi.advanceTimersByTime(199);
    expect(redraw).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(redraw).toHaveBeenCalledTimes(1);
  });

  it('cancels pending redraw on cleanup', () => {
    const redraw = vi.fn();
    const debounced = createDebouncedResizeHandler(redraw);
    debounced();
    debounced.cancel();
    vi.advanceTimersByTime(CHART_RESIZE_DEBOUNCE_MS);
    expect(redraw).not.toHaveBeenCalled();
  });
});
