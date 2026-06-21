/**
 * Local Python research runner — Electron main-process / Node only.
 *
 * Spawns backend CLI scripts via child_process (not FastAPI).
 * Do not import from renderer; use IPC bridge when UI wiring lands.
 */

import { spawn, type ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import {
  parseBatchPromoteOutput,
  parseDetectorPerformanceOutput,
  parseHistoricalScanOutput,
  parseJsonOutput,
  parseRandomAuditOutput,
} from './localPythonOutput';
import { DEFAULT_VPS_BASE_URL } from './vpsConfig';

export { DEFAULT_VPS_BASE_URL } from './vpsConfig';

export type SpawnFn = (
  command: string,
  args: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv; windowsHide?: boolean },
) => ChildProcessWithoutNullStreams;

export type LocalRunnerBaseOptions = {
  pythonPath?: string;
  backendDir?: string;
  databasePath?: string;
  rawMappingDbPath?: string;
  spawnFn?: SpawnFn;
  timeoutMs?: number;
};

export type HistoricalRangeScanArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom: string;
  dateTo: string;
  chain?: boolean;
  useManualSeed?: boolean;
  /** Advanced: promoted map_ranges beat in-scan raw candidate roll. */
  seedPolicy?: 'reviewed_truth_only';
  sample?: number;
  dryRun?: boolean;
  detectionRunId?: string;
  candidateKind?: string;
  limit?: number;
  candleLimit?: number;
};

export type BatchRangePromoteArgs = LocalRunnerBaseOptions & {
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
  json?: boolean;
  summaryOnly?: boolean;
};

export type DetectorPerformanceArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  json?: boolean;
};

export type RandomRangeAuditArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  timeframe?: string;
  layer?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  source?: 'suggestions' | 'confirmed_ranges';
  detectionRunId?: string;
  json?: boolean;
};

export type RecordAuditVerdictArgs = LocalRunnerBaseOptions & {
  suggestionId: string;
  action: 'AUDIT_PASS' | 'AUDIT_FAIL';
  notes?: string;
  json?: boolean;
};

export type PullVpsCandlesArgs = LocalRunnerBaseOptions & {
  baseUrl?: string;
  symbol?: string;
  timeframes?: string;
  limit?: number;
  json?: boolean;
};

export type LocalResearchSeedArgs = LocalRunnerBaseOptions & {
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
};

export type RunDetectorLocalArgs = LocalRunnerBaseOptions & {
  payload: Record<string, unknown>;
  timeoutMs?: number;
};

export type ListDetectorSuggestionsLocalArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId?: string;
  replayUntilMs?: number;
  limit?: number;
  status?: string;
};

export type ListDetectorRunLocalArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId: string;
  candidateKind?: string;
};

export type ReviewSuggestionLocalArgs = LocalRunnerBaseOptions & {
  suggestionId: string;
  action: 'APPROVE' | 'EDIT' | 'REJECT';
  edits?: Record<string, unknown>;
  errorCategory?: string;
  notes?: string;
};

export type ExportDetectionAuditLocalArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  detectionRunId: string;
  candidateKind?: string;
  outPath?: string;
};

export type LatestDetectorRunLocalArgs = LocalRunnerBaseOptions & {
  symbol?: string;
  structureLayer?: string;
  sourceTimeframe?: string;
  candidateKind?: string;
};

export const LAST_DETECTION_RUN_STORAGE_KEY = 'fx_tm_last_detection_run_id';

export type LocalPythonScriptSpec = {
  script: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
  pythonPath: string;
};

export type LocalPythonRunResult = {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  error?: string;
  command: string;
  parsed?: unknown;
};

const DEFAULT_PYTHON = process.env.FXTM_PYTHON || 'python';

export function resolveBackendDir(explicit?: string): string {
  if (explicit) return path.resolve(explicit);
  if (process.env.FXTM_BACKEND_DIR) return path.resolve(process.env.FXTM_BACKEND_DIR);

  const candidates = [
    path.resolve(process.cwd(), 'backend'),
    path.resolve(process.cwd(), '../backend'),
    path.resolve(__dirname, '../../backend'),
    path.resolve(__dirname, '../../../backend'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, 'historical_range_scan.py'))) {
      return candidate;
    }
  }
  return path.resolve(process.cwd(), '../backend');
}

export function resolveDatabasePath(explicit?: string): string {
  if (explicit) return path.resolve(explicit);
  if (process.env.DATABASE_PATH) return path.resolve(process.env.DATABASE_PATH);

  const home = process.env.USERPROFILE || process.env.HOME || '';
  if (home) {
    return path.join(home, 'Documents', 'FXTM_Research', 'raw_mapping_v159.db');
  }
  return path.resolve(resolveBackendDir(), 'data', 'raw_mapping_v159.db');
}

