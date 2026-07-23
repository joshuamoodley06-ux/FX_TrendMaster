import { describe, expect, it } from 'vitest';
import { projectInheritedDailyDoctrineForHierarchy } from './hierarchyWorkspace';

function memory(status: string, payload: Record<string, unknown>) {
  return {
    version_id: 'inherited:weekly-approved',
    version_label: 'approved',
    adapter_key: 'inherited_weekly_doctrine_v1',
    output_hash: `${status}-hash`,
    processing_status: status,
    payload: { ...payload, inherited_processing_status: status },
  };
}

function fixture(status = 'COMPLETE') {
  return {
    trusted_root: {
      children: [{
        id: 'weekly-1',
        structure_layer: 'WEEKLY',
        source_refs: [{ raw_id: 737, case_ref: 'case:live', source_record_id: 'weekly-737' }],
        children: [{
          id: 'daily-662',
          structure_layer: 'DAILY',
          source_refs: [{ raw_id: 662, case_ref: 'case:live', source_record_id: 'daily-662' }],
          analysis_enrichments: {
            daily_structure: memory(status, { chronology: 'RL_TO_RH', bos_direction: 'BOS_UP' }),
            daily_reclaim: memory('COMPLETE', { reclaim_status: 'RECLAIMED' }),
            daily_profile_classification: memory('COMPLETE', { profile_classification: 'S&D' }),
          },
          children: [],
        }],
      }],
    },
  };
}

describe('inherited Daily hierarchy projection', () => {
  it('projects Daily doctrine into the existing Weekly renderer namespace', () => {
    const original = fixture();
    const result = projectInheritedDailyDoctrineForHierarchy(original);
    const children = (result.masterMap as any).trusted_root.children;
    expect(children).toHaveLength(2);
    expect(children[1].id).toBe('daily-662');
    expect(children[1].structure_layer).toBe('WEEKLY');
    expect(children[1].analysis_enrichments.weekly_structure.payload.bos_direction).toBe('BOS_UP');
    expect(children[1].analysis_enrichments.weekly_reclaim.payload.reclaim_status).toBe('RECLAIMED');
    expect(children[1].analysis_enrichments.weekly_profile_classification.payload.profile_classification).toBe('S&D');
    expect((original as any).trusted_root.children).toHaveLength(1);
  });

  it('returns only Daily source ids that need trader review', () => {
    const result = projectInheritedDailyDoctrineForHierarchy(fixture('NEEDS_REVIEW'));
    expect(Array.from(result.needsReviewSourceIds).sort()).toEqual(['662', 'daily-662']);
  });
});
