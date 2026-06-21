import { describe, expect, it, afterEach, beforeAll } from 'vitest';
import {
  MAPPING_SESSION_STORAGE_KEY,
  buildMappingSessionState,
  childMappingParentIdForResume,
  clearMappingSession,
  formatMappingSessionStatusLine,
  hasMappingSession,
  loadMappingSession,
  saveMappingSession,
  sessionTargetsRange,
  yearFromWindow,
} from './mappingSessionPersistence';

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

describe('mappingSessionPersistence', () => {
  beforeAll(() => {
    installLocalStorageMock();
  });

  afterEach(() => {
    clearMappingSession();
  });

  it('saves and loads session state', () => {
    const state = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'DAILY',
      activeWeeklyRangeId: '7',
      activeDailyRangeId: '3',
      currentParentRangeId: '7',
      chartTimeframe: 'D1',
      sourceTimeframe: 'D1',
      rangeScope: 'MAJOR',
      researchWindowStart: '2025-06-01',
      researchWindowEnd: '2025-06-30',
      currentCandidateIndex: 2,
      childMappingActive: true,
      childMappingDetectionRunId: 'run-abc',
      childMappingPhase: 'reviewing',
    });
    saveMappingSession(state);
    expect(hasMappingSession()).toBe(true);
    const loaded = loadMappingSession();
    expect(loaded?.active_layer).toBe('DAILY');
    expect(loaded?.active_weekly_range_id).toBe('7');
    expect(loaded?.current_candidate_index).toBe(2);
    expect(loaded?.child_mapping_active).toBe(true);
  });

  it('formats status bar line', () => {
    const line = formatMappingSessionStatusLine(buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'DAILY',
      activeWeeklyRangeId: '7',
      activeDailyRangeId: '3',
      chartTimeframe: 'D1',
      sourceTimeframe: 'D1',
      rangeScope: 'MAJOR',
    }));
    expect(line).toContain('Mapping Session');
    expect(line).toContain('2025');
    expect(line).toContain('DAILY');
    expect(line).toContain('Weekly #7');
    expect(line).toContain('Daily #3');
  });

  it('derives year from research window', () => {
    expect(yearFromWindow('2025-06-01T00:00:00.000Z', null)).toBe('2025');
  });

  it('clears stored session', () => {
    saveMappingSession(buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'WEEKLY',
      chartTimeframe: 'W1',
      sourceTimeframe: 'W1',
      rangeScope: 'MAJOR',
    }));
    clearMappingSession();
    expect(localStorage.getItem(MAPPING_SESSION_STORAGE_KEY)).toBeNull();
  });

  it('sessionTargetsRange focuses explorer node', () => {
    const base = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'WEEKLY',
      activeWeeklyRangeId: '7',
      chartTimeframe: 'W1',
      sourceTimeframe: 'W1',
      rangeScope: 'MAJOR',
    });
    const next = sessionTargetsRange(base, '12', 'DAILY');
    expect(next.active_layer).toBe('DAILY');
    expect(next.active_daily_range_id).toBe('12');
    expect(next.current_parent_range_id).toBe('7');
  });

  it('sessionTargetsRange sets daily parent for intraday', () => {
    const base = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'DAILY',
      activeWeeklyRangeId: '7',
      activeDailyRangeId: '12',
      chartTimeframe: 'H1',
      sourceTimeframe: 'H1',
      rangeScope: 'MAJOR',
    });
    const next = sessionTargetsRange(base, '55', 'INTRADAY');
    expect(next.active_intraday_range_id).toBe('55');
    expect(next.current_parent_daily_id).toBe('12');
    expect(next.current_parent_range_id).toBe('12');
  });

  it('childMappingParentIdForResume prefers daily parent for intraday workflow', () => {
    const stored = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'INTRADAY',
      activeDailyRangeId: '12',
      currentParentDailyId: '12',
      currentParentRangeId: '12',
      chartTimeframe: 'H1',
      sourceTimeframe: 'H1',
      rangeScope: 'MAJOR',
      childMappingActive: true,
    });
    expect(childMappingParentIdForResume(stored)).toBe('12');
  });

  it('sessionTargetsRange sets intraday parent for micro', () => {
    const base = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'INTRADAY',
      activeDailyRangeId: '12',
      activeIntradayRangeId: '44',
      chartTimeframe: 'M15',
      sourceTimeframe: 'M15',
      rangeScope: 'MAJOR',
    });
    const next = sessionTargetsRange(base, '99', 'MICRO');
    expect(next.active_micro_range_id).toBe('99');
    expect(next.current_parent_intraday_id).toBe('44');
    expect(next.current_parent_range_id).toBe('44');
  });

  it('childMappingParentIdForResume prefers intraday parent for micro workflow', () => {
    const stored = buildMappingSessionState({
      symbol: 'XAUUSD',
      year: '2025',
      activeLayer: 'MICRO',
      activeIntradayRangeId: '44',
      currentParentIntradayId: '44',
      currentParentRangeId: '44',
      chartTimeframe: 'M15',
      sourceTimeframe: 'M15',
      rangeScope: 'MAJOR',
      childMappingActive: true,
    });
    expect(childMappingParentIdForResume(stored)).toBe('44');
  });
});
