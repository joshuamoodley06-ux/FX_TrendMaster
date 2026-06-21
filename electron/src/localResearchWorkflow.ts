import {
  DEFAULT_W1_2025,
  type LocalResearchRunResult,
  type WeeklySeedCheck,
  type WeeklySeedRangeRow,
  runBatchRangePromoteLocal,
  runHistoricalRangeScanLocal,
  runLocalResearchSeedLocal,
  runRandomRangeAuditLocal,
  runRecordAuditVerdictLocal,
} from './localResearchClient';
import type { RangeAuditSample } from './reviewCandidateClient';
import type { WeeklyScanDiagnose } from './localResearchClient';
import { parseHistoricalScanOutput } from './localPythonOutput';

export const WEEKLY_RESEARCH_AUDIT_TARGET = 20;

export type WeeklyScanSummary = {
  rangesFound: number;
  noValidRange: number;
  candlesScanned: number;
  detectionRunId?: string | null;
};

export type WeeklyResearchSummary = {
  audited: number;
  pass: number;
  fail: number;
  skipped: number;
  rangesFound: number;
  promoted: number;
};

export type WeeklyResearchPhase =
  | 'idle'
  | 'seed_setup'
  | 'scanning'
  | 'promote_prompt'
  | 'promoting'
  | 'audit'
  | 'summary'
  | 'error';

export function weeklySeedCheckFromResult(result: LocalResearchRunResult): WeeklySeedCheck | null {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return null;
  const parsed = result.parsed as WeeklySeedCheck;
  if (typeof parsed.has_seed !== 'boolean') return null;
  return parsed;
}

export function weeklySeedRangesFromResult(result: LocalResearchRunResult): WeeklySeedRangeRow[] {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return [];
  const ranges = (result.parsed as { ranges?: WeeklySeedRangeRow[] }).ranges;
  return Array.isArray(ranges) ? ranges : [];
}

export async function checkWeeklySeed(
  symbol: string,
  databasePath?: string,
): Promise<LocalResearchRunResult> {
  return runLocalResearchSeedLocal({ command: 'check', symbol, databasePath });
}

export async function listWeeklySeedRanges(
  symbol: string,
  databasePath?: string,
  limit = 100,
): Promise<LocalResearchRunResult> {
  return runLocalResearchSeedLocal({ command: 'list', symbol, databasePath, limit });
}

export async function createManualWeeklySeed(args: {
  symbol: string;
  rangeHigh: number;
  rangeLow: number;
  rangeHighTime?: string;
  rangeLowTime?: string;
  databasePath?: string;
}): Promise<LocalResearchRunResult> {
  return runLocalResearchSeedLocal({
    command: 'create-manual',
    symbol: args.symbol,
    rangeHigh: args.rangeHigh,
    rangeLow: args.rangeLow,
    rangeHighTime: args.rangeHighTime,
    rangeLowTime: args.rangeLowTime,
    databasePath: args.databasePath,
  });
}

export async function activateWeeklySeed(args: {
  symbol: string;
  rangeId: number;
  databasePath?: string;
}): Promise<LocalResearchRunResult> {
  return runLocalResearchSeedLocal({
    command: 'activate',
    symbol: args.symbol,
    rangeId: args.rangeId,
    databasePath: args.databasePath,
  });
}

export function scanDiagnoseFromResult(result: LocalResearchRunResult): WeeklyScanDiagnose | null {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return null;
  const parsed = result.parsed as Record<string, unknown>;
  if (parsed.ok === false) return null;
  return {
    hint: typeof parsed.hint === 'string' ? parsed.hint : undefined,
    hasSeed: typeof parsed.has_seed === 'boolean' ? parsed.has_seed : undefined,
    seed: (parsed.seed as WeeklyScanDiagnose['seed']) ?? null,
    lifecycleStateCounts: parsed.lifecycle_state_counts as Record<string, number> | undefined,
    reasonTextCounts: parsed.reason_text_counts as Record<string, number> | undefined,
    closestWeek: (parsed.closest_week as WeeklyScanDiagnose['closestWeek']) ?? null,
  };
}

export async function diagnoseWeeklyScan(args: {
  symbol: string;
  detectionRunId: string;
  databasePath?: string;
}): Promise<LocalResearchRunResult> {
  return runLocalResearchSeedLocal({
    command: 'diagnose-scan',
    symbol: args.symbol,
    detectionRunId: args.detectionRunId,
    databasePath: args.databasePath,
  });
}

