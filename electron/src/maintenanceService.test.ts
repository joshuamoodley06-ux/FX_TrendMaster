import { describe, expect, it } from 'vitest';
import {
  AUTO_MERGE_ENABLED,
  buildMaintenanceReport,
  findOrphanRanges,
  findSuggestedMerges,
  normaliseMaintenanceSymbol,
} from './maintenanceService';

function rangeRow(partial: Record<string, unknown>) {
  return partial as import('./maintenanceService').MaintenanceRangeRow;
}

describe('maintenanceService orphan finder', () => {
  it('flags ranges whose parent_range_id no longer exists', () => {
    const orphans = findOrphanRanges([
      rangeRow({ range_id: 1, structure_layer: 'WEEKLY', parent_range_id: 404 }),
      rangeRow({ range_id: 2, structure_layer: 'DAILY', parent_range_id: 1 }),
      rangeRow({ range_id: 10, structure_layer: 'MACRO' }),
    ]);

    expect(orphans).toHaveLength(1);
    expect(orphans[0]).toMatchObject({
      kind: 'missing_parent',
      range_id: '1',
      parent_range_id: '404',
    });
  });

  it('flags self-referencing parent links', () => {
    const orphans = findOrphanRanges([
      rangeRow({ range_id: 7, structure_layer: 'DAILY', parent_range_id: 7 }),
    ]);

    expect(orphans).toHaveLength(1);
    expect(orphans[0].kind).toBe('self_parent');
  });

  it('ignores root ranges with no parent', () => {
    const orphans = findOrphanRanges([
      rangeRow({ range_id: 10, structure_layer: 'WEEKLY', parent_range_id: null }),
      rangeRow({ range_id: 11, structure_layer: 'WEEKLY' }),
    ]);
    expect(orphans).toHaveLength(0);
  });
});

describe('maintenanceService auto-merge', () => {
  it('is disabled and never emits merge suggestions', () => {
    expect(AUTO_MERGE_ENABLED).toBe(false);

    const suggestions = findSuggestedMerges([
      rangeRow({
        range_id: 101,
        structure_layer: 'DAILY',
        parent_range_id: 50,
        range_scope: 'MINOR',
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-01-05T00:00:00.000Z',
      }),
      rangeRow({
        range_id: 102,
        structure_layer: 'DAILY',
        parent_range_id: 50,
        range_scope: 'MINOR',
        range_start_time: '2025-01-03T00:00:00.000Z',
        range_end_time: '2025-01-08T00:00:00.000Z',
      }),
    ]);

    expect(suggestions).toEqual([]);
  });
});

describe('buildMaintenanceReport', () => {
  it('returns a read-only aggregate report without merge suggestions', () => {
    const report = buildMaintenanceReport('xauusd', [
      rangeRow({ range_id: 1, structure_layer: 'WEEKLY', parent_range_id: 404 }),
    ], { reason: 'unit_test' });

    expect(report.ok).toBe(true);
    expect(report.symbol).toBe('XAUUSD');
    expect(report.read_only).toBe(true);
    expect(report.reason).toBe('unit_test');
    expect(report.orphan_count).toBe(1);
    expect(report.suggested_merge_count).toBe(0);
    expect(report.suggested_merges).toEqual([]);
    expect(normaliseMaintenanceSymbol(' us500.cash ')).toBe('US500.CASH');
  });
});
