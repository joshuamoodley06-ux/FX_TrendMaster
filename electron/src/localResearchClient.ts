export type LocalResearchRunResult = {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  error?: string;
  command?: string;
  parsed?: unknown;
};

export type LocalResearchPaths = {
  ok: boolean;
  backendDir: string;
  databasePath: string;
  researchFolder?: string;
  scripts: {
    historicalRangeScan: string;
    batchRangePromote: string;
    detectorPerformance: string;
  };
};

export type LocalResearchDatabaseStatus = {
  ok: boolean;
  databasePath: string;
  researchFolder?: string;
  defaultDatabasePath?: string;
  exists: boolean;
  readable: boolean;
  totalCandles?: number | null;
  w1Candles?: number | null;
  suggestions?: number | null;
  mapRanges?: number | null;
  readyForWeeklyScan?: boolean;
  error?: string;
  canceled?: boolean;
};

export type HistoricalRangeScanRequest = {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom: string;
  dateTo: string;
  /** Candles-only historical chain (experimental — not default for Weekly Research). */
  chain?: boolean;
  /** Advanced: use ACTIVE map_ranges seed with chain mode. */
  useManualSeed?: boolean;
  /** Advanced: seed from promoted APPROVED/EDITED map_ranges when available. */
  seedPolicy?: 'reviewed_truth_only';
  sample?: number;
  dryRun?: boolean;
  detectionRunId?: string;
  candidateKind?: string;
  limit?: number;
  candleLimit?: number;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type BatchRangePromoteRequest = {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom?: string;
  dateTo?: string;
  candidateKind?: string;
  status?: string;
  detectorVersion?: string;
  detectionRunId?: string;
  confirm?: boolean;
  userConfirmed?: boolean;
  json?: boolean;
  summaryOnly?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type DetectorPerformanceRequest = {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  json?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type RunDetectorLocalRequest = {
  payload: Record<string, unknown>;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type ListDetectorSuggestionsLocalRequest = {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId?: string;
  replayUntilMs?: number;
  limit?: number;
  status?: string;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type ListDetectorRunLocalRequest = {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId: string;
  candidateKind?: string;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type ReviewSuggestionLocalRequest = {
  suggestionId: string;
  action: 'APPROVE' | 'EDIT' | 'REJECT';
  edits?: Record<string, unknown>;
  errorCategory?: string;
  notes?: string;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type ExportDetectionAuditLocalRequest = {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId: string;
  candidateKind?: string;
  outPath?: string;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type RandomRangeAuditRequest = {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  source?: 'suggestions' | 'confirmed_ranges';
  detectionRunId?: string;
  json?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type RecordAuditVerdictRequest = {
  suggestionId: string;
  action: 'AUDIT_PASS' | 'AUDIT_FAIL';
  notes?: string;
  json?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type PullVpsCandlesRequest = {
  baseUrl?: string;
  symbol?: string;
  timeframes?: string;
  limit?: number;
  json?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type LocalResearchSeedRequest = {
  symbol?: string;
  command: 'check' | 'list' | 'create-manual' | 'activate' | 'diagnose-scan';
  rangeHigh?: number;
  rangeLow?: number;
  rangeHighTime?: string;
  rangeLowTime?: string;
  rangeId?: number;
  detectionRunId?: string;
  limit?: number;
  json?: boolean;
  databasePath?: string;
  backendDir?: string;
  pythonPath?: string;
};

export type WeeklyScanDiagnose = {
  hint?: string;
  hasSeed?: boolean;
  seed?: WeeklySeedInfo | null;
  lifecycleStateCounts?: Record<string, number>;
  reasonTextCounts?: Record<string, number>;
  closestWeek?: {
    lifecycle_state?: string;
    reason_text?: string;
    replay_until_time?: string;
    broken_boundary?: string;
    bos_candle_index?: number;
    reclaim_candle_index?: number;
  } | null;
};

export type WeeklySeedInfo = {
  id: number;
  range_high_price: number;
  range_low_price: number;
  range_scale?: string | null;
  status?: string | null;
  source?: string | null;
  user_action_at_confirm?: string | null;
};

export type WeeklySeedCheck = {
  ok: boolean;
  has_seed: boolean;
  count?: number;
  seed?: WeeklySeedInfo | null;
  error?: string;
};

export type WeeklySeedRangeRow = {
  id: number;
  status?: string | null;
  range_high_price?: number | null;
  range_low_price?: number | null;
  range_high_time?: string | null;
  range_low_time?: string | null;
  range_scale?: string | null;
  source?: string | null;
  user_action_at_confirm?: string | null;
  selectable: boolean;
};

export type CandleRange = {
  from?: string;
  to?: string;
  limit?: number;
};

export type LocalCandleRow = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  source?: string;
  synced_at?: string | null;
  is_closed?: boolean;
};

export type CandlesFetchResult = {
  ok: boolean;
  symbol: string;
  timeframe: string;
  source: 'local_sqlite' | 'cache';
  databasePath: string;
  candles: LocalCandleRow[];
  error?: string;
};

export type CandlesStatusResult = {
  ok: boolean;
  databasePath: string;
  exists: boolean;
  readable: boolean;
  totalCandles?: number | null;
  symbolCandles?: number | null;
  symbol?: string;
  timeframe?: string;
  firstTime?: string | null;
  lastTime?: string | null;
  syncState?: CandleSyncStateRow | null;
  error?: string;
};

export type UpsertCandleRow = {
  symbol?: string;
  timeframe?: string;
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  source?: string;
  is_closed?: number | boolean;
};

export type CandleSyncStateRow = {
  symbol: string;
  timeframe: string;
  last_time?: string | null;
  bar_count?: number;
  last_sync_at?: string | null;
  last_mode?: string | null;
  last_error?: string | null;
};

export type CandlesUpsertRequest = {
  candles: UpsertCandleRow[];
  symbol?: string;
  timeframe?: string;
  source?: string;
  syncState?: CandleSyncStateRow;
  syncStates?: CandleSyncStateRow[];
};

export type CandlesUpsertResult = {
  ok: boolean;
  databasePath: string;
  upserted: number;
  skipped: number;
  error?: string;
};

export type CandleDataSource = 'local_sqlite' | 'cache' | 'remote_vps';

export type CandleSyncStatus = {
  phase: 'idle' | 'loading' | 'ready' | 'error';
  fetchTarget?: 'local' | 'remote';
  source?: CandleDataSource;
  databasePath?: string;
  localDb?: CandlesStatusResult | null;
  error?: string;
  lastLoadedAt?: string;
};

export type ElectronApiCandlesBridge = {
  fetch: (symbol: string, timeframe: string, range?: CandleRange) => Promise<CandlesFetchResult>;
  status: (symbol?: string, timeframe?: string) => Promise<CandlesStatusResult>;
  upsert: (args: CandlesUpsertRequest) => Promise<CandlesUpsertResult>;
  pullFromVps: (args: { symbol: string; timeframes: string; databasePath?: string }) => Promise<LocalResearchRunResult>;
};

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

export type MappingRangesListResult = {
  ok: boolean;
  databasePath: string;
  symbol?: string;
  timeframe?: string;
  case_id?: string | null;
  ranges: CachedMappingRangeRow[];
  rehydration?: RangeRehydrationReport | null;
  error?: string;
};

export type ElectronApiRangesBridge = {
  validate: (args: Record<string, unknown>) => Promise<Record<string, unknown>>;
  upsert: (args: Record<string, unknown>) => Promise<Record<string, unknown>>;
  list: (args: {
    symbol?: string;
    timeframe?: string;
    case_id?: string;
    validateRehydration?: boolean;
  }) => Promise<MappingRangesListResult>;
};

export type ElectronApiBridge = {
  candles?: ElectronApiCandlesBridge;
  ranges?: ElectronApiRangesBridge;
};

export function basenamePath(value?: string): string {
  if (!value) return '';
  const normalized = value.replace(/\\/g, '/');
  const parts = normalized.split('/');
  return parts[parts.length - 1] || value;
}

export function formatCandleDataSourceLabel(source?: CandleDataSource): string {
  if (source === 'local_sqlite') return 'Local SQLite';
  if (source === 'cache') return 'Local cache';
  if (source === 'remote_vps') return 'VPS remote';
  return 'Unknown source';
}

export type LocalResearchBridge = {
  getPaths: () => Promise<LocalResearchPaths>;
  getDatabaseStatus: (args?: { symbol?: string; timeframe?: string; databasePath?: string }) => Promise<LocalResearchDatabaseStatus>;
  pickDatabaseFile: () => Promise<LocalResearchDatabaseStatus>;
  setDatabasePath: (args: { databasePath: string }) => Promise<LocalResearchDatabaseStatus>;
  openResearchFolder: () => Promise<{ ok: boolean; folder?: string; error?: string }>;
  pullVpsCandles: (args: PullVpsCandlesRequest) => Promise<LocalResearchRunResult>;
  runLocalResearchSeed: (args: LocalResearchSeedRequest) => Promise<LocalResearchRunResult>;
  runHistoricalRangeScan: (args: HistoricalRangeScanRequest) => Promise<LocalResearchRunResult>;
  runBatchRangePromote: (args: BatchRangePromoteRequest) => Promise<LocalResearchRunResult>;
  runDetectorPerformance: (args: DetectorPerformanceRequest) => Promise<LocalResearchRunResult>;
  runDetectorLocal: (args: RunDetectorLocalRequest) => Promise<LocalResearchRunResult>;
  listDetectorSuggestions: (args: ListDetectorSuggestionsLocalRequest) => Promise<LocalResearchRunResult>;
  listDetectorRun: (args: ListDetectorRunLocalRequest) => Promise<LocalResearchRunResult>;
  latestDetectorRun: (args: Omit<ListDetectorRunLocalRequest, 'detectionRunId'>) => Promise<LocalResearchRunResult>;
  reviewSuggestionLocal: (args: ReviewSuggestionLocalRequest) => Promise<LocalResearchRunResult>;
  exportDetectionAudit: (args: ExportDetectionAuditLocalRequest) => Promise<LocalResearchRunResult>;
  runRandomRangeAudit: (args: RandomRangeAuditRequest) => Promise<LocalResearchRunResult>;
  runRecordAuditVerdict: (args: RecordAuditVerdictRequest) => Promise<LocalResearchRunResult>;
};

export const DEFAULT_W1_2025 = {
  symbol: 'XAUUSD',
  timeframe: 'W1',
  layer: 'WEEKLY',
  dateFrom: '2025-01-01',
  dateTo: '2025-12-31',
} as const;

export type PromoteScope = {
  symbol: string;
  timeframe: string;
  layer: string;
  dateFrom: string;
  dateTo: string;
};

export const CONFIRM_PROMOTE_PHRASE = 'PROMOTE 2025 W1';

export type BatchPromoteParsed = {
  ok?: boolean;
  dry_run?: boolean;
  counts?: {
    would_promote?: number;
    pending_candidates_found?: number;
    promoted?: number;
    errors?: number;
  };
  filters?: {
    symbol?: string;
    source_timeframe?: string;
    structure_layer?: string;
  };
  date_range?: {
    from?: string;
    to?: string;
  };
};

export type DryRunStamp = {
  scopeKey: string;
  databasePath: string;
  wouldPromote: number;
  completedAt: string;
};

export function promoteScopeKey(scope: PromoteScope): string {
  return [
    scope.symbol.toUpperCase(),
    scope.timeframe.toUpperCase(),
    scope.layer.toUpperCase(),
    scope.dateFrom,
    scope.dateTo,
  ].join('|');
}

export function promoteScopeFromArgs(args: {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom?: string;
  dateTo?: string;
}): PromoteScope {
  return {
    symbol: String(args.symbol || DEFAULT_W1_2025.symbol).toUpperCase(),
    timeframe: String(args.timeframe || DEFAULT_W1_2025.timeframe).toUpperCase(),
    layer: String(args.layer || DEFAULT_W1_2025.layer).toUpperCase(),
    dateFrom: String(args.dateFrom || DEFAULT_W1_2025.dateFrom),
    dateTo: String(args.dateTo || DEFAULT_W1_2025.dateTo),
  };
}

export function extractBatchPromoteParsed(parsed: unknown): BatchPromoteParsed | null {
  if (!parsed || typeof parsed !== 'object') return null;
  return parsed as BatchPromoteParsed;
}

export function extractWouldPromote(parsed: unknown): number | null {
  const payload = extractBatchPromoteParsed(parsed);
  const count = payload?.counts?.would_promote;
  return typeof count === 'number' && Number.isFinite(count) ? count : null;
}

export function isSuccessfulDryRun(result: LocalResearchRunResult): boolean {
  if (!result.ok) return false;
  const payload = extractBatchPromoteParsed(result.parsed);
  if (!payload) return false;
  if (payload.dry_run === false) return false;
  if (payload.ok === false) return false;
  return extractWouldPromote(result.parsed) !== null;
}

export function dryRunMatchesScope(
  stamp: DryRunStamp | null,
  scope: PromoteScope,
  databasePath: string,
): boolean {
  if (!stamp) return false;
  if (!databasePath) return false;
  return stamp.scopeKey === promoteScopeKey(scope) && stamp.databasePath === databasePath;
}

export function buildDryRunStamp(
  scope: PromoteScope,
  databasePath: string,
  result: LocalResearchRunResult,
): DryRunStamp | null {
  if (!isSuccessfulDryRun(result)) return null;
  const wouldPromote = extractWouldPromote(result.parsed);
  if (wouldPromote === null) return null;
  return {
    scopeKey: promoteScopeKey(scope),
    databasePath,
    wouldPromote,
    completedAt: new Date().toISOString(),
  };
}

declare global {
  interface Window {
    localResearch?: LocalResearchBridge;
    electronAPI?: ElectronApiBridge;
  }
}

export function getLocalResearchBridge(): LocalResearchBridge | null {
  return window.localResearch ?? null;
}

export function getElectronApiBridge(): ElectronApiBridge | null {
  return window.electronAPI ?? null;
}

export function candleRangeFromWindow(window?: { start?: string; end?: string } | null): CandleRange {
  if (!window?.start && !window?.end) return { limit: 8000 };
  return { from: window.start, to: window.end, limit: 8000 };
}

export async function fetchLocalCandles(
  symbol: string,
  timeframe: string,
  range?: CandleRange,
): Promise<CandlesFetchResult> {
  const api = getElectronApiBridge()?.candles;
  if (!api?.fetch) {
    return {
      ok: false,
      symbol,
      timeframe,
      source: 'local_sqlite',
      databasePath: '',
      candles: [],
      error: 'window.electronAPI.candles.fetch is not available (preload bridge missing)',
    };
  }
  return api.fetch(symbol, timeframe, range);
}

export async function getLocalCandlesStatus(
  symbol?: string,
  timeframe?: string,
): Promise<CandlesStatusResult> {
  const api = getElectronApiBridge()?.candles;
  if (!api?.status) {
    return {
      ok: false,
      databasePath: '',
      exists: false,
      readable: false,
      error: 'window.electronAPI.candles.status is not available (preload bridge missing)',
    };
  }
  return api.status(symbol, timeframe);
}

export async function upsertLocalCandles(
  args: CandlesUpsertRequest,
): Promise<CandlesUpsertResult> {
  const api = getElectronApiBridge()?.candles;
  if (!api?.upsert) {
    return {
      ok: false,
      databasePath: '',
      upserted: 0,
      skipped: 0,
      error: 'window.electronAPI.candles.upsert is not available (preload bridge missing)',
    };
  }
  return api.upsert(args);
}

export async function getLocalResearchDatabaseStatus(
  args?: { symbol?: string; timeframe?: string; databasePath?: string },
): Promise<LocalResearchDatabaseStatus> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      databasePath: '',
      exists: false,
      readable: false,
      readyForWeeklyScan: false,
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.getDatabaseStatus(args);
}

export async function pickLocalResearchDatabaseFile(): Promise<LocalResearchDatabaseStatus> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      databasePath: '',
      exists: false,
      readable: false,
      readyForWeeklyScan: false,
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.pickDatabaseFile();
}

export async function openLocalResearchFolder(): Promise<{ ok: boolean; folder?: string; error?: string }> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return { ok: false, error: 'window.localResearch is not available (preload bridge missing)' };
  }
  return bridge.openResearchFolder();
}

export async function pullVpsCandlesLocal(
  args: PullVpsCandlesRequest = {},
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.pullVpsCandles({
    symbol: 'XAUUSD',
    timeframes: 'W1,D1,H4,H1,M15,M5',
    limit: 8000,
    json: true,
    ...args,
  });
}

export async function runLocalResearchSeedLocal(
  args: LocalResearchSeedRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runLocalResearchSeed({
    symbol: 'XAUUSD',
    json: true,
    ...args,
  });
}

export async function runHistoricalRangeScanLocal(
  args: HistoricalRangeScanRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runHistoricalRangeScan(args);
}

export async function runBatchRangePromoteLocal(
  args: BatchRangePromoteRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runBatchRangePromote(args);
}

export async function runDetectorPerformanceLocal(
  args: DetectorPerformanceRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runDetectorPerformance(args);
}

export async function runDetectorLocalResearch(
  args: RunDetectorLocalRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.runDetectorLocal) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.runDetectorLocal is not available',
    };
  }
  return bridge.runDetectorLocal(args);
}

export async function listDetectorSuggestionsLocalResearch(
  args: ListDetectorSuggestionsLocalRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.listDetectorSuggestions) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.listDetectorSuggestions is not available',
    };
  }
  return bridge.listDetectorSuggestions(args);
}

