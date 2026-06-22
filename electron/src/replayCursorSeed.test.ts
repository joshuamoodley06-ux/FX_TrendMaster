import { describe, expect, it } from 'vitest';
import {
  applyReplaySeedPlan,
  buildStructuralReplayScopeKey,
  ensureReplayIndexAllowsForwardPlay,
  isReplayCursorOutsideLoadedWindow,
  isStaleStoredReplayCursor,
  replayPlayForwardState,
  replayPlayForwardStatusMessage,
  replayRestoreStatusMessage,
  resolveStructuralReplayRestore,
  resolveStructuralReplaySeedPlan,
  resolveStructuralReplayStartTime,
  validateReplayCursorForStructuralContext,
} from './replayCursorSeed';

const candles = [
  { time: '2025-01-06T00:00:00.000Z' },
  { time: '2025-01-07T00:00:00.000Z' },
  { time: '2025-01-08T00:00:00.000Z' },
  { time: '2025-01-09T00:00:00.000Z' },
];

const scope = {
  symbol: 'EURUSD',
  caseId: 'case-1',
  timeframe: 'D1',
  rangeId: '10',
  loadWindowStart: '2025-01-06',
  loadWindowEnd: '2025-01-09',
};

describe('replayCursorSeed', () => {
  it('builds scoped storage keys from symbol case tf range and window', () => {
    const key = buildStructuralReplayScopeKey(scope);
    expect(key).toBe('EURUSD|case-1|D1|10|2025-01-06|2025-01-09');
  });

  it('uses true range start fields only for seed time', () => {
    expect(resolveStructuralReplayStartTime({
      range_start_time: '2025-01-07T00:00:00.000Z',
      range_high_time: '2025-01-09T00:00:00.000Z',
    })).toBe('2025-01-07T00:00:00.000Z');
  });

  it('initializes at range start when cursor is missing', () => {
    const decision = resolveStructuralReplayRestore({
      candles,
      scope,
      range: { range_id: 10, range_start_time: '2025-01-07T00:00:00.000Z' },
    });
    expect(decision.action).toBe('initialize');
    expect(decision.reason).toBe('missing');
    expect(decision.index).toBe(1);
    expect(decision.playForwardEnabled).toBe(true);
  });

  it('preserves valid scoped session cursor inside the window', () => {
    const decision = resolveStructuralReplayRestore({
      candles,
      scope,
      scopedCursorTime: '2025-01-08T00:00:00.000Z',
      range: { range_id: 10, range_start_time: '2025-01-07T00:00:00.000Z' },
    });
    expect(decision.action).toBe('preserve');
    expect(decision.index).toBe(2);
    expect(decision.playForwardEnabled).toBe(true);
  });

  it('preserves valid session cursor when play forward is available', () => {
    const decision = resolveStructuralReplayRestore({
      candles,
      scope,
      sessionCursorTime: '2025-01-07T00:00:00.000Z',
      range: { range_id: 10, range_start_time: '2025-01-06T00:00:00.000Z' },
    });
    expect(decision.action).toBe('preserve');
    expect(decision.candidateSource).toBe('session');
    expect(decision.index).toBe(1);
  });

  it('re-initializes stale tail cursor at last bar', () => {
    const decision = resolveStructuralReplayRestore({
      candles,
      scope,
      sessionCursorTime: '2025-01-09T00:00:00.000Z',
      range: { range_id: 10, range_start_time: '2025-01-07T00:00:00.000Z' },
    });
    expect(decision.action).toBe('initialize');
    expect(decision.reason).toBe('blocked_at_last_bar');
    expect(decision.index).toBe(1);
    expect(decision.playForwardEnabled).toBe(true);
  });

  it('walks seed back when range start maps to the last loaded bar', () => {
    const result = applyReplaySeedPlan(candles, {
      seedTime: '2025-01-09T00:00:00.000Z',
      source: 'range_start',
    });
    expect(result.index).toBeLessThan(candles.length - 1);
    expect(result.playForwardEnabled).toBe(true);
    expect(result.seedAdjusted).toBe(true);
  });

  it('re-initializes cursor outside loaded window', () => {
    const check = validateReplayCursorForStructuralContext(
      candles,
      '2025-02-01T00:00:00.000Z',
      'session',
    );
    expect(check.valid).toBe(false);
    expect(check.reason).toBe('outside_window');
    expect(isReplayCursorOutsideLoadedWindow(candles, '2025-02-01T00:00:00.000Z')).toBe(true);
  });

  it('prefers guided cursor time when initializing', () => {
    const plan = resolveStructuralReplaySeedPlan({
      range: { range_start_time: '2025-01-06T00:00:00.000Z' },
      guidedCursorTimeMs: Date.parse('2025-01-08T00:00:00.000Z'),
    });
    expect(plan.source).toBe('guided_cursor');
    const result = applyReplaySeedPlan(candles, plan);
    expect(result.index).toBe(2);
  });

  it('ensureReplayIndexAllowsForwardPlay finds earliest playable bar', () => {
    const ensured = ensureReplayIndexAllowsForwardPlay(candles, candles.length - 1);
    expect(ensured.index).toBe(0);
    expect(ensured.adjusted).toBe(true);
  });

  it('replayPlayForwardState allows forward play at last bar when horizon extend is available', () => {
    const play = replayPlayForwardState(candles, candles.length - 1, true);
    expect(play.enabled).toBe(true);
    expect(play.reason).toBe('ok');
  });

  it('preserves cursor at last bar when structural horizon can extend', () => {
    const decision = resolveStructuralReplayRestore({
      candles,
      scope: {
        symbol: 'XAUUSD',
        caseId: 'c1',
        timeframe: 'D1',
        rangeId: '12',
        loadWindowStart: '2025-01-01',
        loadWindowEnd: '2025-01-20',
      },
      scopedCursorTime: candles[candles.length - 1].time,
      horizonExtendAvailable: true,
    });
    expect(decision.action).toBe('preserve');
    expect(decision.playForwardEnabled).toBe(true);
  });

  it('reports restore and play-forward block reasons', () => {
    expect(replayRestoreStatusMessage({ action: 'initialize', reason: 'blocked_at_last_bar', candidateSource: 'session', seedAdjusted: false }))
      .toContain('stale tail');
    expect(replayPlayForwardStatusMessage('at-last-bar-no-ahead')).toContain('last loaded bar');
  });

  it('flags legacy stale stored replay ahead of seed', () => {
    expect(isStaleStoredReplayCursor('2025-01-09T00:00:00.000Z', '2025-01-06T00:00:00.000Z')).toBe(true);
    expect(isStaleStoredReplayCursor('2025-01-06T00:00:00.000Z', '2025-01-06T00:00:00.000Z')).toBe(false);
  });
});
