import { describe, expect, it, beforeAll, beforeEach } from 'vitest';
import {
  MAPPING_DATA_STORAGE_KEY,
  clearMappingEventsForContainer,
  isMappingEventsScopeHydrated,
  mappingEventsScopeKey,
  resolveActiveCaseDisplayId,
  writeMappingEventsForContainer,
  readMappingEventsForContainer,
} from './mappingEventsPersistence';

function installLocalStorageMock() {
  const store = new Map<string, string>();
  const mock = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
    removeItem: (key: string) => { store.delete(key); },
    clear: () => { store.clear(); },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true });
  return store;
}

describe('mappingEventsPersistence', () => {
  beforeAll(() => {
    installLocalStorageMock();
  });

  beforeEach(() => {
    localStorage.clear();
  });

  it('builds stable symbol|caseId scope keys', () => {
    expect(mappingEventsScopeKey('xauusd', 'case-1')).toBe('XAUUSD|case-1');
    expect(mappingEventsScopeKey('US500.cash')).toBe('US500.CASH|');
  });

  it('resolves active case display id raw-first', () => {
    expect(resolveActiveCaseDisplayId('uuid-raw', 42)).toBe('uuid-raw');
    expect(resolveActiveCaseDisplayId('', 42)).toBe('42');
    expect(resolveActiveCaseDisplayId('', null)).toBe('');
  });

  it('requires exact ref match before persist is allowed', () => {
    const ref = { current: 'XAUUSD|case-a' as string | null };
    expect(isMappingEventsScopeHydrated(ref, 'XAUUSD|case-a')).toBe(true);
    expect(isMappingEventsScopeHydrated(ref, 'XAUUSD|case-b')).toBe(false);
    ref.current = null;
    expect(isMappingEventsScopeHydrated(ref, 'XAUUSD|case-a')).toBe(false);
  });

  it('scopes events by symbol and case under mapping_data', () => {
    const keyA = mappingEventsScopeKey('XAUUSD', 'case-a');
    const keyB = mappingEventsScopeKey('XAUUSD', 'case-b');
    writeMappingEventsForContainer(keyA, { D1: [{ id: 'e1' }] });
    writeMappingEventsForContainer(keyB, { W1: [{ id: 'e2' }] });

    expect(readMappingEventsForContainer(keyA)).toEqual({ D1: [{ id: 'e1' }] });
    expect(readMappingEventsForContainer(keyB)).toEqual({ W1: [{ id: 'e2' }] });
  });

  it('mirrors reactive save shape under mapping_data', () => {
    const key = mappingEventsScopeKey('XAUUSD');
    writeMappingEventsForContainer(key, { D1: [{ id: 'rh-1', event_type: 'RANGE_HIGH' }] });
    const raw = JSON.parse(localStorage.getItem(MAPPING_DATA_STORAGE_KEY) || '{}');
    expect(raw[key].D1[0]).toMatchObject({ id: 'rh-1', event_type: 'RANGE_HIGH' });
  });

  it('clears a container bucket', () => {
    const key = mappingEventsScopeKey('US500.cash');
    writeMappingEventsForContainer(key, { H1: [{ id: 'x' }] });
    clearMappingEventsForContainer(key);
    expect(readMappingEventsForContainer(key)).toEqual({});
  });
});

describe('syncService re-export contract', () => {
  it('exports mappingEventsScopeKey from syncService', async () => {
    const sync = await import('./syncService');
    expect(sync.mappingEventsScopeKey('XAUUSD', 'abc')).toBe('XAUUSD|abc');
    expect(sync.resolveActiveCaseDisplayId('', 7)).toBe('7');
    expect(sync.MAPPING_DATA_STORAGE_KEY).toBe('mapping_data');
  });
});
