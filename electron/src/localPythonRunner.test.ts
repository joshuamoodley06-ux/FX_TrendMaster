import { EventEmitter } from 'events';
import path from 'path';
import { describe, expect, it } from 'vitest';
import type { ChildProcessWithoutNullStreams } from 'child_process';
import {
  buildBatchRangePromoteCommand,
  buildDetectorPerformanceCommand,
  buildHistoricalRangeScanCommand,
  buildLocalPythonEnv,
  runBatchRangePromote,
  runDetectorPerformance,
  runHistoricalRangeScan,
  type SpawnFn,
} from './localPythonRunner';
import { parseBatchPromoteOutput, parseHistoricalScanOutput } from './localPythonOutput';

const BACKEND = 'C:\\FXTM\\backend';
const DB = 'C:\\Users\\test\\Documents\\FXTM_Research\\raw_mapping_v159.db';

function mockSpawn(stdout: string, stderr: string, exitCode: number): SpawnFn {
  return () => {
    const proc = new EventEmitter() as ChildProcessWithoutNullStreams;
    proc.stdout = new EventEmitter() as ChildProcessWithoutNullStreams['stdout'];
    proc.stderr = new EventEmitter() as ChildProcessWithoutNullStreams['stderr'];
    queueMicrotask(() => {
      if (stdout) proc.stdout.emit('data', Buffer.from(stdout));
      if (stderr) proc.stderr.emit('data', Buffer.from(stderr));
      proc.emit('close', exitCode);
    });
    return proc;
  };
}

describe('localPythonRunner command builders', () => {
  it('buildHistoricalRangeScanCommand builds correct command', () => {
    const spec = buildHistoricalRangeScanCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      layer: 'WEEKLY',
      dryRun: true,
      limit: 100,
    });

    expect(spec.pythonPath).toBe('python');
    expect(spec.cwd).toBe(BACKEND);
    expect(spec.args).toContain(path.join(BACKEND, 'historical_range_scan.py'));
    expect(spec.args).toEqual(
      expect.arrayContaining([
        '--symbol',
        'XAUUSD',
        '--timeframe',
        'W1',
        '--from',
        '2025-01-01',
        '--to',
        '2025-12-31',
        '--layer',
        'WEEKLY',
        '--limit',
        '100',
        '--db',
        DB,
        '--dry-run',
      ]),
    );
    expect(spec.args).not.toContain('--seed-policy');
  });

  it('buildHistoricalRangeScanCommand adds --seed-policy reviewed_truth_only when set', () => {
    const spec = buildHistoricalRangeScanCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      seedPolicy: 'reviewed_truth_only',
    });

    expect(spec.args).toEqual(
      expect.arrayContaining(['--seed-policy', 'reviewed_truth_only']),
    );
  });

  it('buildBatchRangePromoteCommand includes --json by default', () => {
    const spec = buildBatchRangePromoteCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      layer: 'WEEKLY',
      confirm: true,
    });

    expect(spec.args).toContain('--json');
    expect(spec.args).toContain('--confirm');
    expect(spec.args).toEqual(
      expect.arrayContaining(['--from', '2025-01-01', '--to', '2025-12-31', '--layer', 'WEEKLY']),
    );
  });

  it('buildDetectorPerformanceCommand requests JSON output', () => {
    const spec = buildDetectorPerformanceCommand({
      backendDir: BACKEND,
      databasePath: DB,
      symbol: 'XAUUSD',
      structureLayer: 'WEEKLY',
      sourceTimeframe: 'W1',
    });

    expect(spec.args).toContain('--json');
    expect(spec.args).toEqual(
      expect.arrayContaining([
        '--symbol',
        'XAUUSD',
        '--structure-layer',
        'WEEKLY',
        '--source-timeframe',
        'W1',
        '--db',
        DB,
      ]),
    );
  });
});

describe('localPythonRunner env', () => {
  it('buildLocalPythonEnv passes required detector and DB env vars', () => {
    const env = buildLocalPythonEnv({
      backendDir: BACKEND,
      databasePath: DB,
    });

    expect(env.DATABASE_PATH).toBe(DB);
    expect(env.RAW_MAPPING_DB_PATH).toBe(DB);
    expect(env.DETECTOR_RANGE_MODE).toBe('doctrine_v2');
    expect(env.DETECTOR_RANGE_SCALE_MODE).toBe('generic');
    expect(env.PYTHONPATH).toBe(BACKEND);
    expect(env.PYTHONUNBUFFERED).toBe('1');
  });
});

describe('localPythonRunner output parsers', () => {
  it('parseHistoricalScanOutput extracts summary fields', () => {
    const parsed = parseHistoricalScanOutput(`
candles_scanned: 79
suggestions_created: 79
RANGE_CANDIDATE: 79
NO_VALID_RANGE: 0
detection_run_id: abc-123
`);
    expect(parsed.candles_scanned).toBe(79);
    expect(parsed.suggestions_created).toBe(79);
    expect(parsed.detection_run_id).toBe('abc-123');
  });

  it('parseBatchPromoteOutput parses JSON stdout', () => {
    const parsed = parseBatchPromoteOutput('{"ok":true,"would_promote":79}');
    expect(parsed).toEqual({ ok: true, would_promote: 79 });
  });
});

describe('localPythonRunner spawn', () => {
  it('runHistoricalRangeScan handles success output', async () => {
    const stdout = 'candles_scanned: 10\nsuggestions_created: 10\n';
    const result = await runHistoricalRangeScan({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      spawnFn: mockSpawn(stdout, '', 0),
    });

    expect(result.ok).toBe(true);
    expect(result.exitCode).toBe(0);
    expect(result.parsed).toMatchObject({ candles_scanned: 10, suggestions_created: 10 });
  });

  it('runBatchRangePromote handles Python failure cleanly', async () => {
    const result = await runBatchRangePromote({
      backendDir: BACKEND,
      databasePath: DB,
      spawnFn: mockSpawn('', 'database is locked', 1),
    });

    expect(result.ok).toBe(false);
    expect(result.exitCode).toBe(1);
    expect(result.stderr).toContain('database is locked');
  });

  it('runDetectorPerformance surfaces spawn errors', async () => {
    const failingSpawn: SpawnFn = () => {
      const proc = new EventEmitter() as ChildProcessWithoutNullStreams;
      proc.stdout = new EventEmitter() as ChildProcessWithoutNullStreams['stdout'];
      proc.stderr = new EventEmitter() as ChildProcessWithoutNullStreams['stderr'];
      queueMicrotask(() => proc.emit('error', new Error('ENOENT python')));
      return proc;
    };

    const result = await runDetectorPerformance({
      backendDir: BACKEND,
      databasePath: DB,
      spawnFn: failingSpawn,
    });

    expect(result.ok).toBe(false);
    expect(result.error).toContain('ENOENT');
  });
});
