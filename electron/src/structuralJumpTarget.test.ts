import { describe, expect, it } from 'vitest';
import {
  normalizeGapTarget,
  normalizeReviewTarget,
  normalizeStructuralEventTarget,
  normalizeStructuralRangeTarget,
} from './structuralJumpTarget';

const canonicalDaily = {
  id: 'mm:range:daily-420',
  node_type: 'RANGE',
  symbol: 'XAUUSD',
  structure_layer: 'DAILY',
  source_timeframe: 'D1',
  range_high_time: '2026-06-10T00:00:00Z',
  range_low_time: '2026-06-12T00:00:00Z',
  active_from_time: '2026-06-12T00:00:00Z',
  inactive_from_time: null,
  navigation_status: 'REVIEW',
  statistics_status: 'EXCLUDED',
  direct_parent_link_status: 'NEEDS_REVIEW',
  source_refs: [
    { raw_id: 77, case_ref: 'case-live', source_record_id: '420', payload_sha256: 'abc' },
  ],
};

describe('structuralJumpTarget', () => {
  it('normalizes a canonical Master Map range and preserves source provenance', () => {
    const target = normalizeStructuralRangeTarget(canonicalDaily, 'HIERARCHY');
    expect(target).toMatchObject({
      symbol: 'XAUUSD',
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      canonicalRangeId: 'mm:range:daily-420',
      preferredAnchorTime: '2026-06-12T00:00:00.000Z',
      reason: 'HIERARCHY',
    });
    expect(target?.sourceRecordProvenance.caseRefs).toEqual(['case-live']);
    expect(target?.sourceRecordProvenance.sourceRecordIds).toEqual(['420']);
  });

  it('normalizes an event against its canonical range and prefers the event time', () => {
    const target = normalizeStructuralEventTarget({
      id: 'mm:event:break-420',
      event_time_utc: '2026-06-18T00:00:00Z',
      source_refs: [{ case_ref: 'case-live', source_record_id: '9001' }],
    }, canonicalDaily);
    expect(target?.eventId).toBe('mm:event:break-420');
    expect(target?.preferredAnchorTime).toBe('2026-06-18T00:00:00.000Z');
    expect(target?.sourceRecordProvenance.sourceRecordIds).toEqual(['420', '9001']);
  });

  it('normalizes a coverage gap onto the missing child timeframe and exact gap window', () => {
    const target = normalizeGapTarget({
      parentId: 'mm:range:weekly-1',
      parentRange: {
        symbol: 'XAUUSD',
        structure_layer: 'WEEKLY',
        source_timeframe: 'W1',
        range_high_time: '2026-01-04T00:00:00Z',
        range_low_time: '2026-01-11T00:00:00Z',
        active_from_time: '2026-01-11T00:00:00Z',
        source_refs: [{ case_ref: 'case-a', source_record_id: '418' }],
      },
      parentLayer: 'WEEKLY',
      expectedChildLayer: 'DAILY',
      coverage: {
        first_gap_start: '2026-02-03T00:00:00Z',
        first_gap_end: '2026-02-09T00:00:00Z',
      },
    });
    expect(target).toMatchObject({
      canonicalRangeId: 'mm:range:weekly-1',
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      preferredAnchorTime: '2026-02-03T00:00:00.000Z',
      visibleWindow: {
        start: '2026-02-03T00:00:00.000Z',
        end: '2026-02-09T00:00:00.000Z',
      },
      reason: 'GAP',
    });
  });

  it('keeps Daily 420 reviewable with case/source provenance and does not invent a parent', () => {
    const target = normalizeReviewTarget({
      review_key: 'mm:review:daily-420',
      item_type: 'PARENT_LINK_NEEDS_REVIEW',
      entity_kind: 'RANGE',
      status: 'NEEDS_REVIEW',
      canonical_ids: ['mm:range:daily-420'],
      case_refs: ['case-live'],
      source_record_ids: ['420'],
      reason_codes: ['EXPLICIT_PARENT_FACTS_DISAGREE'],
    }, { canonicalRange: canonicalDaily });
    expect(target?.reason).toBe('REVIEW');
    expect(target?.canonicalRangeId).toBe('mm:range:daily-420');
    expect(target?.sourceRecordProvenance).toMatchObject({
      caseRefs: ['case-live'],
      sourceRecordIds: ['420'],
      reviewKey: 'mm:review:daily-420',
      itemType: 'PARENT_LINK_NEEDS_REVIEW',
    });
    expect(Object.prototype.hasOwnProperty.call(target || {}, 'parentRangeId')).toBe(false);
  });

  it('supports the legacy review/audit shape without losing case_ref', () => {
    const target = normalizeReviewTarget({
      range_id: 88,
      symbol: 'XAUUSD',
      structure_layer: 'INTRADAY',
      source_timeframe: 'H4',
      range_high_time: '2026-04-01T08:00:00Z',
      range_low_time: '2026-04-01T12:00:00Z',
      range_start_time: '2026-04-01T12:00:00Z',
      range_end_time: '2026-04-02T08:00:00Z',
      case_ref: 'legacy-case',
      source_record_id: '88',
      replay_until_time: '2026-04-02T08:00:00Z',
    });
    expect(target).toMatchObject({
      structureLayer: 'INTRADAY',
      sourceTimeframe: 'H4',
      canonicalRangeId: '88',
      reason: 'REVIEW',
    });
    expect(target?.preferredAnchorTime).toBe('2026-04-02T08:00:00.000Z');
    expect(target?.visibleWindow).toEqual({
      start: '2026-04-01T12:00:00.000Z',
      end: '2026-04-02T08:00:00.000Z',
    });
    expect(target?.sourceRecordProvenance.caseRefs).toEqual(['legacy-case']);
  });

  it('orders reversed explicit windows and rejects incomplete structural identity', () => {
    const ordered = normalizeStructuralRangeTarget(canonicalDaily, 'HIERARCHY', {
      visibleStart: '2026-06-20T00:00:00Z',
      visibleEnd: '2026-06-01T00:00:00Z',
    });
    expect(ordered?.visibleWindow).toEqual({
      start: '2026-06-01T00:00:00.000Z',
      end: '2026-06-20T00:00:00.000Z',
    });
    expect(normalizeStructuralRangeTarget({ symbol: 'XAUUSD', structure_layer: 'DAILY' })).toBeNull();
  });
});
