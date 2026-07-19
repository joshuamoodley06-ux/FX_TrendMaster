import fs from 'fs';
import path from 'path';
import os from 'os';
import { describe, expect, it, vi } from 'vitest';
import { createRequire } from 'module';
import { buildBatchRangePromoteCommand, buildHistoricalRangeScanCommand, buildLocalResearchSeedCommand } from './localPythonRunner';

const requireCjs = createRequire(import.meta.url);
const {
  validateBatchPromoteArgs,
  normalizeRunnerArgs,
  buildMappingAssistantSpec,
  buildWeeklyScript1Spec,
  buildWeeklyMasterMapSpec,
  buildWeeklyScript1ReviewSpec,
  preflightWeeklyAnalysis,
  runWeeklyScript1Activation,
  runWeeklyScript1Review,
} = requireCjs('../electron/localResearchIpc.cjs');

const BACKEND = path.resolve(__dirname, '../../backend');
const PYTHON_ROOT = path.resolve(__dirname, '../../python');
const DB = path.resolve(__dirname, '../test-fixtures/raw_mapping_v159.db');
const RANGE_LIBRARY_DB = path.resolve(__dirname, '../test-fixtures/range_library_memory.sqlite3');

describe('localResearchIpc safety', () => {
  it('blocks confirm promote without userConfirmed', () => {
    const blocked = validateBatchPromoteArgs({
      confirm: true,
      userConfirmed: false,
    });
    expect(blocked?.ok).toBe(false);
    expect(blocked?.error).toContain('userConfirmed');
  });

  it('allows dry-run promote without userConfirmed', () => {
    const blocked = validateBatchPromoteArgs({ confirm: false });
    expect(blocked).toBeNull();
  });

  it('allows confirm promote when userConfirmed is true', () => {
    const blocked = validateBatchPromoteArgs({ confirm: true, userConfirmed: true });
    expect(blocked).toBeNull();
  });

  it('normalizeRunnerArgs fills backendDir and databasePath', () => {
    const payload = normalizeRunnerArgs({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
    });
    expect(payload.backendDir).toBe(BACKEND);
    expect(payload.databasePath).toBe(DB);
  });
});

