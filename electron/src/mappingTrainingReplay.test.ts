import { describe, expect, it } from 'vitest';
import {
  filterCandlesToReplayCut,
  filterEventsToReplayCut,
  isMappingTrainingReplayActive,
  replayBootstrapIndex,
  resolveMappingTrainingReplayStart,
  trimCandlesToResearchWindow,
} from './mappingTrainingReplay';

const tailCandles = [
  { time: '2026-04-20T00:00:00.000Z', high: 1, low: 0 },
  { time: '2026-04-21T09:30:00.000Z', high: 2, low: 1 },
];

const candles = [
  { time: '2024-11-04T00:00:00.000Z', high: 1, low: 0 },
  { time: '2024-11-05T00:00:00.000Z', high: 2, low: 1 },
  { time: '2024-11-06T00:00:00.000Z', high: 3, low: 2 },
  { time: '2024-11-07T00:00:00.000Z', high: 4, low: 3 },
  { time: '2024-11-08T00:00:00.000Z', high: 5, low: 4 },
];

describe('mappingTrainingReplay', () => {
  it('training replay is active during child mapping or guided cursor', () => {
    expect(isMappingTrainingReplayActive(null, null)).toBe(false);
    expect(isMappingTrainingReplayActive({ parentRangeId: '1' }, null)).toBe(true);
    expect(isMappingTrainingReplayActive(null, { active: true })).toBe(true);
  });

  it('replay start prefers parent range start', () => {
    const start = resolveMappingTrainingReplayStart({
      range_start_time: '2024-11-04T00:00:00.000Z',
    }, { cursor_time_ms: Date.parse('2024-11-08T00:00:00.000Z') });
    expect(start?.source).toBe('parent_start');
    expect(start?.startTime).toBe('2024-11-04T00:00:00.000Z');
  });

  it('filterCandlesToReplayCut hides forward candles', () => {
    const visible = filterCandlesToReplayCut(candles, '2024-11-06T00:00:00.000Z');
    expect(visible.length).toBe(3);
    expect(visible[visible.length - 1].time).toBe('2024-11-06T00:00:00.000Z');
  });

  it('filterEventsToReplayCut hides future events', () => {
    const events = [
      { time: '2024-11-05T00:00:00.000Z' },
      { time: '2024-11-09T00:00:00.000Z' },
    ];
    const visible = filterEventsToReplayCut(events, '2024-11-06T00:00:00.000Z');
    expect(visible.length).toBe(1);
  });

  it('replayBootstrapIndex stays at first bar when parent start is before history', () => {
    expect(replayBootstrapIndex(tailCandles, '2024-11-14T00:00:00.000Z')).toBe(0);
    expect(replayBootstrapIndex(tailCandles, '2026-04-21T09:30:00.000Z')).toBe(1);
  });

  it('trimCandlesToResearchWindow drops tail outside parent day', () => {
    const mixed = [
      ...candles,
      ...tailCandles,
    ];
    const trimmed = trimCandlesToResearchWindow(mixed, '2024-11-04', '2024-11-08');
    expect(trimmed.every((c) => c.time.startsWith('2024-11-'))).toBe(true);
    expect(trimmed.some((c) => c.time.startsWith('2026'))).toBe(false);
  });
});
