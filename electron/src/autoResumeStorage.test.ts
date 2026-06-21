import { describe, expect, it, beforeAll, beforeEach } from 'vitest';
import {
  LAST_ACTIVE_SYMBOL_KEY,
  LAST_ACTIVE_TF_KEY,
  readAutoResumeSession,
  writeAutoResumeSession,
  clearAutoResumeSession,
} from './autoResumeStorage';

function installLocalStorageMock() {
  const store = new Map<string, string>();
  const mock = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
    removeItem: (key: string) => { store.delete(key); },
    clear: () => { store.clear(); },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true });
}

describe('autoResumeStorage', () => {
  beforeAll(() => {
    installLocalStorageMock();
  });

  beforeEach(() => {
    clearAutoResumeSession();
  });

  it('returns null when no session is stored', () => {
    expect(readAutoResumeSession()).toBeNull();
  });

  it('round-trips symbol and timeframe', () => {
    writeAutoResumeSession('xauusd', 'd1');
    expect(readAutoResumeSession()).toEqual({ symbol: 'XAUUSD', timeframe: 'D1' });
    expect(localStorage.getItem(LAST_ACTIVE_SYMBOL_KEY)).toBe('XAUUSD');
    expect(localStorage.getItem(LAST_ACTIVE_TF_KEY)).toBe('D1');
  });
});
