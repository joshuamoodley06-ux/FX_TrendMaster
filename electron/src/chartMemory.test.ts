import { describe, expect, it } from 'vitest';
import {
  buildRoutineMemoryFitWindow,
  chartMemoryKey,
  countBarsInCandleWindow,
  expandCandleIndexWindow,
  globalReplayCursorKey,
  isDegenerateH1MemorySpan,
  legacyChartMemoryKey,
  memoryOverlapsCandles,
  minimumRoutineVisibleBarsForTimeframe,
  parseChartTimeMs,
  pickRoutineAnchorTime,
  readChartMemoryFromStore,
  resolveNearestCandleTime,
  resolveRoutineTfSwitchCameraPlan,
  routineTfMemoryReason,
  sanitizeRoutineMemoryCameraAfterLoad,
  shouldPersistChartMemory,
  snapshotMemoryFromVisibleDomain,
} from './chartMemory';

function makeDailyCandles(count: number, startYear = 2024): { time: string; high?: number; low?: number }[] {
  const rows: { time: string; high?: number; low?: number }[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(Date.UTC(startYear, 0, 1 + i));
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    rows.push({ time: `${y}.${m}.${day} 00:00`, high: 100 + i, low: 90 + i });
  }
  return rows;
}

function makeHourlyCandles(count: number, startYear = 2024): { time: string; high?: number; low?: number }[] {
  const rows: { time: string; high?: number; low?: number }[] = [];
  const start = Date.UTC(startYear, 0, 1, 0, 0, 0);
  for (let i = 0; i < count; i += 1) {
    const d = new Date(start + i * 3600000);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    const h = String(d.getUTCHours()).padStart(2, '0');
    rows.push({ time: `${y}.${m}.${day} ${h}:00`, high: 100 + i, low: 90 + i });
  }
  return rows;
}

function makeM15Candles(count: number, startYear = 2024): { time: string; high?: number; low?: number }[] {
  const rows: { time: string; high?: number; low?: number }[] = [];
  const start = Date.UTC(startYear, 0, 1, 0, 0, 0);
  for (let i = 0; i < count; i += 1) {
    const d = new Date(start + i * 900000);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    const h = String(d.getUTCHours()).padStart(2, '0');
    const min = String(d.getUTCMinutes()).padStart(2, '0');
    rows.push({ time: `${y}.${m}.${day} ${h}:${min}`, high: 100 + i, low: 90 + i });
  }
  return rows;
}

const historicalSourceViewport = snapshotMemoryFromVisibleDomain({
  start: '2024-01-01T00:00:00.000Z',
  end: '2024-03-01T00:00:00.000Z',
});

const staleNearLatestDest = {
  start: '2025-06-01T00:00:00.000Z',
  end: '2025-06-15T00:00:00.000Z',
  visibleBars: 120,
};

