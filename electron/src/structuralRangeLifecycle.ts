export function activeStructuralRangeStatusFields(): { status: 'ACTIVE' } {
  return { status: 'ACTIVE' };
}

export function isStructuralRangeBrokenStatusValue(status: unknown): boolean {
  return String(status || '').toUpperCase() === 'BROKEN';
}

export function brokenStructuralRangeLifecycleFields(range: any): {
  status: 'BROKEN';
  broken_by_event_id: string | number | null;
  direction_of_break: 'UP' | 'DOWN' | null;
  inactive_from_time: string | null;
} {
  const direction = String(range?.direction_of_break || '').toUpperCase();
  return {
    status: 'BROKEN',
    broken_by_event_id: range?.broken_by_event_id ?? null,
    direction_of_break: direction === 'UP' || direction === 'DOWN' ? direction : null,
    inactive_from_time: range?.inactive_from_time ?? range?.range_end_time ?? null,
  };
}

export function structuralRangeStatusFieldsForSave(isBrokenUpdate: boolean, existingRange: any | null) {
  if (isBrokenUpdate && existingRange) return brokenStructuralRangeLifecycleFields(existingRange);
  return activeStructuralRangeStatusFields();
}
