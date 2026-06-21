import { describe, expect, it, afterEach, beforeAll } from 'vitest';
import {
  applyMappingSessionRestore,
  deriveLayerActiveIdsFromRanges,
  snapshotToMappingSession,
  type MappingSessionRestoreActions,
} from './useMappingSessionPersistence';
import {
  buildMappingSessionState,
  clearMappingSession,
  loadMappingSession,
  saveMappingSession,
} from '../mappingSessionPersistence';

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

describe('useMappingSessionPersistence helpers', () => {
  beforeAll(() => {
    installLocalStorageMock();
  });

  afterEach(() => {
    clearMappingSession();
  });

  it('snapshotToMappingSession maps UI snapshot to persisted state', () => {
    const state = snapshotToMappingSession({
      symbol: 'XAUUSD',
      year: '2025',
      structureLayer: 'DAILY',
      activeWeeklyRangeId: '7',
      activeDailyRangeId: '12',
      selectedParentRangeId: '7',
      activeStructuralRangeId: '12',
      chartTimeframe: 'D1',
      sourceTimeframe: 'D1',
      rangeScope: 'MAJOR',
    });
    expect(state.active_layer).toBe('DAILY');
    expect(state.active_weekly_range_id).toBe('7');
    expect(state.active_structural_range_id).toBe('12');
  });

  it('applyMappingSessionRestore applies layer, scope, and parent', () => {
    const stored = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'INTRADAY',
      currentParentRangeId: '12',
      chartTimeframe: 'H1',
      sourceTimeframe: 'H1',
      rangeScope: 'MINOR',
    });
    const calls: string[] = [];
    const actions: MappingSessionRestoreActions = {
      setStructureLayer: (layer) => calls.push(`layer:${layer}`),
      setRangeScope: (scope) => calls.push(`scope:${scope}`),
      setSourceTimeframe: (tf) => calls.push(`source:${tf}`),
      setTimeframe: (tf) => calls.push(`chart:${tf}`),
      setSelectedParentRangeId: (id) => calls.push(`parent:${id}`),
      setActiveStructuralRangeId: (id) => calls.push(`active:${id}`),
      setExplorerYearFilter: (year) => calls.push(`year:${year}`),
    };
    applyMappingSessionRestore(stored, actions);
    expect(calls).toContain('layer:INTRADAY');
    expect(calls).toContain('scope:MINOR');
    expect(calls).toContain('parent:12');
    expect(calls).toContain('chart:H1');
  });

  it('deriveLayerActiveIdsFromRanges walks parent chain', () => {
    const ids = deriveLayerActiveIdsFromRanges([
      { range_id: '7', structure_layer: 'WEEKLY' },
      { range_id: '12', structure_layer: 'DAILY', parent_range_id: '7' },
      { range_id: '44', structure_layer: 'INTRADAY', parent_range_id: '12' },
    ], '44');
    expect(ids.activeWeeklyRangeId).toBe('7');
    expect(ids.activeDailyRangeId).toBe('12');
    expect(ids.activeIntradayRangeId).toBe('44');
  });

  it('persists snapshot through save/load round trip', () => {
    saveMappingSession(snapshotToMappingSession({
      symbol: 'XAUUSD',
      year: '2025',
      structureLayer: 'WEEKLY',
      activeWeeklyRangeId: '7',
      chartTimeframe: 'W1',
      sourceTimeframe: 'W1',
      rangeScope: 'MAJOR',
    }));
    const loaded = loadMappingSession();
    expect(loaded?.symbol).toBe('XAUUSD');
    expect(loaded?.active_layer).toBe('WEEKLY');
    expect(loaded?.active_weekly_range_id).toBe('7');
  });
});