describe('localResearchIpc runner args', () => {
  it('preflights separate candle and Range Library databases for the selected case', () => {
    const { DatabaseSync } = requireCjs('node:sqlite');
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-weekly-preflight-'));
    const candlePath = path.join(folder, 'candles.sqlite3');
    const rangePath = path.join(folder, 'range.sqlite3');
    const candle = new DatabaseSync(candlePath);
    candle.exec("CREATE TABLE candles(symbol TEXT,timeframe TEXT,time TEXT); INSERT INTO candles VALUES ('XAUUSD','W1','2026-01-01')");
    candle.close();
    const range = new DatabaseSync(rangePath);
    range.exec('CREATE TABLE raw_ranges(id INTEGER); CREATE TABLE raw_events(id INTEGER); CREATE TABLE master_map_ranges(canonical_range_id TEXT); CREATE TABLE master_map_outputs(symbol TEXT, output_json TEXT)');
    const output = JSON.stringify({ trusted_root: { children: [{ structure_layer: 'WEEKLY', source_refs: [{ case_ref: 'case:live' }], children: [] }] } });
    range.prepare('INSERT INTO master_map_outputs VALUES (?,?)').run('XAUUSD', output);
    range.close();

    expect(() => preflightWeeklyAnalysis({ candleDatabasePath: candlePath,
      analysisDatabasePath: rangePath, caseRef: 'case:live', symbol: 'XAUUSD' })).not.toThrow();
    expect(() => preflightWeeklyAnalysis({ candleDatabasePath: rangePath,
      analysisDatabasePath: rangePath, caseRef: 'case:live', symbol: 'XAUUSD' })).toThrow(/CANDLE_SOURCE_INVALID/);
  });

  it('batch promote IPC args omit --confirm unless confirm is true', () => {
    const dry = buildBatchRangePromoteCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      layer: 'WEEKLY',
      confirm: false,
    });
    expect(dry.args).not.toContain('--confirm');

    const confirmed = buildBatchRangePromoteCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      layer: 'WEEKLY',
      confirm: true,
    });
    expect(confirmed.args).toContain('--confirm');
  });

  it('historical range scan command includes --chain when enabled', () => {
    const spec = buildHistoricalRangeScanCommand({
      backendDir: BACKEND,
      databasePath: DB,
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      chain: true,
    });
    expect(spec.args).toContain('--chain');
  });

  it('historical range scan command passes --seed-policy when reviewed truth enabled', () => {
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

  it('local research seed command uses subcommand and json flag', () => {
    const spec = buildLocalResearchSeedCommand({
      backendDir: BACKEND,
      databasePath: DB,
      command: 'create-manual',
      rangeHigh: 2500,
      rangeLow: 2300,
    });
    expect(spec.args).toContain('create-manual');
    expect(spec.args).toContain('--range-high');
    expect(spec.args).toContain('2500');
    expect(spec.args).toContain('--json');
  });

  it('Mapping Assistant runs the range library module against an explicit database', () => {
    const spec = buildMappingAssistantSpec({
      databasePath: RANGE_LIBRARY_DB,
      pythonRoot: PYTHON_ROOT,
      pythonPath: 'python',
    });
    expect(spec.cwd).toBe(PYTHON_ROOT);
    expect(spec.args).toEqual([
      '-m',
      'range_library_memory.xauusd_mapping_assistant',
      '--db-path', RANGE_LIBRARY_DB,
      '--symbol', 'XAUUSD',
      '--json',
    ]);
    expect(spec.env.FXTM_RANGE_LIBRARY_MEMORY_DB).toBe(RANGE_LIBRARY_DB);
  });

  it('Mapping Assistant rejects an implicit database target', () => {
    expect(() => buildMappingAssistantSpec({ pythonRoot: PYTHON_ROOT })).toThrow(/explicit Range Library/);
  });

  it('routes Weekly Script 1 writes only to the disposable copy', () => {
    const candle = path.resolve('C:/research/candles.sqlite3');
    const copy = path.resolve('C:/research/analysis/copy.sqlite3');
    const spec = buildWeeklyScript1Spec({ candleDatabasePath: candle, analysisDatabasePath: copy,
      caseRef: 'case:live', symbol: 'XAUUSD', pythonRoot: PYTHON_ROOT });
    expect(spec.args).toEqual(expect.arrayContaining([
      '--db-path', copy, '--source-db', candle, '--case-ref', 'case:live', '--symbol', 'XAUUSD',
    ]));
    expect(spec.env.FXTM_RANGE_LIBRARY_MEMORY_DB).toBe(copy);
    expect(() => buildWeeklyScript1Spec({ candleDatabasePath: copy, analysisDatabasePath: copy,
      caseRef: 'case:live', symbol: 'XAUUSD', pythonRoot: PYTHON_ROOT })).toThrow(/refuses/);
  });

  it('rebuilds Master Map against the same disposable copy', () => {
    const copy = path.resolve('C:/research/analysis/copy.sqlite3');
    const output = path.resolve('C:/research/analysis/copy.json');
    const spec = buildWeeklyMasterMapSpec({ analysisDatabasePath: copy, outputPath: output, pythonRoot: PYTHON_ROOT });
    expect(spec.args).toEqual(expect.arrayContaining(['--db-path', copy, '--output', output]));
    expect(spec.env.FXTM_RANGE_LIBRARY_MEMORY_DB).toBe(copy);
  });

  it('persists review only to an allow-listed disposable copy and refreshes its Master Map', async () => {
    const copy = path.resolve('C:/research/analysis/copy.sqlite3');
    const live = path.resolve('C:/research/live.sqlite3');
    const calls: any[] = [];
    const runScript = vi.fn(async (spec: any) => {
      calls.push(spec);
      return spec.args.includes('review-weekly-script1')
        ? { ok: true }
        : { ok: true, parsed: { schema_version: 'xauusd_master_map_v0.1' } };
    });
    const result = await runWeeklyScript1Review({ analysisDatabasePath: copy, liveDatabasePath: live,
      runId: 'run-1', caseRef: 'case:live', symbol: 'XAUUSD', canonicalRangeId: 'weekly-1', decision: 'APPROVED',
      pythonRoot: PYTHON_ROOT }, { allowedCopies: new Set([copy]), runScript });
    expect(result.ok).toBe(true);
    expect(calls[0].args).toEqual(expect.arrayContaining([
      'review-weekly-script1', '--db-path', copy, '--run-id', 'run-1', '--canonical-range-id', 'weekly-1', '--decision', 'APPROVED',
    ]));
    expect(calls[0].args).not.toContain(live);
    await expect(runWeeklyScript1Review({ analysisDatabasePath: live, liveDatabasePath: live,
      runId: 'run-1', caseRef: 'case:live', symbol: 'XAUUSD', canonicalRangeId: 'weekly-1', decision: 'APPROVED' },
    { allowedCopies: new Set([live]), runScript })).rejects.toThrow(/LIVE_RANGE_LIBRARY_WRITE_BLOCKED/);
  });

  it('activation copies first, then runs Script 1 and Master Map on that copy', async () => {
    const calls: string[] = [];
    const analysisRoot = path.resolve(__dirname, '../work/weekly-script1-test');
    const copyDatabase = vi.fn(async (_live: string, copy: string) => { calls.push(`copy:${copy}`); return copy; });
    const runScript = vi.fn(async (spec: { script: string }) => {
      calls.push(spec.script);
      return spec.script === 'range_library_memory.master_map'
        ? { ok: true, parsed: { schema_version: 'xauusd_master_map_v0.1' } }
        : { ok: true };
    });
    const existingSource = path.resolve(__dirname, '../package.json');
    const existingCandleSource = path.resolve(__dirname, '../package-lock.json');
    const preflight = vi.fn();
    const result = await runWeeklyScript1Activation({ databasePath: existingSource,
      candleDatabasePath: existingCandleSource, caseRef: 'case:live', symbol: 'XAUUSD',
      analysisRoot, runId: 'test' }, { copyDatabase, runScript, preflight });
    expect(result.source).toBe('DISPOSABLE_ANALYSIS_COPY');
    expect(result.analysisDatabasePath).not.toBe(existingSource);
    expect(calls.slice(1)).toEqual(['range_library_memory.cli', 'range_library_memory.master_map']);
    expect(calls[0]).toBe(`copy:${result.analysisDatabasePath}`);
    expect(preflight).toHaveBeenCalledWith(expect.objectContaining({
      caseRef: 'case:live', symbol: 'XAUUSD', analysisDatabasePath: result.analysisDatabasePath,
    }));
  });
});

