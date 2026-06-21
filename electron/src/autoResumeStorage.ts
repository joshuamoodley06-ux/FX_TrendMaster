export const LAST_ACTIVE_SYMBOL_KEY = 'last_active_symbol';
export const LAST_ACTIVE_TF_KEY = 'last_active_tf';

export type AutoResumeSession = {
  symbol: string;
  timeframe: string;
};

export function normaliseAutoResumeSymbol(raw?: string | null): string | null {
  const value = String(raw || '').trim().toUpperCase();
  return value || null;
}

export function normaliseAutoResumeTimeframe(raw?: string | null): string | null {
  const value = String(raw || '').trim().toUpperCase();
  return value || null;
}

export function readAutoResumeSession(): AutoResumeSession | null {
  try {
    const symbol = normaliseAutoResumeSymbol(localStorage.getItem(LAST_ACTIVE_SYMBOL_KEY));
    const timeframe = normaliseAutoResumeTimeframe(localStorage.getItem(LAST_ACTIVE_TF_KEY));
    if (!symbol || !timeframe) return null;
    return { symbol, timeframe };
  } catch {
    return null;
  }
}

export function writeAutoResumeSession(symbol: string, timeframe: string): void {
  const sym = normaliseAutoResumeSymbol(symbol);
  const tf = normaliseAutoResumeTimeframe(timeframe);
  if (!sym || !tf) return;
  try {
    localStorage.setItem(LAST_ACTIVE_SYMBOL_KEY, sym);
    localStorage.setItem(LAST_ACTIVE_TF_KEY, tf);
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearAutoResumeSession(): void {
  try {
    localStorage.removeItem(LAST_ACTIVE_SYMBOL_KEY);
    localStorage.removeItem(LAST_ACTIVE_TF_KEY);
  } catch {
    /* ignore */
  }
}
