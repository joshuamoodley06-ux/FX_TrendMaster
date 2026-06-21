import { describe, expect, it } from 'vitest';
import {
  buildDryRunStamp,
  dryRunMatchesScope,
  extractWouldPromote,
  isSuccessfulDryRun,
  promoteScopeFromArgs,
  promoteScopeKey,
  type LocalResearchRunResult,
} from './localResearchClient';

const SCOPE = promoteScopeFromArgs({
  symbol: 'XAUUSD',
  timeframe: 'W1',
  layer: 'WEEKLY',
  dateFrom: '2025-01-01',
  dateTo: '2025-12-31',
});

const DB = 'C:\\Users\\test\\Documents\\FXTM_Research\\raw_mapping_v159.db';

function dryRunResult(wouldPromote: number, ok = true): LocalResearchRunResult {
  return {
    ok,
    exitCode: ok ? 0 : 1,
    stdout: '',
    stderr: '',
    parsed: {
      ok: true,
      dry_run: true,
      counts: { would_promote: wouldPromote },
    },
  };
}

describe('localResearch promote safety', () => {
  it('promoteScopeKey is stable for same filters', () => {
    expect(promoteScopeKey(SCOPE)).toBe('XAUUSD|W1|WEEKLY|2025-01-01|2025-12-31');
  });

  it('extractWouldPromote reads counts.would_promote', () => {
    expect(extractWouldPromote({ counts: { would_promote: 79 } })).toBe(79);
    expect(extractWouldPromote({ counts: {} })).toBeNull();
  });

  it('isSuccessfulDryRun requires ok dry_run payload', () => {
    expect(isSuccessfulDryRun(dryRunResult(10))).toBe(true);
    expect(isSuccessfulDryRun({ ...dryRunResult(10), ok: false })).toBe(false);
    expect(isSuccessfulDryRun({
      ok: true,
      exitCode: 0,
      stdout: '',
      stderr: '',
      parsed: { ok: true, dry_run: false, counts: { would_promote: 1 } },
    })).toBe(false);
  });

  it('dryRunMatchesScope requires matching scope and database path', () => {
    const stamp = buildDryRunStamp(SCOPE, DB, dryRunResult(79));
    expect(stamp).not.toBeNull();
    expect(dryRunMatchesScope(stamp, SCOPE, DB)).toBe(true);
    expect(dryRunMatchesScope(stamp, { ...SCOPE, dateTo: '2025-06-30' }, DB)).toBe(false);
    expect(dryRunMatchesScope(stamp, SCOPE, 'C:\\other.db')).toBe(false);
    expect(dryRunMatchesScope(null, SCOPE, DB)).toBe(false);
  });

  it('buildDryRunStamp rejects failed dry-run', () => {
    expect(buildDryRunStamp(SCOPE, DB, dryRunResult(5, false))).toBeNull();
  });
});
