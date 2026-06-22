import { describe, expect, it } from 'vitest';
import {
  activeStructuralRangeStatusFields,
  brokenStructuralRangeLifecycleFields,
  structuralRangeStatusFieldsForSave,
} from './structuralRangeLifecycle';

describe('structuralRangeLifecycle', () => {
  it('active saves emit ACTIVE only', () => {
    expect(activeStructuralRangeStatusFields()).toEqual({ status: 'ACTIVE' });
  });

  it('broken updates preserve lifecycle fields from existing row', () => {
    const existing = {
      status: 'BROKEN',
      broken_by_event_id: 'evt-42',
      direction_of_break: 'UP',
      inactive_from_time: '2025-03-10T00:00:00.000Z',
    };
    expect(brokenStructuralRangeLifecycleFields(existing)).toEqual({
      status: 'BROKEN',
      broken_by_event_id: 'evt-42',
      direction_of_break: 'UP',
      inactive_from_time: '2025-03-10T00:00:00.000Z',
    });
    expect(structuralRangeStatusFieldsForSave(true, existing)).toEqual({
      status: 'BROKEN',
      broken_by_event_id: 'evt-42',
      direction_of_break: 'UP',
      inactive_from_time: '2025-03-10T00:00:00.000Z',
    });
  });

  it('non-broken updates stay ACTIVE', () => {
    expect(structuralRangeStatusFieldsForSave(false, { status: 'BROKEN' })).toEqual({ status: 'ACTIVE' });
    expect(structuralRangeStatusFieldsForSave(true, null)).toEqual({ status: 'ACTIVE' });
  });
});