export function scanSummaryFromResult(result: LocalResearchRunResult): WeeklyScanSummary | null {
  if (!result.ok) return null;
  const parsed = result.parsed && typeof result.parsed === 'object'
    ? result.parsed as Record<string, unknown>
    : parseHistoricalScanOutput(result.stdout);
  const rangesFound = Number(
    parsed.range_candidate_count
    ?? parsed.chain_candidates
    ?? parsed.suggestions_created
    ?? 0,
  );
  const noValidRange = Number(parsed.no_valid_range_count ?? 0);
  const candlesScanned = Number(parsed.candles_scanned ?? 0);
  const detectionRunId = typeof parsed.detection_run_id === 'string' ? parsed.detection_run_id : null;
  if (!Number.isFinite(rangesFound)) return null;
  return {
    rangesFound,
    noValidRange: Number.isFinite(noValidRange) ? noValidRange : 0,
    candlesScanned: Number.isFinite(candlesScanned) ? candlesScanned : 0,
    detectionRunId,
  };
}

export function promotedCountFromResult(result: LocalResearchRunResult): number {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return 0;
  const counts = (result.parsed as { counts?: { promoted?: number; would_promote?: number } }).counts;
  return Number(counts?.promoted ?? counts?.would_promote ?? 0) || 0;
}

export function auditSamplesFromResult(result: LocalResearchRunResult): RangeAuditSample[] {
  if (!result.ok || !result.parsed || typeof result.parsed !== 'object') return [];
  const samples = (result.parsed as { samples?: RangeAuditSample[] }).samples;
  return Array.isArray(samples) ? samples : [];
}

export function suggestionIdFromSample(sample: RangeAuditSample | null | undefined): string | null {
  if (!sample) return null;
  return sample.suggestion_id || (sample.source === 'suggestions' ? sample.id || null : null);
}

export async function runWeeklyHistoricalScan(
  databasePath?: string,
  options?: { useManualSeed?: boolean; experimentalChain?: boolean; reviewedTruthSeed?: boolean },
): Promise<LocalResearchRunResult> {
  return runHistoricalRangeScanLocal({
    ...DEFAULT_W1_2025,
    databasePath,
    chain: options?.experimentalChain === true,
    useManualSeed: options?.useManualSeed,
    ...(options?.reviewedTruthSeed ? { seedPolicy: 'reviewed_truth_only' as const } : {}),
  });
}

export async function loadWeeklyScanCandidates(
  detectionRunId: string,
  databasePath?: string,
  limit = 50,
  source: 'suggestions' | 'confirmed_ranges' = 'suggestions',
): Promise<LocalResearchRunResult> {
  return runRandomRangeAuditLocal({
    ...DEFAULT_W1_2025,
    limit,
    source,
    detectionRunId,
    json: true,
    databasePath,
  });
}

export async function runWeeklyPromote(
  databasePath?: string,
  detectionRunId?: string | null,
): Promise<LocalResearchRunResult> {
  return runBatchRangePromoteLocal({
    ...DEFAULT_W1_2025,
    confirm: true,
    userConfirmed: true,
    json: true,
    summaryOnly: true,
    detectionRunId: detectionRunId || undefined,
    databasePath,
  });
}

export async function loadWeeklyAuditSamples(
  limit = WEEKLY_RESEARCH_AUDIT_TARGET,
  databasePath?: string,
): Promise<LocalResearchRunResult> {
  return runRandomRangeAuditLocal({
    ...DEFAULT_W1_2025,
    limit,
    source: 'confirmed_ranges',
    json: true,
    databasePath,
  });
}

export async function recordWeeklyAuditVerdict(
  suggestionId: string,
  pass: boolean,
  databasePath?: string,
): Promise<LocalResearchRunResult> {
  return runRecordAuditVerdictLocal({
    suggestionId,
    action: pass ? 'AUDIT_PASS' : 'AUDIT_FAIL',
    notes: pass ? 'weekly research visual pass' : 'weekly research visual fail',
    json: true,
    databasePath,
  });
}

export function friendlyError(result: LocalResearchRunResult): string {
  if (result.error) return result.error;
  if (result.stderr?.trim()) return result.stderr.trim().split('\n')[0];
  return 'Something went wrong. Please try again.';
}
