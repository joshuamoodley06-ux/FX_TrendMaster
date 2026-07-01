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
  readChartMemoryFromStore,
  resolveNearestCandleTime,
  resolveRoutineTfSwitchCameraPlan,
  routineTfMemoryReason,
  sanitizeRoutineMemoryCameraAfterLoad,
  shouldPersistChartMemory,
  snapshotMemoryFromVisibleDomain,
} from './chartMemory';

function makeDailyCandles(count: number, startYear = 2024): { time: string }[] {
  const rows: { time: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(Date.UTC(startYear, 0, 1 + i));
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    rows.push({ time: `${y}.${m}.${day} 00:00` });
  }
  return rows;
}

function makeHourlyCandles(count: number, startYear = 2024): { time: string }[] {
  const rows: { time: string }[] = [];
  const start = Date.UTC(startYear, 0, 1, 0, 0, 0);
  for (let i = 0; i < count; i += 1) {
    const d = new Date(start + i * 3600000);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, '0');
    const day = String(d.getUTCDate()).padStart(2, '0');
    const h = String(d.getUTCHours()).padStart(2, '0');
    rows.push({ time: `${y}.${m}.${day} ${h}:00` });
  }
  return rows;
}

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

  it('prefers global replay over saved destination memory for routine switch', () => {
    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode: 'CASE',
      sourceTf: 'W1',
      destTf: 'D1',
      savedDestMemory: {
        start: '2024-03-01T00:00:00.000Z',
        end: '2024-04-01T00:00:00.000Z',
      },
      sourceViewport: null,
      globalReplayTime: '2024-05-01T00:00:00.000Z',
      selectedCandleTime: '2024-02-01T00:00:00.000Z',
      replayMode: true,
      explicitReplayMode: true,
    });
    expect(plan.reason).toBe(routineTfMemoryReason('W1', 'D1'));
    expect(plan.targetTime).toBe('2024-05-01T00:00:00.000Z');
    expect(plan.fitWindow).toBeNull();
  });

  it('uses saved destination center only on cross-timeframe switch', () => {
    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode: 'CASE',
      sourceTf: 'W1',
      destTf: 'D1',
      savedDestMemory: {
        start: '2024-03-01T00:00:00.000Z',
        end: '2024-04-01T00:00:00.000Z',
      },
      sourceViewport: null,
      globalReplayTime: '2024-05-01T00:00:00.000Z',
      selectedCandleTime: null,
      replayMode: false,
    });
    expect(plan.fitWindow).toBeNull();
    expect(plan.targetTime).toBeTruthy();
  });

  it('keeps saved span on same-timeframe switch', () => {
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
  });

  it('maps source viewport center when no higher-priority anchor exists', () => {
    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode: 'CASE',
      sourceTf: 'W1',
      destTf: 'D1',
      savedDestMemory: null,
      sourceViewport: snapshotMemoryFromVisibleDomain({
        start: '2024-01-01T00:00:00.000Z',
        end: '2024-03-01T00:00:00.000Z',
      }),
      globalReplayTime: null,
      selectedCandleTime: null,
    });
    expect(plan.intent).toBe('PRESERVE_OR_NEAREST_TIME');
    expect(plan.targetTime).toBeTruthy();
    expect(plan.fitWindow).toBeNull();
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

  it('uses global replay as camera anchor only when explicit replay is off', () => {
    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode: 'CASE',
      sourceTf: 'D1',
      destTf: 'H4',
      savedDestMemory: null,
      sourceViewport: null,
      globalReplayTime: '2024-05-01T00:00:00.000Z',
      selectedCandleTime: null,
      explicitReplayMode: false,
    });
    expect(plan.targetTime).toBe('2024-05-01T00:00:00.000Z');
    expect(plan.fitWindow).toBeNull();
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

  it('prefers saved H1 memory over cross-TF selected candle', () => {
    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode: 'CASE',
      sourceTf: 'D1',
      destTf: 'H1',
      savedDestMemory: {
        start: '2024-03-01T08:00:00.000Z',
        end: '2024-03-05T20:00:00.000Z',
      },
      sourceViewport: null,
      globalReplayTime: null,
      selectedCandleTime: '2024-06-01T00:00:00.000Z',
      replayMode: false,
    });
    expect(plan.targetTime).toBeTruthy();
    expect(plan.fitWindow).toBeNull();
    expect(plan.targetTime).not.toBe('2024-06-01T00:00:00.000Z');
    expect(parseChartTimeMs(String(plan.targetTime))!).toBeLessThan(parseChartTimeMs('2024-04-01T00:00:00.000Z')!);
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
    }, candles, 'H1');
    expect(countBarsInCandleWindow(candles, sanitized.fitWindow!.start, sanitized.fitWindow!.end))
      .toBeGreaterThanOrEqual(minimumRoutineVisibleBarsForTimeframe('H1'));
  });
});
