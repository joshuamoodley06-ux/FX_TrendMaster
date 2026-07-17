import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import { createRequire } from 'module';
import { buildBatchRangePromoteCommand, buildHistoricalRangeScanCommand, buildLocalResearchSeedCommand } from './localPythonRunner';

const requireCjs = createRequire(import.meta.url);
const {
  validateBatchPromoteArgs,
  normalizeRunnerArgs,
  buildMappingAssistantSpec,
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
    expect(src).toContain('local-research:mapping-assistant');
    expect(src).toContain('local-research:seed');
    expect(src).toContain('local-research:historical-range-scan');
    expect(src).toContain('local-research:batch-range-promote');
    expect(src).toContain('local-research:detector-performance');
  });
});
