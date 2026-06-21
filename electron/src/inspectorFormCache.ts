/** Local persistence for in-progress Inspector form fields across tab switches. */

export type InspectorFormCache = {
  seedNotes?: string;
  tradeIdeaNotes?: string;
  markWorkspaceMode?: 'htf' | 'manual' | 'case';
};

const STORAGE_KEY = 'fx_tm_inspector_form_cache_v1';

function safeParse(raw: string | null): Record<string, InspectorFormCache> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function inspectorFormCacheKey(
  symbol: string,
  timeframe: string,
  caseId?: string | null,
): string {
  const sym = String(symbol || '').trim().toUpperCase() || 'UNKNOWN';
  const tf = String(timeframe || '').trim().toUpperCase() || 'D1';
  const cid = String(caseId || 'none').trim() || 'none';
  return `${sym}|${tf}|${cid}`;
}

export function readInspectorFormCache(scopeKey: string): InspectorFormCache {
  if (typeof localStorage === 'undefined') return {};
  const all = safeParse(localStorage.getItem(STORAGE_KEY));
  return all[scopeKey] || {};
}

export function writeInspectorFormCache(scopeKey: string, patch: InspectorFormCache): void {
  if (typeof localStorage === 'undefined') return;
  const all = safeParse(localStorage.getItem(STORAGE_KEY));
  all[scopeKey] = { ...(all[scopeKey] || {}), ...patch };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}