export async function runRandomRangeAuditLocal(
  args: RandomRangeAuditRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runRandomRangeAudit(args);
}

export async function runRecordAuditVerdictLocal(
  args: RecordAuditVerdictRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch is not available (preload bridge missing)',
    };
  }
  return bridge.runRecordAuditVerdict(args);
}

export async function latestDetectorRunLocalResearch(
  args: Omit<ListDetectorRunLocalRequest, 'detectionRunId'>,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.latestDetectorRun) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.latestDetectorRun is not available',
    };
  }
  return bridge.latestDetectorRun(args);
}

export async function listDetectorRunLocalResearch(
  args: ListDetectorRunLocalRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.listDetectorRun) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.listDetectorRun is not available',
    };
  }
  return bridge.listDetectorRun(args);
}

export async function reviewSuggestionLocalResearch(
  args: ReviewSuggestionLocalRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.reviewSuggestionLocal) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.reviewSuggestionLocal is not available',
    };
  }
  return bridge.reviewSuggestionLocal(args);
}

export async function exportDetectionAuditLocalResearch(
  args: ExportDetectionAuditLocalRequest,
): Promise<LocalResearchRunResult> {
  const bridge = getLocalResearchBridge();
  if (!bridge?.exportDetectionAudit) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'window.localResearch.exportDetectionAudit is not available',
    };
  }
  return bridge.exportDetectionAudit(args);
}
