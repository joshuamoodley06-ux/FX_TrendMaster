import { describe, expect, it } from 'vitest';
import {
  applyCandleAvailabilityToCoverageRow,
  buildHierarchyCoverageRows,
  candleAvailabilityIntervals,
  coverageCandleTimeframe,
  deriveCoverageYearOptions,
  filterCoverageRowsByYear,
  mergeClippedIntervals,
  normalizeCoverageYearRange,
  uncoveredIntervals,
} from './hierarchyCoverage';
const day = 24 * 60 * 60 * 1000;
const hour = 60 * 60 * 1000;

describe('hierarchy coverage intervals', () => {
  it('merges overlaps and clips children without double counting', () => {
    expect(mergeClippedIntervals([
      { startMs: -day, endMs: 4 * day }, { startMs: 3 * day, endMs: 7 * day }, { startMs: 9 * day, endMs: 12 * day },
    ], { startMs: 0, endMs: 10 * day })).toEqual([
      { startMs: 0, endMs: 7 * day }, { startMs: 9 * day, endMs: 10 * day },
    ]);
  });
  it('detects exact front, middle, and tail intervals', () => {
    const gaps = uncoveredIntervals({ startMs: 0, endMs: 10 * day }, [
      { startMs: day, endMs: 4 * day }, { startMs: 6 * day, endMs: 9 * day },
    ]);
    expect(gaps.map(({ startMs, endMs }) => ({ startMs, endMs }))).toEqual([
      { startMs: 0, endMs: day }, { startMs: 4 * day, endMs: 6 * day }, { startMs: 9 * day, endMs: 10 * day },
    ]);
  });
  it('computes coverage from linked spans, not child count', () => {
    const [row] = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
      { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
      { range_id: 3, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-04', range_end_time: '2025-01-08' },
    ], 'WEEKLY');
    expect(row.coveragePercent).toBe(70);
    expect(row.gaps[0].startIso).toBe('2025-01-08T00:00:00.000Z');
  });
  it('accepts one child as 100 percent when its span covers the full parent', () => {
    const [row] = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-02-01' },
      { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-02-01' },
    ], 'WEEKLY');
    expect(row.coveragePercent).toBe(100);
    expect(row.gaps).toEqual([]);
  });
  it('maps each parent layer to the candle timeframe that proves tradable coverage', () => {
    expect(coverageCandleTimeframe('WEEKLY')).toBe('D1');
    expect(coverageCandleTimeframe('DAILY')).toBe('H1');
    expect(coverageCandleTimeframe('INTRADAY')).toBe('M15');
    expect(coverageCandleTimeframe('MICRO')).toBeNull();
  });
  it('uses actual candle intervals instead of bridging a weekend', () => {
    const window = {
      startMs: Date.parse('2025-01-03T20:00:00Z'),
      endMs: Date.parse('2025-01-06T02:00:00Z'),
    };
    expect(candleAvailabilityIntervals([
      { time: '2025.01.03 20:00' },
      { time: '2025.01.06 00:00' },
      { time: '2025.01.06 01:00' },
    ], 'H1', window)).toEqual([
      { startMs: window.startMs, endMs: window.startMs + hour },
      { startMs: Date.parse('2025-01-06T00:00:00Z'), endMs: window.endMs },
    ]);
  });
  it('keeps only candle-supported parts of a suspected mapping gap', () => {
    const [row] = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-03T18:00:00Z', range_end_time: '2025-01-06T02:00:00Z' },
      { range_id: 2, parent_range_id: 1, structure_layer: 'INTRADAY', range_start_time: '2025-01-03T18:00:00Z', range_end_time: '2025-01-03T20:00:00Z' },
    ], 'DAILY');
    const qualified = applyCandleAvailabilityToCoverageRow(row, [
      { time: '2025.01.03 20:00' },
      { time: '2025.01.06 00:00' },
      { time: '2025.01.06 01:00' },
    ], 'H1');
    expect(qualified.marketDataStatus).toBe('AVAILABLE');
    expect(qualified.gaps.map(({ startIso, endIso }) => ({ startIso, endIso }))).toEqual([
      { startIso: '2025-01-03T20:00:00.000Z', endIso: '2025-01-03T21:00:00.000Z' },
      { startIso: '2025-01-06T00:00:00.000Z', endIso: '2025-01-06T02:00:00.000Z' },
    ]);
    expect(qualified.coveragePercent).toBe(40);
  });
  it('removes a suspected gap when the candle store has no OHLC in it', () => {
    const [row] = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
      { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
    ], 'WEEKLY');
    const qualified = applyCandleAvailabilityToCoverageRow(row, [], 'D1');
    expect(qualified.marketDataStatus).toBe('NO_DATA');
    expect(qualified.gaps).toEqual([]);
    expect(qualified.coveragePercent).toBe(100);
  });
  it('derives every available year from actual parent and gap dates', () => {
    const rows = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2023-12-20', range_end_time: '2025-01-05' },
    ], 'WEEKLY');
    expect(deriveCoverageYearOptions(rows)).toEqual([2023, 2024, 2025]);
  });
  it('filters inclusively across the selected from and to years', () => {
    const rows = buildHierarchyCoverageRows([
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2023-01-01', range_end_time: '2023-02-01' },
      { range_id: 2, structure_layer: 'WEEKLY', range_start_time: '2024-01-01', range_end_time: '2024-02-01' },
      { range_id: 3, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-02-01' },
    ], 'WEEKLY');
    expect(filterCoverageRowsByYear(rows, 2023, 2024).map((row) => row.parentId)).toEqual(['1', '2']);
  });
  it('normalizes an inverted year range cleanly', () => {
    expect(normalizeCoverageYearRange(2025, 2023)).toEqual({ fromYear: 2023, toYear: 2025 });
  });
});
