// Local validation notes (PASS / REVIEW) — renderer-only, not durable truth.

export type ValidationStatus = 'PASS' | 'REVIEW';

export type ValidationEntry = {
  id: string;
  at: number;
  symbol: string;
  batch: string;
  kind: 'weekly_range' | 'daily_retracement' | 'ask_result';
  subjectId: string;
  status: ValidationStatus;
  snapshot: Record<string, unknown>;
};

const STORAGE_KEY = 'analyst.validationJournal';

export function loadValidationJournal(): ValidationEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveValidationEntry(entry: Omit<ValidationEntry, 'id' | 'at'>): ValidationEntry {
  const rows = loadValidationJournal();
  const full: ValidationEntry = {
    ...entry,
    id: `v_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    at: Date.now(),
  };
  rows.unshift(full);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rows.slice(0, 500)));
  return full;
}

export function journalCounts(symbol?: string): { pass: number; review: number } {
  const rows = loadValidationJournal();
  const filtered = symbol ? rows.filter((r) => r.symbol === symbol) : rows;
  return {
    pass: filtered.filter((r) => r.status === 'PASS').length,
    review: filtered.filter((r) => r.status === 'REVIEW').length,
  };
}
