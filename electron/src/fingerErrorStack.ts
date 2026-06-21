import { useEffect, useState, type Dispatch, type SetStateAction } from 'react';

/** LIFO stack — array is the database; undo is slice(0, -1). */

export function readFingerErrorStack<T>(storageKey: string): T[] {
  if (!storageKey) return [];
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function writeFingerErrorStack<T>(storageKey: string, stack: T[]): void {
  if (!storageKey) return;
  try {
    localStorage.setItem(storageKey, JSON.stringify(stack));
  } catch {
    /* quota / private mode */
  }
}

export function popFingerErrorStack<T>(stack: T[]): { next: T[]; popped: T | null } {
  if (!stack.length) return { next: stack, popped: null };
  return { next: stack.slice(0, -1), popped: stack[stack.length - 1] };
}

export function pushFingerErrorStack<T>(stack: T[], item: T, maxItems = 50): T[] {
  return [...stack, item].slice(-maxItems);
}

/** Persisted LIFO stack — useEffect mirrors state to localStorage on every change. */
export function useFingerErrorStack<T>(storageKey: string, maxItems = 50): {
  stack: T[];
  setStack: Dispatch<SetStateAction<T[]>>;
  push: (item: T) => void;
  undo: () => T | null;
  canUndo: boolean;
  peek: T | null;
} {
  const [stack, setStack] = useState<T[]>(() => readFingerErrorStack<T>(storageKey));

  useEffect(() => {
    setStack(readFingerErrorStack<T>(storageKey));
  }, [storageKey]);

  useEffect(() => {
    writeFingerErrorStack(storageKey, stack);
  }, [storageKey, stack]);

  const push = (item: T) => {
    setStack((prev) => pushFingerErrorStack(prev, item, maxItems));
  };

  const undo = (): T | null => {
    let popped: T | null = null;
    setStack((prev) => {
      const result = popFingerErrorStack(prev);
      popped = result.popped;
      return result.next;
    });
    return popped;
  };

  return {
    stack,
    setStack,
    push,
    undo,
    canUndo: stack.length > 0,
    peek: stack.length ? stack[stack.length - 1] : null,
  };
}