describe('preload localResearch API', () => {
  it('exposes expected API names on window.localResearch', () => {
    const preloadPath = path.resolve(__dirname, '../electron/preload.cjs');
    const src = fs.readFileSync(preloadPath, 'utf8');
    expect(src).toContain("exposeInMainWorld('localResearch'");
    expect(src).toContain('getDatabaseStatus');
    expect(src).toContain('pickDatabaseFile');
    expect(src).toContain('openResearchFolder');
    expect(src).toContain('runHistoricalRangeScan');
    expect(src).toContain('runBatchRangePromote');
    expect(src).toContain('runDetectorPerformance');
    expect(src).toContain('runRandomRangeAudit');
    expect(src).toContain('runRecordAuditVerdict');
    expect(src).toContain('pullVpsCandles');
    expect(src).toContain('runLocalResearchSeed');
    expect(src).toContain('runMappingAssistant');
    expect(src).toContain('runWeeklyScript1');
    expect(src).toContain('reviewWeeklyScript1');
    expect(src).toContain('local-research:weekly-script1');
    expect(src).toContain('local-research:mapping-assistant');
    expect(src).toContain('local-research:seed');
    expect(src).toContain('local-research:historical-range-scan');
    expect(src).toContain('local-research:batch-range-promote');
    expect(src).toContain('local-research:detector-performance');
  });
});
