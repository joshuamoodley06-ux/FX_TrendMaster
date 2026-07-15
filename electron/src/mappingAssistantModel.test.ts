import { describe, expect, it } from 'vitest';

import { computeMappingGaps } from './mappingWorkflow';
import {
  adaptMappingAssistantSnapshot,
  masterMapDocumentToCoverageRanges,
  navigationRequestForAssistantTarget,
  navigationRequestForCoverageGap,
} from './mappingAssistantModel';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function snapshotFixture(): Record<string, unknown> {
  const hash = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';
  return {
    schema_version: 'xauusd_mapping_assistant_snapshot_v0.1',
    generated_at_utc: '2026-07-15T00:00:00Z',
    symbol: 'XAUUSD',
    structural_content_hash: hash,
    summary: {
      research_gap_count: 1,
      blocked_candidate_count: 13,
      unique_weekly_parent_count: 1,
      structure_query_ready_count: 0,
      confirmation_query_ready_count: 0,
      outcome_query_ready_count: 0,
      overall_first_query_ready_count: 0,
    },
    gaps: [
      {
        schema_version: 'xauusd_mapping_assistant_gap_v0.1',
        gap_id: 'mapping-gap:weekly',
        priority_rank: 1,
        gap_type: 'RESEARCH_EVIDENCE',
        symbol: 'XAUUSD',
        parent: {
          canonical_range_id: 'mm:range:weekly-trusted',
          source_range_ids: ['431'],
          structure_layer: 'WEEKLY',
          source_timeframe: 'W1',
          range_high: 2800,
          range_low: 2300,
          range_high_time: '2026-01-04T00:00:00Z',
          range_low_time: '2026-01-01T00:00:00Z',
          active_from_time: '2026-01-04T00:00:00Z',
          inactive_from_time: '2026-03-01T00:00:00Z',
          status: 'BROKEN',
          navigation_status: 'TRUSTED',
          statistics_status: 'ELIGIBLE',
          source_refs: [],
        },
        research_impact: {
          blocked_candidate_count: 13,
          blocked_candidate_ids: ['candidate-1'],
          earliest_candidate_freeze: '2026-02-02T00:00:00Z',
          latest_candidate_freeze: '2026-02-20T00:00:00Z',
        },
        requirement: {
          missing_evidence_code: ['APPROVED_PREFREEZE_WEEKLY_DIRECTION_EVIDENCE'],
          recommended_action_code: 'MAP_WEEKLY_FORMATION_BOS',
          evidence_already_present: [],
          trader_title: 'Weekly direction evidence missing',
          trader_instruction: 'Review the move that created this Weekly parent.',
        },
        navigation: {
          open_structure: {
            canonical_range_id: 'mm:range:weekly-trusted',
            event_id: null,
            target_layer: 'WEEKLY',
            target_timeframe: 'W1',
            preferred_anchor_time: '2026-01-04T00:00:00Z',
            visible_start: '2025-10-01T00:00:00Z',
            visible_end: '2026-02-02T00:00:00Z',
          },
          show_first_candidate: {
            canonical_range_id: 'mm:range:daily-trusted',
            event_id: 'mm:event:bos-1',
            target_layer: 'DAILY',
            target_timeframe: 'D1',
            preferred_anchor_time: '2026-02-02T00:00:00Z',
            visible_start: '2026-01-01T00:00:00Z',
            visible_end: '2026-02-16T00:00:00Z',
          },
        },
      },
    ],
    master_map: masterMapFixture(),
    determinism_hash: 'd'.repeat(64),
    source_integrity: {
      database_path: 'C:/FXTM/range_library_memory.sqlite3',
      sha256_before: 'e'.repeat(64),
      sha256_after: 'e'.repeat(64),
      unchanged: true,
      build_mode: 'DISPOSABLE_SQLITE_BACKUP',
    },
  };
}

describe('Mapping Assistant adapter', () => {
  it('adapts a source-integrity-checked snapshot', () => {
    const snapshot = adaptMappingAssistantSnapshot(snapshotFixture());
    expect(snapshot.summary.researchGapCount).toBe(1);
    expect(snapshot.summary.blockedCandidateCount).toBe(13);
    expect(snapshot.gaps[0].requirement.traderTitle).toBe('Weekly direction evidence missing');
    expect(snapshot.sourceIntegrity.unchanged).toBe(true);
  });

  it('rejects a changed source database', () => {
    const fixture = snapshotFixture();
    (fixture.source_integrity as Record<string, unknown>).sha256_after = 'f'.repeat(64);
    expect(() => adaptMappingAssistantSnapshot(fixture)).toThrow(/integrity/);
  });

  it('builds an exact GAP navigation request for Python guidance', () => {
    const snapshot = adaptMappingAssistantSnapshot(snapshotFixture());
    const request = navigationRequestForAssistantTarget(
      snapshot.gaps[0].navigation.showFirstCandidate,
      snapshot.masterMap,
    );
    expect(request).toMatchObject({
      canonicalRangeId: 'mm:range:daily-trusted',
      layer: 'DAILY',
      sourceTimeframe: 'D1',
      reason: 'GAP',
      eventId: 'mm:event:bos-1',
      preferredAnchorTime: '2026-02-02T00:00:00Z',
      visibleStart: '2026-01-01T00:00:00Z',
      visibleEnd: '2026-02-16T00:00:00Z',
    });
  });
});

describe('Mapping Assistant coverage projection', () => {
  it('projects Master Map hierarchy into the existing gap detector', () => {
    const snapshot = adaptMappingAssistantSnapshot(snapshotFixture());
    const records = masterMapDocumentToCoverageRanges(snapshot.masterMap);
    const dailyGaps = computeMappingGaps(records, 'htf').filter(
      (gap) => gap.parentLayer === 'WEEKLY' && gap.expectedChildLayer === 'DAILY',
    );
    expect(dailyGaps).toHaveLength(1);
    expect(dailyGaps[0].parentId).toBe('mm:range:weekly-trusted');
  });

  it('routes coverage gaps into the expected child layer and window', () => {
    const snapshot = adaptMappingAssistantSnapshot(snapshotFixture());
    const records = masterMapDocumentToCoverageRanges(snapshot.masterMap);
    const gap = computeMappingGaps(records, 'htf').find(
      (item) => item.parentLayer === 'WEEKLY' && item.expectedChildLayer === 'DAILY',
    );
    expect(gap).toBeTruthy();
    const request = navigationRequestForCoverageGap(gap!, snapshot.masterMap);
    expect(request).toMatchObject({
      canonicalRangeId: 'mm:range:weekly-trusted',
      layer: 'DAILY',
      sourceTimeframe: 'D1',
      reason: 'GAP',
    });
    expect(request?.visibleStart).toBeTruthy();
    expect(request?.visibleEnd).toBeTruthy();
  });
});