export function buildLocalPythonEnv(options: {
  backendDir: string;
  databasePath?: string;
  rawMappingDbPath?: string;
  extra?: Record<string, string | undefined>;
}): NodeJS.ProcessEnv {
  const backendDir = path.resolve(options.backendDir);
  const dbPath = path.resolve(options.databasePath || resolveDatabasePath());
  const rawPath = path.resolve(options.rawMappingDbPath || dbPath);

  return {
    ...process.env,
    PYTHONPATH: backendDir,
    PYTHONUNBUFFERED: '1',
    DATABASE_PATH: dbPath,
    RAW_MAPPING_DB_PATH: rawPath,
    MARKET_MEMORY_DB_PATH: dbPath,
    DETECTOR_RANGE_MODE: 'doctrine_v2',
    DETECTOR_RANGE_SCALE_MODE: 'generic',
    FXTM_BACKEND_DIR: backendDir,
    ...options.extra,
  };
}

function pushArg(args: string[], flag: string, value: string | number | undefined | null) {
  if (value === undefined || value === null || value === '') return;
  args.push(flag, String(value));
}

export function buildHistoricalRangeScanCommand(args: HistoricalRangeScanArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'historical_range_scan.py'),
    '--symbol', args.symbol || 'XAUUSD',
    '--timeframe', args.timeframe || 'W1',
    '--from', args.dateFrom,
    '--to', args.dateTo,
  ];
  pushArg(cliArgs, '--layer', args.layer);
  pushArg(cliArgs, '--sample', args.sample);
  pushArg(cliArgs, '--detection-run-id', args.detectionRunId);
  pushArg(cliArgs, '--candidate-kind', args.candidateKind);
  pushArg(cliArgs, '--limit', args.limit);
  pushArg(cliArgs, '--candle-limit', args.candleLimit);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.chain) cliArgs.push('--chain');
  if (args.useManualSeed) cliArgs.push('--use-manual-seed');
  if (args.seedPolicy === 'reviewed_truth_only') {
    pushArg(cliArgs, '--seed-policy', 'reviewed_truth_only');
  }
  if (args.dryRun) cliArgs.push('--dry-run');

  return {
    script: 'historical_range_scan.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildBatchRangePromoteCommand(args: BatchRangePromoteArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'batch_range_promote.py'),
    '--symbol', args.symbol || 'XAUUSD',
    '--timeframe', args.timeframe || 'W1',
  ];
  pushArg(cliArgs, '--layer', args.layer);
  pushArg(cliArgs, '--from', args.dateFrom);
  pushArg(cliArgs, '--to', args.dateTo);
  pushArg(cliArgs, '--candidate-kind', args.candidateKind);
  pushArg(cliArgs, '--status', args.status);
  pushArg(cliArgs, '--detector-version', args.detectorVersion);
  pushArg(cliArgs, '--detection-run-id', args.detectionRunId);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.confirm) cliArgs.push('--confirm');
  if (args.summaryOnly) cliArgs.push('--summary-only');
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'batch_range_promote.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildDetectorPerformanceCommand(args: DetectorPerformanceArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [path.join(backendDir, 'detector_performance.py')];
  pushArg(cliArgs, '--symbol', args.symbol);
  pushArg(cliArgs, '--structure-layer', args.structureLayer);
  pushArg(cliArgs, '--source-timeframe', args.sourceTimeframe);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'detector_performance.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildRandomRangeAuditCommand(args: RandomRangeAuditArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'random_range_audit.py'),
    '--symbol', args.symbol || 'XAUUSD',
    '--timeframe', args.timeframe || 'W1',
  ];
  pushArg(cliArgs, '--layer', args.layer);
  pushArg(cliArgs, '--from', args.dateFrom);
  pushArg(cliArgs, '--to', args.dateTo);
  pushArg(cliArgs, '--limit', args.limit);
  pushArg(cliArgs, '--source', args.source);
  pushArg(cliArgs, '--detection-run-id', args.detectionRunId);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'random_range_audit.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildRecordAuditVerdictCommand(args: RecordAuditVerdictArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'record_audit_verdict.py'),
    '--suggestion-id', args.suggestionId,
    '--action', args.action,
  ];
  pushArg(cliArgs, '--notes', args.notes);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'record_audit_verdict.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildPullVpsCandlesCommand(args: PullVpsCandlesArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'pull_vps_candles.py'),
    '--base-url', args.baseUrl || DEFAULT_VPS_BASE_URL,
    '--symbol', args.symbol || 'XAUUSD',
    '--timeframes', args.timeframes || 'W1,D1,H4,H1,M15,M5',
  ];
  pushArg(cliArgs, '--limit', args.limit);
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'pull_vps_candles.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildLocalResearchSeedCommand(args: LocalResearchSeedArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'local_research_seed.py'),
    args.command,
    '--symbol', args.symbol || 'XAUUSD',
  ];
  pushArg(cliArgs, '--db', args.databasePath);
  if (args.command === 'create-manual') {
    pushArg(cliArgs, '--range-high', args.rangeHigh);
    pushArg(cliArgs, '--range-low', args.rangeLow);
    pushArg(cliArgs, '--range-high-time', args.rangeHighTime);
    pushArg(cliArgs, '--range-low-time', args.rangeLowTime);
  }
  if (args.command === 'activate') {
    pushArg(cliArgs, '--range-id', args.rangeId);
  }
  if (args.command === 'list') {
    pushArg(cliArgs, '--limit', args.limit);
  }
  if (args.command === 'diagnose-scan') {
    pushArg(cliArgs, '--detection-run-id', args.detectionRunId);
  }
  if (args.json !== false) cliArgs.push('--json');

  return {
    script: 'local_research_seed.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

function formatCommand(spec: LocalPythonScriptSpec): string {
  return `${spec.pythonPath} ${spec.args.join(' ')}`;
}

export async function spawnLocalPythonScript(
  spec: LocalPythonScriptSpec,
  options?: { spawnFn?: SpawnFn; timeoutMs?: number; parse?: (stdout: string) => unknown },
): Promise<LocalPythonRunResult> {
  const spawnImpl = options?.spawnFn || spawn;
  const command = formatCommand(spec);

  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let spawnError: string | undefined;
    let timedOut = false;

    let child: ChildProcessWithoutNullStreams;
    try {
      child = spawnImpl(spec.pythonPath, spec.args, {
        cwd: spec.cwd,
        env: spec.env,
        windowsHide: true,
      });
    } catch (err) {
      resolve({
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: String(err instanceof Error ? err.message : err),
        command,
      });
      return;
    }

    const timer =
      options?.timeoutMs && options.timeoutMs > 0
        ? setTimeout(() => {
            timedOut = true;
            child.kill('SIGTERM');
          }, options.timeoutMs)
        : null;

    let settled = false;
    const finish = (payload: Omit<LocalPythonRunResult, 'command'> & { command?: string }) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      const parsed = options?.parse && stdout ? options.parse(stdout) : undefined;
      resolve({
        ok: payload.ok,
        exitCode: payload.exitCode,
        stdout,
        stderr,
        error: payload.error,
        command,
        parsed,
      });
    };

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', (err) => {
      spawnError = String(err.message || err);
      finish({
        ok: false,
        exitCode: null,
        error: spawnError,
      });
    });
    child.on('close', (code) => {
      const ok = !spawnError && !timedOut && code === 0;
      finish({
        ok,
        exitCode: code,
        error: spawnError || (timedOut ? `timeout after ${options?.timeoutMs}ms` : undefined),
      });
    });
  });
}

