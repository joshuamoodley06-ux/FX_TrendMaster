import { describe, expect, it } from 'vitest';
import {
  auditSamplesFromResult,
  promotedCountFromResult,
  scanSummaryFromResult,
  suggestionIdFromSample,
  weeklySeedCheckFromResult,
  weeklySeedRangesFromResult,
} from './localResearchWorkflow';
import { buildHistoricalRangeScanCommand } from './localPythonRunner';
import type { LocalResearchRunResult } from './localResearchClient';

describe('localResearchWorkflow', () => {
  it('scanSummaryFromResult reads human-facing counts', () => {
    const result: LocalResearchRunResult = {
      ok: true,
      exitCode: 0,
      stdout: 'RANGE_CANDIDATE: 12\nNO_VALID_RANGE: 3\n',
      stderr: '',
      parsed: {
        range_candidate_count: 12,
        no_valid_range_count: 3,
        detection_run_id: 'run-1',
      },
    };
    expect(scanSummaryFromResult(result)).toEqual({
      rangesFound: 12,
      noValidRange: 3,
      candlesScanned: 0,
      detectionRunId: 'run-1',
    });
  });

  it('promotedCountFromResult reads promoted count', () => {
    const result: LocalResearchRunResult = {
      ok: true,
      exitCode: 0,
      stdout: '',
      stderr: '',
      parsed: { counts: { promoted: 12 } },
    };
    expect(promotedCountFromResult(result)).toBe(12);
  });

  it('auditSamplesFromResult returns chart-ready samples', () => {
    const result: LocalResearchRunResult = {
      ok: true,
      exitCode: 0,
      stdout: '',
      stderr: '',
      parsed: {
        samples: [{ source: 'confirmed_ranges', suggestion_id: 's-1', rh: 10, rl: 5 }],
      },
    };
    expect(auditSamplesFromResult(result)).toHaveLength(1);
    expect(suggestionIdFromSample(auditSamplesFromResult(result)[0])).toBe('s-1');
  });

  it('weeklySeedCheckFromResult reads has_seed flag', () => {
    const result: LocalResearchRunResult = {
      ok: true,
      exitCode: 0,
      stdout: '',
      stderr: '',
      parsed: { ok: true, has_seed: true, seed: { id: 7, range_high_price: 2500, range_low_price: 2300 } },
    };
    expect(weeklySeedCheckFromResult(result)?.has_seed).toBe(true);
  });

  it('weeklySeedRangesFromResult returns selectable rows', () => {
    const result: LocalResearchRunResult = {
      ok: true,
      exitCode: 0,
      stdout: '',
      stderr: '',
      parsed: {
        ok: true,
        ranges: [{ id: 3, selectable: true, range_high_price: 2400, range_low_price: 2200 }],
      },
    };
    expect(weeklySeedRangesFromResult(result)).toHaveLength(1);
  });

  it('weekly historical scan defaults to baseline replay (no --chain)', () => {
    const spec = buildHistoricalRangeScanCommand({
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
    });
    expect(spec.args).not.toContain('--chain');
  });

  it('experimental chain mode adds --chain flag', () => {
    const spec = buildHistoricalRangeScanCommand({
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      chain: true,
    });
    expect(spec.args).toContain('--chain');
  });

  it('reviewed truth seed adds --seed-policy reviewed_truth_only', () => {
    const spec = buildHistoricalRangeScanCommand({
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
      seedPolicy: 'reviewed_truth_only',
    });
    expect(spec.args).toEqual(
      expect.arrayContaining(['--seed-policy', 'reviewed_truth_only']),
    );
  });

  it('weekly historical scan omits --seed-policy by default', () => {
    const spec = buildHistoricalRangeScanCommand({
      dateFrom: '2025-01-01',
      dateTo: '2025-12-31',
    });
    expect(spec.args).not.toContain('--seed-policy');
  });
});
