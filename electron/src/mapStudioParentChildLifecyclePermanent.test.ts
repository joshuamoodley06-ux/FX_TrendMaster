import { describe, expect, it } from 'vitest';
import {
  childDraftAnchorTimesMs,
  evaluateChildMappingParentBlockReason,
  parentContainsChildByLifecycle,
} from './mapStudioMappingContext';

describe('permanent parent-child lifecycle overlap contract', () => {
  it('uses factual RH/RL anchors instead of stale restored window fields', () => {
    expect(childDraftAnchorTimesMs({
      range_high_time: '2025-12-31T00:00:00.000Z',
      range_low_time: '2025-12-30T00:00:00.000Z',
      active_from_time: '2025-11-01T00:00:00.000Z',
      range_start_time: '2025-11-01T00:00:00.000Z',
      range_end_time: '2026-02-01T00:00:00.000Z',
    })).toEqual([
      Date.parse('2025-12-31T00:00:00.000Z'),
      Date.parse('2025-12-30T00:00:00.000Z'),
    ]);
  });

  it('falls back to lifecycle window fields until both factual anchors exist', () => {
    expect(childDraftAnchorTimesMs({
      range_high_time: '2025-12-31T00:00:00.000Z',
      range_low_time: null,
      range_start_time: '2025-12-29T00:00:00.000Z',
      range_end_time: '2026-01-02T00:00:00.000Z',
    })).toEqual([
      Date.parse('2025-12-31T00:00:00.000Z'),
      Date.parse('2025-12-29T00:00:00.000Z'),
      Date.parse('2026-01-02T00:00:00.000Z'),
    ]);
  });

  it('allows child formation before the parent when the factual lifecycle overlaps', () => {
    const weekly = {
      range_id: '569',
      structure_layer: 'WEEKLY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      active_from_time: '2025-12-27T00:00:00.000Z',
      range_start_time: '2025-12-27T00:00:00.000Z',
    };

    expect(parentContainsChildByLifecycle(weekly, [
      Date.parse('2025-12-25T00:00:00.000Z'),
      Date.parse('2025-12-30T00:00:00.000Z'),
    ])).toBe(true);
  });

  it('blocks a child lifecycle that is fully disjoint from the parent', () => {
    const weekly = {
      range_id: '569',
      structure_layer: 'WEEKLY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      active_from_time: '2025-12-27T00:00:00.000Z',
      range_start_time: '2025-12-27T00:00:00.000Z',
    };

    expect(parentContainsChildByLifecycle(weekly, [
      Date.parse('2025-12-20T00:00:00.000Z'),
      Date.parse('2025-12-25T23:59:59.000Z'),
    ])).toBe(false);
  });

  it('allows a mid-Weekly Daily despite stale fallback dates', () => {
    const weekly = {
      range_id: '569',
      structure_layer: 'WEEKLY',
      range_scope: 'MAJOR',
      status: 'BROKEN',
      active_from_time: '2025-12-27T00:00:00.000Z',
      range_start_time: '2025-12-27T00:00:00.000Z',
      inactive_from_time: '2026-01-04T00:00:00.000Z',
    };

    expect(evaluateChildMappingParentBlockReason({
      structureLayer: 'DAILY',
      rangeScope: 'MAJOR',
      lockedChildMappingParentId: '569',
      childSpan: {
        range_high_time: '2025-12-31T00:00:00.000Z',
        range_low_time: '2025-12-30T00:00:00.000Z',
        active_from_time: '2025-11-01T00:00:00.000Z',
        range_start_time: '2025-11-01T00:00:00.000Z',
        range_end_time: '2026-02-01T00:00:00.000Z',
      },
      savedRanges: [weekly],
      resolvedParentId: '569',
      allowOrphanOverride: false,
    })).toBeNull();
  });

  it('applies the same factual-anchor rule to Daily-to-Intraday containment', () => {
    const daily = {
      range_id: '434',
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'BROKEN',
      active_from_time: '2026-02-01T00:00:00.000Z',
      range_start_time: '2026-02-01T00:00:00.000Z',
      inactive_from_time: '2026-03-03T00:00:00.000Z',
    };

    expect(evaluateChildMappingParentBlockReason({
      structureLayer: 'INTRADAY',
      rangeScope: 'MAJOR',
      lockedChildMappingParentId: '434',
      childSpan: {
        range_high_time: '2026-03-03T14:00:00.000Z',
        range_low_time: '2026-03-03T10:00:00.000Z',
        range_start_time: '2026-01-01T00:00:00.000Z',
        range_end_time: '2026-03-04T00:00:00.000Z',
      },
      savedRanges: [daily],
      resolvedParentId: '434',
      allowOrphanOverride: false,
    })).toBeNull();
  });

  it('still blocks Intraday after the Daily lifecycle', () => {
    const daily = {
      range_id: '434',
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'BROKEN',
      active_from_time: '2026-02-01T00:00:00.000Z',
      range_start_time: '2026-02-01T00:00:00.000Z',
      inactive_from_time: '2026-03-03T00:00:00.000Z',
    };

    expect(evaluateChildMappingParentBlockReason({
      structureLayer: 'INTRADAY',
      rangeScope: 'MAJOR',
      lockedChildMappingParentId: '434',
      childSpan: {
        range_high_time: '2026-03-04T14:00:00.000Z',
        range_low_time: '2026-03-04T10:00:00.000Z',
      },
      savedRanges: [daily],
      resolvedParentId: '434',
      allowOrphanOverride: false,
    })).toContain('Intraday window is not inside Daily #434');
  });
});