describe('chartMemory', () => {
  it('builds case|symbol|timeframe keys', () => {
    expect(chartMemoryKey('42', 'xauusd', 'w1')).toBe('42|XAUUSD|W1');
    expect(globalReplayCursorKey('42', 'xauusd')).toBe('42|XAUUSD');
    expect(legacyChartMemoryKey('42', 'w1')).toBe('42_W1');
  });

  it('reads memory from new or legacy store keys', () => {
    const store = { '42_W1': { start: '2024-01-01T00:00:00.000Z', end: '2024-06-01T00:00:00.000Z' } };
    const mem = readChartMemoryFromStore(store, '42', 'XAUUSD', 'W1');
    expect(mem?.start).toBe('2024-01-01T00:00:00.000Z');
  });

  describe('pickRoutineAnchorTime priority', () => {
    it('replay beats selected, source, saved, and latest', () => {
      const pick = pickRoutineAnchorTime({
        destTf: 'M15',
        globalReplayTime: '2024-05-01T00:00:00.000Z',
        selectedCandleTime: '2024-02-01T00:00:00.000Z',
        sourceViewport: historicalSourceViewport,
        savedDestMemory: staleNearLatestDest,
      });
      expect(pick.anchorSource).toBe('globalReplay');
      expect(pick.targetTime).toBe('2024-05-01T00:00:00.000Z');
    });

    it('selected beats source, saved, and latest', () => {
      const pick = pickRoutineAnchorTime({
        destTf: 'M15',
        globalReplayTime: null,
        selectedCandleTime: '2024-02-01T00:00:00.000Z',
        sourceViewport: historicalSourceViewport,
        savedDestMemory: staleNearLatestDest,
      });
      expect(pick.anchorSource).toBe('selectedCandle');
      expect(pick.targetTime).toBe('2024-02-01T00:00:00.000Z');
    });

    it('source viewport beats saved destination and latest', () => {
      const pick = pickRoutineAnchorTime({
        destTf: 'M15',
        globalReplayTime: null,
        selectedCandleTime: null,
        sourceViewport: historicalSourceViewport,
        savedDestMemory: staleNearLatestDest,
      });
      expect(pick.anchorSource).toBe('sourceViewport');
      expect(parseChartTimeMs(String(pick.targetTime))!).toBeLessThan(parseChartTimeMs('2024-04-01T00:00:00.000Z')!);
    });

    it('saved destination used only when no replay, selected, or source exists', () => {
      const pick = pickRoutineAnchorTime({
        destTf: 'D1',
        globalReplayTime: null,
        selectedCandleTime: null,
        sourceViewport: null,
        savedDestMemory: {
          start: '2024-03-01T00:00:00.000Z',
          end: '2024-04-01T00:00:00.000Z',
        },
      });
      expect(pick.anchorSource).toBe('savedDest');
      expect(pick.targetTime).toBeTruthy();
    });

    it('latest is the final fallback only', () => {
      const pick = pickRoutineAnchorTime({
        destTf: 'H4',
        globalReplayTime: null,
        selectedCandleTime: null,
        sourceViewport: null,
        savedDestMemory: null,
      });
      expect(pick.anchorSource).toBe('latest');
      expect(pick.useLatestFallback).toBe(true);
      expect(pick.targetTime).toBeNull();
    });

    it('stale saved destination near latest cannot override historical source', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'H4',
        destTf: 'M15',
        savedDestMemory: staleNearLatestDest,
        sourceViewport: historicalSourceViewport,
        globalReplayTime: null,
        selectedCandleTime: null,
      });
      expect(plan.anchorSource).toBe('sourceViewport');
      expect(parseChartTimeMs(String(plan.targetTime))!).toBeLessThan(parseChartTimeMs('2024-04-01T00:00:00.000Z')!);
    });
  });

  describe('resolveRoutineTfSwitchCameraPlan matrix', () => {
    const matrix: Array<{ sourceTf: string; destTf: string }> = [
      { sourceTf: 'W1', destTf: 'D1' },
      { sourceTf: 'D1', destTf: 'H4' },
      { sourceTf: 'H4', destTf: 'H1' },
      { sourceTf: 'H4', destTf: 'M15' },
      { sourceTf: 'H1', destTf: 'M15' },
      { sourceTf: 'M15', destTf: 'H1' },
      { sourceTf: 'M15', destTf: 'D1' },
      { sourceTf: 'D1', destTf: 'W1' },
    ];

    it.each(matrix)('preserves historical source viewport on $sourceTf→$destTf', ({ sourceTf, destTf }) => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf,
        destTf,
        savedDestMemory: staleNearLatestDest,
        sourceViewport: historicalSourceViewport,
        globalReplayTime: null,
        selectedCandleTime: null,
      });
      expect(plan.reason).toBe(routineTfMemoryReason(sourceTf, destTf));
      expect(plan.anchorSource).toBe('sourceViewport');
      expect(parseChartTimeMs(String(plan.targetTime))!).toBeLessThan(parseChartTimeMs('2024-04-01T00:00:00.000Z')!);
    });

    it('ignores stored global replay when replay mode is off', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'D1',
        destTf: 'H4',
        savedDestMemory: staleNearLatestDest,
        sourceViewport: historicalSourceViewport,
        globalReplayTime: '2024-02-15T00:00:00.000Z',
        selectedCandleTime: null,
        explicitReplayMode: false,
        replayMode: false,
      });
      expect(plan.anchorSource).toBe('sourceViewport');
      expect(plan.targetTime).not.toBe('2024-02-15T00:00:00.000Z');
    });

    it('uses stored global replay when replay mode is active', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'D1',
        destTf: 'H4',
        savedDestMemory: staleNearLatestDest,
        sourceViewport: historicalSourceViewport,
        globalReplayTime: '2024-02-15T00:00:00.000Z',
        selectedCandleTime: null,
        replayMode: true,
      });
      expect(plan.anchorSource).toBe('globalReplay');
      expect(plan.targetTime).toBe('2024-02-15T00:00:00.000Z');
    });

    it('keeps saved span on same-timeframe switch when no higher anchor exists', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'D1',
        destTf: 'D1',
        savedDestMemory: {
          start: '2024-03-01T00:00:00.000Z',
          end: '2024-04-01T00:00:00.000Z',
        },
        sourceViewport: null,
        globalReplayTime: null,
        selectedCandleTime: null,
      });
      expect(plan.fitWindow?.start).toBe('2024-03-01T00:00:00.000Z');
      expect(plan.anchorSource).toBe('savedDest');
    });

    it('ignores stale saved M15 destination memory on cross-timeframe lower-TF entry', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'H4',
        destTf: 'M15',
        savedDestMemory: staleNearLatestDest,
        sourceViewport: null,
        globalReplayTime: null,
        selectedCandleTime: null,
        ignoreSavedDestMemory: true,
      });
      expect(plan.anchorSource).toBe('latest');
      expect(plan.intent).toBe('LATEST');
    });

    it('keeps saved M15 memory for same-timeframe reloads', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'M15',
        destTf: 'M15',
        savedDestMemory: staleNearLatestDest,
        sourceViewport: null,
        globalReplayTime: null,
        selectedCandleTime: null,
      });
      expect(plan.anchorSource).toBe('savedDest');
      expect(plan.fitWindow?.start).toBe(staleNearLatestDest.start);
    });

    it('prefers selected candle over saved destination on H1 to H1', () => {
      const plan = resolveRoutineTfSwitchCameraPlan({
        cameraMode: 'CASE',
        sourceTf: 'H1',
        destTf: 'H1',
        savedDestMemory: {
          start: '2024-03-01T08:00:00.000Z',
          end: '2024-03-05T20:00:00.000Z',
          visibleBars: 90,
        },
        sourceViewport: null,
        globalReplayTime: null,
        selectedCandleTime: '2024-06-01T00:00:00.000Z',
      });
      expect(plan.anchorSource).toBe('selectedCandle');
      expect(plan.targetTime).toBe('2024-06-01T00:00:00.000Z');
    });
  });

  it('resolves nearest candle time on destination feed', () => {
    const candles = [
      { time: '2024.01.01 00:00' },
      { time: '2024.02.01 00:00' },
      { time: '2024.03.01 00:00' },
    ];
    expect(resolveNearestCandleTime(candles, '2024-01-15T00:00:00.000Z')).toBe('2024.01.01 00:00');
  });

  it('rejects degenerate persisted memory spans', () => {
    expect(shouldPersistChartMemory({ start: 'a', end: 'b', visibleBars: 4 }, 'D1')).toBe(false);
    expect(shouldPersistChartMemory({ start: '2024-01-01T00:00:00.000Z', end: '2024-01-01T00:00:00.000Z', visibleBars: 120 }, 'D1')).toBe(false);
    expect(shouldPersistChartMemory({ start: '2024-01-01T00:00:00.000Z', end: '2024-06-01T00:00:00.000Z', visibleBars: 120 }, 'D1')).toBe(true);
  });

  it('purges degenerate memory on read', () => {
    const store = {
      '42|XAUUSD|H1': { start: '2024-01-01T00:00:00.000Z', end: '2024-01-01T00:00:00.000Z', visibleBars: 4 },
    };
    expect(readChartMemoryFromStore(store, '42', 'XAUUSD', 'H1')).toBeNull();
  });

  it('expands tiny saved memory to minimum D1 span', () => {
    const candles = makeDailyCandles(200);
    const tinyStart = candles[100].time;
    const tinyEnd = candles[103].time;
    const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason: routineTfMemoryReason('W1', 'D1'),
      targetTime: tinyStart,
      fitWindow: { start: tinyStart, end: tinyEnd, low: 0, high: 0, padRatio: 0 },
      priceDomain: null,
      anchorSource: 'sourceViewport',
    }, candles, 'D1');
    const bars = countBarsInCandleWindow(candles, sanitized.fitWindow!.start, sanitized.fitWindow!.end);
    expect(bars).toBeGreaterThanOrEqual(minimumRoutineVisibleBarsForTimeframe('D1'));
  });

  it('builds minimum-span fit window around center time', () => {
    const candles = makeDailyCandles(120);
    const center = candles[60].time;
    const fit = buildRoutineMemoryFitWindow(candles, center, 'D1');
    expect(fit).toBeTruthy();
    expect(countBarsInCandleWindow(candles, fit!.start, fit!.end)).toBeGreaterThanOrEqual(80);
  });

  it('expands index window symmetrically around center', () => {
    const expanded = expandCandleIndexWindow(200, 100, 103, 80, 101);
    expect(expanded.i1 - expanded.i0 + 1).toBeGreaterThanOrEqual(80);
  });

  it('parses MT5 candle timestamps for memory overlap checks', () => {
    const candles = [{ time: '2024.01.01 00:00' }, { time: '2024.03.01 00:00' }];
    expect(memoryOverlapsCandles(candles, { start: '2024-02-01T00:00:00.000Z', end: '2024-02-15T00:00:00.000Z' })).toBe(true);
  });

  it('lands on nearest candle when target anchor is implausible but historical anchor existed', () => {
    const candles = makeHourlyCandles(400);
    const historicalTarget = '2025-06-01T12:00:00.000Z';
    const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason: routineTfMemoryReason('H4', 'H1'),
      targetTime: historicalTarget,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'sourceViewport',
    }, candles, 'H1');
    expect(sanitized.anchorSource).toBe('nearest');
    expect(sanitized.targetTime).toBeTruthy();
    expect(sanitized.intent).toBe('PRESERVE_OR_NEAREST_TIME');
    expect(sanitized.targetTime).not.toBe(historicalTarget);
  });

  it('falls back to latest only when no historical anchor exists', () => {
    const candles = makeM15Candles(500);
    const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
      intent: 'LATEST',
      reason: routineTfMemoryReason('H4', 'M15'),
      targetTime: null,
      fitWindow: null,
      priceDomain: null,
      anchorSource: 'latest',
    }, candles, 'M15');
    expect(sanitized.intent).toBe('LATEST');
    expect(sanitized.anchorSource).toBe('latest');
    expect(sanitized.targetTime).toBe(candles[candles.length - 1].time);
  });

  it('rejects degenerate H1 memory spans and expands on sanitize', () => {
    const candles = makeHourlyCandles(400);
    const center = candles[200].time;
    expect(isDegenerateH1MemorySpan({ start: center, end: center })).toBe(true);
    const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason: routineTfMemoryReason('D1', 'H1'),
      targetTime: center,
      fitWindow: {
        start: candles[200].time,
        end: candles[201].time,
        low: 0,
        high: 0,
        padRatio: 0,
      },
      priceDomain: null,
      anchorSource: 'sourceViewport',
    }, candles, 'H1');
    expect(countBarsInCandleWindow(candles, sanitized.fitWindow!.start, sanitized.fitWindow!.end))
      .toBeGreaterThanOrEqual(minimumRoutineVisibleBarsForTimeframe('H1'));
  });
});