export async function runHistoricalRangeScan(args: HistoricalRangeScanArgs): Promise<LocalPythonRunResult> {
  const spec = buildHistoricalRangeScanCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseHistoricalScanOutput,
  });
}

export async function runBatchRangePromote(args: BatchRangePromoteArgs): Promise<LocalPythonRunResult> {
  const spec = buildBatchRangePromoteCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseBatchPromoteOutput,
  });
}

export async function runDetectorPerformance(args: DetectorPerformanceArgs): Promise<LocalPythonRunResult> {
  const spec = buildDetectorPerformanceCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseDetectorPerformanceOutput,
  });
}

export async function runRandomRangeAudit(args: RandomRangeAuditArgs): Promise<LocalPythonRunResult> {
  const spec = buildRandomRangeAuditCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseRandomAuditOutput,
  });
}

export async function runRecordAuditVerdict(args: RecordAuditVerdictArgs): Promise<LocalPythonRunResult> {
  const spec = buildRecordAuditVerdictCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseBatchPromoteOutput,
  });
}

export async function runPullVpsCandles(args: PullVpsCandlesArgs): Promise<LocalPythonRunResult> {
  const spec = buildPullVpsCandlesCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 180_000,
    parse: parseJsonOutput,
  });
}

export async function runLocalResearchSeed(args: LocalResearchSeedArgs): Promise<LocalPythonRunResult> {
  const spec = buildLocalResearchSeedCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 60_000,
    parse: parseJsonOutput,
  });
}

