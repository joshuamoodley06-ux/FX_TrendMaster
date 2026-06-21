import { describe, expect, it } from 'vitest';
import {
  advanceGuidedCursorAfterChildSave,
  buildGuidedCursorFromParent,
  filterCandidatesAfterCursor,
  findNextSiblingParent,
  guidedCursorResearchWindow,
  guidedCursorToSessionFields,
  isGuidedParentComplete,
  markGuidedParentComplete,
} from './guidedMappingCursor';

describe('guidedMappingCursor', () => {
  const weeklyParent = {
    range_id: 7,
    structure_layer: 'WEEKLY',
    range_scope: 'MAJOR',
    range_start_time: '2025-03-01T00:00:00.000Z',
    range_end_time: '2025-06-15T00:00:00.000Z',
    range_high_price: 3400,
    range_low_price: 3200,
  };

  it('builds cursor from parent range at start', () => {
    const cursor = buildGuidedCursorFromParent(weeklyParent, '2025');
    expect(cursor.active_parent_range_id).toBe('7');
    expect(cursor.active_child_layer).toBe('DAILY');
    expect(cursor.cursor_status).toBe('MAPPING_CHILD');
    expect(cursor.cursor_time_ms).toBe(cursor.parent_start_time_ms);
  });

  it('narrows research window from cursor position', () => {
    const cursor = buildGuidedCursorFromParent(weeklyParent, '2025', Date.parse('2025-04-01T00:00:00.000Z'));
    const win = guidedCursorResearchWindow(cursor);
    expect(win.dateFrom).toBe('2025-04-01');
    expect(win.dateTo).toBe('2025-06-15');
  });

  it('advances cursor after child save', () => {
    const base = buildGuidedCursorFromParent(weeklyParent, '2025');
    const next = advanceGuidedCursorAfterChildSave(base, {
      rangeId: '42',
      rangeEndTime: '2025-04-10T00:00:00.000Z',
      bosTime: '2025-04-09T12:00:00.000Z',
    });
    expect(next.current_child_index).toBe(1);
    expect(next.saved_child_ids).toContain('42');
    expect(next.cursor_time_ms).toBeGreaterThan(base.cursor_time_ms);
  });

  it('marks parent complete at end', () => {
    const cursor = markGuidedParentComplete(buildGuidedCursorFromParent(weeklyParent, '2025'));
    expect(isGuidedParentComplete(cursor)).toBe(true);
    expect(cursor.cursor_status).toBe('PARENT_COMPLETE');
  });

  it('filters candidates after cursor time', () => {
    const samples = [
      { range_start_time: '2025-03-05T00:00:00.000Z' },
      { replay_until_time: '2025-04-12T00:00:00.000Z' },
    ] as any[];
    const cursor = buildGuidedCursorFromParent(weeklyParent, '2025', Date.parse('2025-04-01T00:00:00.000Z'));
    const filtered = filterCandidatesAfterCursor(samples, cursor.cursor_time_ms);
    expect(filtered).toHaveLength(1);
  });

  it('finds next sibling parent', () => {
    const ranges = [
      { range_id: '7', structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', range_start_time: '2025-03-01' },
      { range_id: '8', structure_layer: 'WEEKLY', range_scope: 'MAJOR', status: 'ACTIVE', range_start_time: '2025-06-20' },
    ];
    const next = findNextSiblingParent('7', 'WEEKLY', ranges);
    expect(next?.range_id).toBe('8');
  });

  it('serializes cursor to session fields', () => {
    const cursor = buildGuidedCursorFromParent(weeklyParent, '2025');
    const fields = guidedCursorToSessionFields(cursor);
    expect(fields.guidedCursorActive).toBe(true);
    expect(fields.guidedParentRangeId).toBe('7');
  });
});
