import { getElectronApiBridge } from './localResearchClient';

export type CachedMappingRangeRow = {
  id: string;
  case_id?: string | null;
  symbol: string;
  timeframe: string;
  structure_layer?: string | null;
  range_high: number;
  range_low: number;
  start_time?: string | null;
  end_time?: string | null;
  parent_id?: string | null;
  origin?: string | null;
  status?: string | null;
};

export type RangeRehydrationReport = {
  context_match: boolean;
  should_clear_ui: boolean;
  matching_count: number;
  stale_count: number;
  mismatched_count: number;
  total_count: number;
};

export type RangeRehydrationListResult = {
  ok: boolean;
  databasePath: string;
  symbol?: string;
  timeframe?: string;
  case_id?: string | null;
  ranges: CachedMappingRangeRow[];
  rehydration: RangeRehydrationReport | null;
  error?: string;
};

export function normaliseRehydrationSymbol(raw: unknown): string {
  return String(raw || 'XAUUSD').trim().toUpperCase();
}

export function normaliseRehydrationTimeframe(raw: unknown): string {
  return String(raw || 'D1').trim().toUpperCase();
}

export async function validateRangeRehydration(
  symbol: string,
  timeframe: string,
  caseId?: string | null,
): Promise<RangeRehydrationListResult> {
  const api = getElectronApiBridge()?.ranges;
  if (!api?.list) {
    return {
      ok: false,
      databasePath: '',
      ranges: [],
      rehydration: null,
      error: 'window.electronAPI.ranges.list is not available (preload bridge missing)',
    };
  }

  return api.list({
    symbol: normaliseRehydrationSymbol(symbol),
    timeframe: normaliseRehydrationTimeframe(timeframe),
    case_id: caseId ?? undefined,
    validateRehydration: true,
  });
}

export function shouldClearRangeUiFromRehydration(result: RangeRehydrationListResult | null | undefined): boolean {
  return Boolean(result?.rehydration?.should_clear_ui);
}

export function ghostRangeUiClearMessage(symbol: string, timeframe: string): string {
  return `Cleared stale range UI for ${normaliseRehydrationSymbol(symbol)} ${normaliseRehydrationTimeframe(timeframe)} (local cache context mismatch).`;
}