export function buildRunDetectorLocalCommand(
  args: RunDetectorLocalArgs & { payloadFile: string },
): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'run',
    '--payload-file', args.payloadFile,
  ];
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildListDetectorSuggestionsLocalCommand(
  args: ListDetectorSuggestionsLocalArgs,
): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'list',
    '--symbol', args.symbol || 'XAUUSD',
    '--structure-layer', args.structureLayer || 'WEEKLY',
    '--source-timeframe', args.sourceTimeframe || 'W1',
  ];
  pushArg(cliArgs, '--detection-run-id', args.detectionRunId);
  pushArg(cliArgs, '--replay-until-ms', args.replayUntilMs);
  pushArg(cliArgs, '--limit', args.limit);
  pushArg(cliArgs, '--status', args.status);
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export async function runDetectorLocal(args: RunDetectorLocalArgs): Promise<LocalPythonRunResult> {
  const payloadFile = path.join(
    os.tmpdir(),
    `fx-detector-payload-${Date.now()}-${Math.random().toString(16).slice(2)}.json`,
  );
  fs.writeFileSync(payloadFile, JSON.stringify(args.payload ?? {}), 'utf8');
  try {
    const spec = buildRunDetectorLocalCommand({ ...args, payloadFile });
    return await spawnLocalPythonScript(spec, {
      spawnFn: args.spawnFn,
      timeoutMs: args.timeoutMs ?? 120_000,
      parse: parseJsonOutput,
    });
  } finally {
    try {
      fs.unlinkSync(payloadFile);
    } catch {
      /* ignore */
    }
  }
}

export async function listDetectorSuggestionsLocal(
  args: ListDetectorSuggestionsLocalArgs,
): Promise<LocalPythonRunResult> {
  const spec = buildListDetectorSuggestionsLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 60_000,
    parse: parseJsonOutput,
  });
}

export function buildListDetectorRunLocalCommand(args: ListDetectorRunLocalArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'list-run',
    '--symbol', args.symbol || 'XAUUSD',
    '--structure-layer', args.structureLayer || 'WEEKLY',
    '--source-timeframe', args.sourceTimeframe || 'W1',
    '--detection-run-id', args.detectionRunId,
    '--candidate-kind', args.candidateKind || 'RANGE_CANDIDATE',
  ];
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildReviewSuggestionLocalCommand(args: ReviewSuggestionLocalArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'review',
    '--suggestion-id', args.suggestionId,
    '--action', args.action,
  ];
  if (args.edits && Object.keys(args.edits).length) {
    cliArgs.push('--edits-json', JSON.stringify(args.edits));
  }
  pushArg(cliArgs, '--error-category', args.errorCategory);
  pushArg(cliArgs, '--notes', args.notes);
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export function buildExportDetectionAuditLocalCommand(args: ExportDetectionAuditLocalArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'export-audit',
    '--symbol', args.symbol || 'XAUUSD',
    '--structure-layer', args.structureLayer || 'WEEKLY',
    '--source-timeframe', args.sourceTimeframe || 'W1',
    '--detection-run-id', args.detectionRunId,
    '--candidate-kind', args.candidateKind || 'RANGE_CANDIDATE',
  ];
  pushArg(cliArgs, '--out', args.outPath);
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export async function listDetectorRunLocal(args: ListDetectorRunLocalArgs): Promise<LocalPythonRunResult> {
  const spec = buildListDetectorRunLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 60_000,
    parse: parseJsonOutput,
  });
}

export async function reviewSuggestionLocal(args: ReviewSuggestionLocalArgs): Promise<LocalPythonRunResult> {
  const spec = buildReviewSuggestionLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 60_000,
    parse: parseJsonOutput,
  });
}

export async function exportDetectionAuditLocal(args: ExportDetectionAuditLocalArgs): Promise<LocalPythonRunResult> {
  const spec = buildExportDetectionAuditLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 120_000,
    parse: parseJsonOutput,
  });
}

export function buildLatestDetectorRunLocalCommand(args: LatestDetectorRunLocalArgs): LocalPythonScriptSpec {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    path.join(backendDir, 'run_detector_local.py'),
    '--db', args.databasePath || resolveDatabasePath(),
    'latest-run',
    '--symbol', args.symbol || 'XAUUSD',
    '--structure-layer', args.structureLayer || 'WEEKLY',
    '--source-timeframe', args.sourceTimeframe || 'W1',
    '--candidate-kind', args.candidateKind || 'RANGE_CANDIDATE',
  ];
  return {
    script: 'run_detector_local.py',
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath,
    }),
    pythonPath,
  };
}

export async function latestDetectorRunLocal(args: LatestDetectorRunLocalArgs): Promise<LocalPythonRunResult> {
  const spec = buildLatestDetectorRunLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 60_000,
    parse: parseJsonOutput,
  });
}
