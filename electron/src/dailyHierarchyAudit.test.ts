import { describe, expect, it } from 'vitest';
import { buildDailyHierarchyAuditLayout } from './dailyHierarchyAudit';

describe('buildDailyHierarchyAuditLayout', () => {
  it('numbers Daily children in visible hierarchy order and resets for each Weekly parent', () => {
    const layout = buildDailyHierarchyAuditLayout([
      { rangeId: 'weekly-1', layer: 'WEEKLY', depth: 0 },
      { rangeId: 'daily-1', layer: 'DAILY', depth: 1 },
      { rangeId: 'intraday-1', layer: 'INTRADAY', depth: 2 },
      { rangeId: 'daily-2', layer: 'DAILY', depth: 1 },
      { rangeId: 'weekly-2', layer: 'WEEKLY', depth: 0 },
      { rangeId: 'daily-3', layer: 'DAILY', depth: 1 },
    ]);

    expect(layout.rows.map((row) => [row.rangeId, row.dailySequenceNumber])).toEqual([
      ['weekly-1', null],
      ['daily-1', 1],
      ['intraday-1', null],
      ['daily-2', 2],
      ['weekly-2', null],
      ['daily-3', 1],
    ]);
    expect(layout.weeklySummaries).toEqual([
      { weeklyRangeId: 'weekly-1', dailyCount: 2, invalidCount: 0 },
      { weeklyRangeId: 'weekly-2', dailyCount: 1, invalidCount: 0 },
    ]);
  });

  it('marks an orphan Daily invalid and refuses to invent a Weekly parent or R number', () => {
    const layout = buildDailyHierarchyAuditLayout([
      { rangeId: 'weekly-1', layer: 'WEEKLY', depth: 0 },
      { rangeId: 'daily-1', layer: 'DAILY', depth: 1 },
      { rangeId: 'daily-orphan', layer: 'DAILY', depth: 0, orphan: true },
    ]);

    const orphan = layout.rows.find((row) => row.rangeId === 'daily-orphan');
    expect(orphan).toMatchObject({
      parentWeeklyRangeId: null,
      dailySequenceNumber: null,
      linkStatus: 'INVALID',
    });
    expect(orphan?.linkReason).toContain('unlinked or orphaned');
  });

  it('clears Weekly scope after an orphan so later rows cannot borrow the old parent', () => {
    const layout = buildDailyHierarchyAuditLayout([
      { rangeId: 'weekly-1', layer: 'WEEKLY', depth: 0 },
      { rangeId: 'daily-1', layer: 'DAILY', depth: 1 },
      { rangeId: 'daily-orphan', layer: 'DAILY', depth: 0, orphan: true },
      { rangeId: 'daily-after-orphan', layer: 'DAILY', depth: 1 },
    ]);

    expect(layout.rows.find((row) => row.rangeId === 'daily-after-orphan')).toMatchObject({
      parentWeeklyRangeId: null,
      dailySequenceNumber: null,
      linkStatus: 'INVALID',
    });
  });

  it('does not borrow the previous Weekly parent after the hierarchy returns to another root layer', () => {
    const layout = buildDailyHierarchyAuditLayout([
      { rangeId: 'weekly-1', layer: 'WEEKLY', depth: 1 },
      { rangeId: 'daily-1', layer: 'DAILY', depth: 2 },
      { rangeId: 'macro-2', layer: 'MACRO', depth: 0 },
      { rangeId: 'daily-unlinked', layer: 'DAILY', depth: 1 },
    ]);

    expect(layout.rows.find((row) => row.rangeId === 'daily-unlinked')).toMatchObject({
      parentWeeklyRangeId: null,
      dailySequenceNumber: null,
      linkStatus: 'INVALID',
    });
  });

  it('preserves the hierarchy order instead of sorting by ids', () => {
    const layout = buildDailyHierarchyAuditLayout([
      { rangeId: 'weekly-1', layer: 'WEEKLY', depth: 0 },
      { rangeId: 'daily-900', layer: 'DAILY', depth: 1 },
      { rangeId: 'daily-100', layer: 'DAILY', depth: 1 },
    ]);

    expect(layout.rows.filter((row) => row.layer === 'DAILY').map((row) => ({
      id: row.rangeId,
      sequence: row.dailySequenceNumber,
    }))).toEqual([
      { id: 'daily-900', sequence: 1 },
      { id: 'daily-100', sequence: 2 },
    ]);
  });
});
