/** Reactive local persistence for chart mapping events (RH, RL, BOS, etc.). */

export const MAPPING_DATA_STORAGE_KEY = 'mapping_data';

export type MappingEventsByTimeframe = Record<string, unknown[]>;

type MappingDataStore = Record<string, MappingEventsByTimeframe>;

/** Canonical scope key: `SYMBOL|caseId` (empty caseId = global workspace bucket). */
export function mappingEventsScopeKey(symbol: string, caseId?: string | null): string {
  return `${String(symbol || 'XAUUSD').toUpperCase()}|${String(caseId ?? '')}`;
}

/** @deprecated Use mappingEventsScopeKey — kept for existing call sites. */
export const mappingEventsContainerKey = mappingEventsScopeKey;

export function resolveActiveCaseDisplayId(
  rawCaseId?: string | null,
  numericCaseId?: number | null,
): string {
  const raw = String(rawCaseId || '').trim();
  if (raw) return raw;
  if (numericCaseId !== null && numericCaseId !== undefined) return String(numericCaseId);
  return '';
}

export function isMappingEventsScopeHydrated(
  hydratedScopeRef: { current: string | null },
  scopeKey: string,
): boolean {
  return hydratedScopeRef.current === scopeKey;
}

function readStore(): MappingDataStore {
  try {
    const raw = localStorage.getItem(MAPPING_DATA_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as MappingDataStore;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(store: MappingDataStore): void {
  try {
    localStorage.setItem(MAPPING_DATA_STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readMappingEventsForContainer(containerKey: string): MappingEventsByTimeframe {
  const store = readStore();
  const row = store[containerKey];
  return row && typeof row === 'object' ? row : {};
}

export function writeMappingEventsForContainer(
  containerKey: string,
  eventsByTf: MappingEventsByTimeframe,
): void {
  const store = readStore();
  store[containerKey] = eventsByTf;
  writeStore(store);
}

export function clearMappingEventsForContainer(containerKey: string): void {
  const store = readStore();
  if (!(containerKey in store)) return;
  delete store[containerKey];
  writeStore(store);
}
