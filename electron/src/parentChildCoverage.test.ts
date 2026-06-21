import { describe, expect, it } from 'vitest';
import {
  buildGuidedCursorFromParent,
  guidedCursorResearchWindow,
} from './guidedMappingCursor';
import { getNextMappingTask } from './mappingCampaignManager';
import {
  computeParentChildCoverage,
  detectCoverageGaps,
  toleranceMsForChildLayer,
} from './parentChildCoverage';

const weeklyParent = {
  range_id: 7,
  structure_layer: 'WEEKLY',
  range_scope: 'MAJOR',
  status: 'ACTIVE',
  range_start_time: '2025-01-01T00:00:00.000Z',
  range_end_time: '2025-03-01T00:00:00.000Z',
};

describe('parentChildCoverage', () => {
  it('no children = NO_CHILDREN', () => {
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', []);
    expect(result.coverage_status).toBe('NO_CHILDREN');
    expect(result.child_count).toBe(0);
    expect(result.coverage_percent).toBe(0);
    expect(result.gap_count).toBe(1);
  });

  it('one child covering entire parent = COMPLETE_COVERAGE', () => {
    const ranges = [
      weeklyParent,
      {
        range_id: 71,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-03-01T00:00:00.000Z',
      },
    ];
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', ranges);
    expect(result.coverage_status).toBe('COMPLETE_COVERAGE');
    expect(result.coverage_percent).toBe(100);
    expect(result.gap_count).toBe(0);
  });

  it('detects front gap', () => {
    const tol = toleranceMsForChildLayer('DAILY');
    const gaps = detectCoverageGaps(
      Date.parse('2025-01-01T00:00:00.000Z'),
      Date.parse('2025-03-01T00:00:00.000Z'),
      [{ startMs: Date.parse('2025-01-10T00:00:00.000Z'), endMs: Date.parse('2025-02-01T00:00:00.000Z') }],
      tol,
    );
    expect(gaps.length).toBe(2);
    expect(gaps[0].startIso).toBe('2025-01-01T00:00:00.000Z');
    expect(gaps[0].endIso).toBe('2025-01-10T00:00:00.000Z');
  });

  it('detects middle gap', () => {
    const ranges = [
      weeklyParent,
      {
        range_id: 71,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-01-10T00:00:00.000Z',
      },
      {
        range_id: 72,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-02-01T00:00:00.000Z',
        range_end_time: '2025-02-15T00:00:00.000Z',
      },
    ];
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', ranges);
    expect(result.coverage_status).toBe('HAS_GAPS');
    expect(result.gap_count).toBeGreaterThanOrEqual(2);
    expect(result.first_gap_start).toBe('2025-01-10T00:00:00.000Z');
    expect(result.first_gap_end).toBe('2025-02-01T00:00:00.000Z');
    expect(result.coverage_percent).toBeGreaterThan(0);
    expect(result.coverage_percent).toBeLessThan(100);
  });

  it('detects tail gap', () => {
    const ranges = [
      weeklyParent,
      {
        range_id: 71,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-01-20T00:00:00.000Z',
      },
    ];
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', ranges);
    expect(result.coverage_status).toBe('HAS_GAPS');
    expect(result.gaps.some((g) => g.startIso === '2025-01-20T00:00:00.000Z')).toBe(true);
  });

  it('calculates partial coverage percentage', () => {
    const ranges = [
      weeklyParent,
      {
        range_id: 71,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-02-01T00:00:00.000Z',
      },
    ];
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', ranges);
    expect(result.coverage_percent).toBeGreaterThan(30);
    expect(result.coverage_percent).toBeLessThan(60);
  });

  it('detects out-of-window existing child', () => {
    const ranges = [
      weeklyParent,
      {
        range_id: 71,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        parent_range_id: 7,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-04-01T00:00:00.000Z',
      },
    ];
    const result = computeParentChildCoverage(weeklyParent, 'DAILY', ranges);
    expect(result.coverage_status).toBe('OUT_OF_WINDOW_CHILD');
  });

  it('Continue Campaign targets first coverage gap', () => {
    const ranges = [
      {
        range_id: 1,
        structure_layer: 'WEEKLY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-03-01T00:00:00.000Z',
      },
      {
        range_id: 10,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        range_start_time: '2025-01-01T00:00:00.000Z',
        range_end_time: '2025-01-10T00:00:00.000Z',
      },
      {
        range_id: 11,
        structure_layer: 'DAILY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        parent_range_id: 1,
        range_start_time: '2025-02-01T00:00:00.000Z',
        range_end_time: '2025-02-15T00:00:00.000Z',
      },
    ];
    const task = getNextMappingTask(ranges);
    expect(task.task).toBe('MAP_DAILY');
    expect(task.gap?.parentId).toBe('1');
    expect(task.gap?.coverage?.first_gap_start).toBe('2025-01-10T00:00:00.000Z');
    expect(task.gap?.coverage?.coverage_status).toBe('HAS_GAPS');
  });

  it('guided cursor starts at first_gap_start', () => {
    const gapStart = Date.parse('2025-01-10T00:00:00.000Z');
    const gapEnd = Date.parse('2025-02-01T00:00:00.000Z');
    const cursor = buildGuidedCursorFromParent(weeklyParent, '2025', gapStart, gapEnd);
    expect(cursor.cursor_time_ms).toBe(gapStart);
    expect(cursor.coverage_gap_end_ms).toBe(gapEnd);
    const win = guidedCursorResearchWindow(cursor);
    expect(win.start).toBe('2025-01-10T00:00:00.000Z');
    expect(win.end).toBe('2025-02-01T00:00:00.000Z');
  });
});
