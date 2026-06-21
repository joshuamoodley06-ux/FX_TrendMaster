import { describe, expect, it, vi } from 'vitest';
import {
  popFingerErrorStack,
  pushFingerErrorStack,
  readFingerErrorStack,
  writeFingerErrorStack,
} from './fingerErrorStack';

describe('fingerErrorStack LIFO helpers', () => {
  it('pops the last item LIFO style', () => {
    const stack = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    const { next, popped } = popFingerErrorStack(stack);
    expect(popped).toEqual({ id: 'c' });
    expect(next).toEqual([{ id: 'a' }, { id: 'b' }]);
  });

  it('undo on empty stack is a no-op', () => {
    const { next, popped } = popFingerErrorStack([]);
    expect(popped).toBeNull();
    expect(next).toEqual([]);
  });

  it('push respects max length', () => {
    const next = pushFingerErrorStack([1, 2], 3, 2);
    expect(next).toEqual([2, 3]);
  });
});

describe('fingerErrorStack localStorage mirror', () => {
  it('persists stack to localStorage', () => {
    const bucket: Record<string, string> = {};
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => bucket[key] ?? null,
      setItem: (key: string, value: string) => { bucket[key] = value; },
      removeItem: (key: string) => { delete bucket[key]; },
    });

    const KEY = 'fx_tm_finger_error_stack_test';
    writeFingerErrorStack(KEY, [{ role: 'RH' }]);
    expect(readFingerErrorStack(KEY)).toEqual([{ role: 'RH' }]);
  });
});
