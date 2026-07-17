import { describe, expect, it } from 'vitest';

import { buildCanonicalChartOverlay } from './canonicalChartOverlay';

const weekly = {
  canonical_range_id: 'mm:range:weekly-1',
  canonical_structure_layer: 'WEEKLY',
  range_high: 2800,
  range_low: 2300,
  range_high_time: '2026-01-25T00:00:00Z',
  range_low_time: '2025-12-28T00:00:00Z',
  structural_range_start_time: '2025-12-28T00:00:00Z',
  structural_range_end_time: '2026-01-25T00:00:00Z',
  status: 'ACTIVE',
};

const daily = {
  canonical_range_id: 'mm:range:daily-1',
  canonical_structure_layer: 'DAILY',
  structure_layer: 'INTRADAY',
  range_high_price: 2500,
  range_low_price: 2400,
  range_high_time: '2026-01-18T00:00:00Z',
  range_low_time: '2026-01-12T00:00:00Z',
  structural_range_start_time: '2026-01-12T00:00:00Z',
  structural_range_end_time: '2026-01-18T00:00:00Z',
  range_start_time: '2026-01-01T00:00:00Z',
  range_end_time: '2026-02-01T00:00:00Z',
  status: 'BROKEN',
};

describe('buildCanonicalChartOverlay', () => {
  it('preserves the canonical Weekly overlay contract', () => {
    expect(buildCanonicalChartOverlay(weekly)).toEqual({
      rangeId: 'mm:range:weekly-1',
      structureLayer: 'WEEKLY',
      rangeScope: 'MAJOR',
      status: 'ACTIVE',
      customLabelPrefix: 'CANONICAL WEEKLY',
      high: 2800,
      low: 2300,
      start: '2025-12-28T00:00:00Z',
      end: '2026-01-25T00:00:00Z',
      isActive: true,
    });
  });

  it('builds a Daily parent overlay even when the chart target layer is Intraday', () => {
    expect(buildCanonicalChartOverlay(daily)).toMatchObject({
      rangeId: 'mm:range:daily-1',
      structureLayer: 'DAILY',
      customLabelPrefix: 'CANONICAL DAILY',
      high: 2500,
      low: 2400,
      status: 'BROKEN',
    });
  });

  it('uses structural anchor times rather than the padded navigation window', () => {
    expect(buildCanonicalChartOverlay(daily)).toMatchObject({
      start: '2026-01-12T00:00:00Z',
      end: '2026-01-18T00:00:00Z',
    });
  });

  it('falls back to ordinary range window fields when structural fields are absent', () => {
    expect(buildCanonicalChartOverlay({
      canonical_range_id: 'mm:range:daily-fallback',
      structure_layer: 'DAILY',
      range_high: 2450,
      range_low: 2350,
      range_start_time: '2026-02-01T00:00:00Z',
      range_end_time: '2026-02-10T00:00:00Z',
    })).toMatchObject({
      start: '2026-02-01T00:00:00Z',
      end: '2026-02-10T00:00:00Z',
    });
  });

  it('replaces selection naturally because each call contains only the current canonical range', () => {
    const first = buildCanonicalChartOverlay(daily);
    const second = buildCanonicalChartOverlay({
      ...daily,
      canonical_range_id: 'mm:range:daily-2',
      range_high_price: 2600,
      range_low_price: 2450,
    });
    const backToWeekly = buildCanonicalChartOverlay(weekly);
    expect(first?.rangeId).toBe('mm:range:daily-1');
    expect(second).toMatchObject({
      rangeId: 'mm:range:daily-2',
      structureLayer: 'DAILY',
      high: 2600,
      low: 2450,
    });
    expect(backToWeekly).toMatchObject({
      rangeId: 'mm:range:weekly-1',
      structureLayer: 'WEEKLY',
    });
  });

  it('does not duplicate a canonical range already represented by a saved overlay', () => {
    expect(buildCanonicalChartOverlay(daily, ['mm:range:daily-1'])).toBeNull();
  });

  it('rejects unsupported layers and invalid price bounds', () => {
    expect(buildCanonicalChartOverlay({
      ...daily,
      canonical_structure_layer: 'INTRADAY',
    })).toBeNull();
    expect(buildCanonicalChartOverlay({
      ...daily,
      range_high_price: 2400,
      range_low_price: 2500,
    })).toBeNull();
  });
});
