import {
  clearMappingEventsForContainer,
  mappingEventsContainerKey,
  writeMappingEventsForContainer,
} from './mappingEventsPersistence';
import { ghostRangeUiClearMessage } from './rangeRehydrationService';
import type { RangeRehydrationListResult } from './rangeRehydrationService';
import { loadSessionFromSyncArchitect, type SyncArchitectLoadResult } from './syncArchitectLoad';

/** Local mirror key for chart mapping events (RH/RL markers, etc.). */
export const MAPPING_DATA_LOCAL_KEY = 'mapping_data';

export type StructuralAnchorSnapshot = { price: string; time: string };

/** Map Studio UI slice exercised by stale-rehydration integration tests. */
export type MapStudioUiState = {
  candles: unknown[];
  rhAnchor: StructuralAnchorSnapshot;
  rlAnchor: StructuralAnchorSnapshot;
  bhAnchor: StructuralAnchorSnapshot;
  blAnchor: StructuralAnchorSnapshot;
  structuralRanges: unknown[];
  savedStructuralRanges: unknown[];
  eventsByTf: Record<string, unknown[]>;
  activeStructuralRangeId: string;
  selectedParentRangeId: string;
  rangeHigh: string;
  rangeLow: string;
  chartBlocked: boolean;
  statusMessage: string;
};

const EMPTY_ANCHOR: StructuralAnchorSnapshot = { price: '', time: '' };

/** Pre-populated “ghost” UI — RH/RL, ranges, and local mapping events present. */
export function createGhostMapStudioUiState(timeframe = 'D1'): MapStudioUiState {
  return {
    candles: [{ time: '2026-01-01T00:00:00.000Z', open: 1, high: 2, low: 0.5, close: 1.5 }],
    rhAnchor: { price: '2650.00', time: '2026-01-01T00:00:00.000Z' },
    rlAnchor: { price: '2600.00', time: '2025-12-01T00:00:00.000Z' },
    bhAnchor: { price: '2660.00', time: '2026-01-02T00:00:00.000Z' },
    blAnchor: { price: '2590.00', time: '2025-11-01T00:00:00.000Z' },
    structuralRanges: [{ range_id: 'ghost-1', range_high: 2650, range_low: 2600 }],
    savedStructuralRanges: [{ range_id: 'ghost-1', range_high: 2650, range_low: 2600 }],
    eventsByTf: { [timeframe]: [{ id: 'ghost-rh', event_type: 'RANGE_HIGH', price: 2650 }] },
    activeStructuralRangeId: 'ghost-1',
    selectedParentRangeId: 'ghost-parent',
    rangeHigh: '2650.00',
    rangeLow: '2600.00',
    chartBlocked: false,
    statusMessage: '',
  };
}

export function hasGhostMapStudioData(state: MapStudioUiState): boolean {
  return (
    state.candles.length > 0
    || !!String(state.rhAnchor.price || '').trim()
    || !!String(state.rlAnchor.price || '').trim()
    || state.structuralRanges.length > 0
    || state.savedStructuralRanges.length > 0
    || Object.values(state.eventsByTf).some((rows) => rows.length > 0)
    || !!state.activeStructuralRangeId
  );
}

/** Cleared UI snapshot after Sync Architect blocks rehydration. */
export function buildMapStudioGhostClearState(symbol: string, timeframe: string): MapStudioUiState {
  return {
    candles: [],
    rhAnchor: { ...EMPTY_ANCHOR },
    rlAnchor: { ...EMPTY_ANCHOR },
    bhAnchor: { ...EMPTY_ANCHOR },
    blAnchor: { ...EMPTY_ANCHOR },
    structuralRanges: [],
    savedStructuralRanges: [],
    eventsByTf: {},
    activeStructuralRangeId: '',
    selectedParentRangeId: '',
    rangeHigh: '',
    rangeLow: '',
    chartBlocked: true,
    statusMessage: ghostRangeUiClearMessage(symbol, timeframe),
  };
}

export function applyGhostClearToUiState(
  _prior: MapStudioUiState,
  symbol: string,
  timeframe: string,
): MapStudioUiState {
  return buildMapStudioGhostClearState(symbol, timeframe);
}

export function isStaleRehydrationLoad(result: Pick<SyncArchitectLoadResult, 'should_clear_ui'>): boolean {
  return Boolean(result.should_clear_ui);
}

/** Seed ghost mapping events into localStorage (`mapping_data`). */
export function seedGhostMappingLocalStorage(symbol: string, caseId: string, timeframe = 'D1'): void {
  const key = mappingEventsContainerKey(symbol, caseId);
  writeMappingEventsForContainer(key, {
    [timeframe]: [{ id: 'ghost-rh', event_type: 'RANGE_HIGH', price: 2650 }],
  });
}

export function purgeGhostMappingLocalStorage(symbol: string, caseId?: string | null): void {
  clearMappingEventsForContainer(mappingEventsContainerKey(symbol, caseId ?? null));
}

/**
 * Test fixture: stale `mapping_ranges` context (SQLite via electronAPI) represented as
 * a rehydration list result with `should_clear_ui: true`.
 */
export function buildStaleMappingRangesRehydrationFixture(
  symbol: string,
  timeframe: string,
  caseId?: string | null,
): RangeRehydrationListResult {
  return {
    ok: true,
    databasePath: 'C:\\cache\\candle_cache.db',
    symbol: symbol.toUpperCase(),
    timeframe: timeframe.toUpperCase(),
    case_id: caseId ?? null,
    ranges: [],
    rehydration: {
      context_match: false,
      should_clear_ui: true,
      matching_count: 0,
      stale_count: 3,
      mismatched_count: 0,
      total_count: 3,
    },
  };
}

export type MapStudioSessionLoadOutcome = {
  sync: SyncArchitectLoadResult;
  ui: MapStudioUiState;
  blocked: boolean;
};

/** Map Studio warm load — Sync Architect guard + UI clear when cache is stale. */
export async function executeMapStudioSessionLoad(args: {
  symbol: string;
  timeframe: string;
  caseId?: string | null;
  priorUi: MapStudioUiState;
  refresh?: boolean;
  range?: { start?: string; end?: string } | null;
}): Promise<MapStudioSessionLoadOutcome> {
  const sym = String(args.symbol || 'XAUUSD').trim().toUpperCase();
  const tf = String(args.timeframe || 'D1').trim().toUpperCase();

  const sync = await loadSessionFromSyncArchitect(sym, tf, {
    caseId: args.caseId ?? null,
    refresh: !!args.refresh,
    range: args.range ?? null,
  });

  if (isStaleRehydrationLoad(sync)) {
    purgeGhostMappingLocalStorage(sym, args.caseId ?? null);
    return {
      sync,
      ui: applyGhostClearToUiState(args.priorUi, sym, tf),
      blocked: true,
    };
  }

  return {
    sync,
    ui: {
      ...args.priorUi,
      candles: sync.candles,
      chartBlocked: sync.candles.length === 0,
      statusMessage: sync.candles.length
        ? priorUiStatus(args.priorUi)
        : (sync.error || `No ${tf} candles available.`),
    },
    blocked: false,
  };
}

function priorUiStatus(prior: MapStudioUiState): string {
  return prior.statusMessage || '';
}
