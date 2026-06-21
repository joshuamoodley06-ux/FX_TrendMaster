import { describe, expect, it } from 'vitest';
import {
  createLayoutResizeGuard,
  shouldIgnoreInspectorLayoutResize,
} from './chartLayoutResizeGuard';

describe('chartLayoutResizeGuard', () => {
  it('ignores redraw when inspector open state changed', () => {
    expect(shouldIgnoreInspectorLayoutResize(true, false)).toEqual({
      ignore: true,
      nextInspectorState: true,
    });
    expect(shouldIgnoreInspectorLayoutResize(false, true)).toEqual({
      ignore: true,
      nextInspectorState: false,
    });
  });

  it('allows redraw when inspector state is stable', () => {
    expect(shouldIgnoreInspectorLayoutResize(true, true)).toEqual({
      ignore: false,
      nextInspectorState: true,
    });
    expect(shouldIgnoreInspectorLayoutResize(false, false)).toEqual({
      ignore: false,
      nextInspectorState: false,
    });
  });

  it('allows first resize measure', () => {
    expect(shouldIgnoreInspectorLayoutResize(false, null)).toEqual({
      ignore: false,
      nextInspectorState: false,
    });
  });

  it('tracks state via createLayoutResizeGuard', () => {
    const guard = createLayoutResizeGuard();
    expect(guard.shouldIgnoreRedraw(false)).toBe(false);
    expect(guard.shouldIgnoreRedraw(true)).toBe(true);
    expect(guard.shouldIgnoreRedraw(true)).toBe(false);
    expect(guard.shouldIgnoreRedraw(false)).toBe(true);
    guard.reset();
    expect(guard.shouldIgnoreRedraw(true)).toBe(false);
  });
});
