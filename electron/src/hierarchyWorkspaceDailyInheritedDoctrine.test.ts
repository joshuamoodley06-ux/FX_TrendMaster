// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';
import {
  projectInheritedDailyDoctrineForHierarchy,
  projectInheritedLowerTimeframeDoctrineForHierarchy,
  renderNativeLayerAnnotations,
} from './hierarchyWorkspace';
import {
  doctrineNamespacesForLayer,
  flattenHierarchyNodes,
  hierarchyEnrichmentLookup,
  script1Labels,
} from './hierarchyWorkspaceCore';

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

function fixture(status = 'COMPLETE', profileStatus = 'COMPLETE') {
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
            daily_profile_classification: memory(profileStatus, { profile_classification: 'S&D' }),
          },
          children: [{
            id: 'intraday-900',
            structure_layer: 'INTRADAY',
            source_refs: [{ raw_id: 900, case_ref: 'case:live', source_record_id: 'intraday-900' }],
            analysis_enrichments: {
              intraday_structure: memory('COMPLETE', { chronology: 'RH_TO_RL', bos_direction: 'BOS_DOWN' }),
              intraday_reclaim: memory('COMPLETE', { reclaim_status: 'ABANDONED' }),
              intraday_profile_classification: memory('COMPLETE', { profile_classification: 'S&R' }),
            },
            children: [],
          }],
        }],
      }],
    },
  };
}

describe('inherited lower-timeframe hierarchy projection', () => {
  it('keeps Daily doctrine on the original native Daily node', () => {
    const original = fixture();
    const result = projectInheritedDailyDoctrineForHierarchy(original);
    const children = (result.masterMap as any).trusted_root.children;
    const daily = children[0].children[0];
    expect(children).toHaveLength(1);
    expect(daily.id).toBe('daily-662');
    expect(daily.structure_layer).toBe('DAILY');
    expect(daily.analysis_enrichments.daily_structure.payload.bos_direction).toBe('BOS_UP');
    expect(daily.analysis_enrichments.daily_reclaim.payload.reclaim_status).toBe('RECLAIMED');
    expect(daily.analysis_enrichments.daily_profile_classification.payload.profile_classification).toBe('S&D');
    expect(daily.children[0].id).toBe('intraday-900');
    expect(result.masterMap).toBe(original);
  });

  it('uses the same native namespace resolver for future Intraday doctrine', () => {
    const result = projectInheritedLowerTimeframeDoctrineForHierarchy(fixture());
    const intraday = (result.masterMap as any).trusted_root.children[0].children[0].children[0];
    expect(intraday.structure_layer).toBe('INTRADAY');
    expect(intraday.analysis_enrichments.intraday_structure.payload.bos_direction).toBe('BOS_DOWN');
    expect(doctrineNamespacesForLayer('INTRADAY')).toEqual({
      structure: 'intraday_structure',
      reclaim: 'intraday_reclaim',
      profile: 'intraday_profile_classification',
    });
  });

  it('returns lower-timeframe source ids when any inherited stage needs review', () => {
    const result = projectInheritedLowerTimeframeDoctrineForHierarchy(fixture('COMPLETE', 'NEEDS_REVIEW'));
    expect(Array.from(result.needsReviewSourceIds).sort()).toEqual(['662', 'daily-662']);
  });

  it('renders compact native Daily facts and review from any inherited stage', () => {
    const raw = fixture('COMPLETE', 'NEEDS_REVIEW').trusted_root.children[0].children[0];
    const analysisEnrichments = Object.fromEntries(
      Object.entries(raw.analysis_enrichments).map(([key, value]: [string, any]) => [
        key,
        { payload: value.payload },
      ]),
    );
    const labels = script1Labels({
      layer: 'DAILY',
      analysisEnrichments,
      script1Chronology: null,
      script1BosDirection: null,
      script1ReviewStatus: null,
    } as any);
    expect(labels).toEqual({
      chronology: 'RL → RH',
      bos: 'BOS Up · RECL · ◆ S&D',
      status: 'Needs Review',
    });
  });

  it('builds the enrichment lookup recursively without changing hierarchy order', () => {
    const intraday = { canonicalRangeId: 'intraday', children: [] } as any;
    const daily1 = { canonicalRangeId: 'daily-1', children: [intraday] } as any;
    const daily2 = { canonicalRangeId: 'daily-2', children: [] } as any;
    const weekly = { canonicalRangeId: 'weekly', children: [daily1, daily2] } as any;
    expect(flattenHierarchyNodes([weekly]).map((node) => node.canonicalRangeId)).toEqual([
      'weekly', 'daily-1', 'intraday', 'daily-2',
    ]);
    expect(weekly.children).toEqual([daily1, daily2]);
  });

  it('matches persisted raw-prefixed case refs to the active case', () => {
    const raw = fixture().trusted_root.children[0].children[0];
    raw.source_refs[0].case_ref = 'raw:0900da83-e96d-4baf-9f49-b7e96e382dfd';
    const node = {
      layer: 'DAILY',
      sourceRefs: raw.source_refs.map((ref) => ({
        rawId: ref.raw_id,
        caseRef: ref.case_ref,
        sourceRecordId: ref.source_record_id,
      })),
      analysisEnrichments: Object.fromEntries(
        Object.entries(raw.analysis_enrichments).map(([key, value]: [string, any]) => [
          key,
          { payload: value.payload },
        ]),
      ),
      children: [],
    } as any;
    const lookup = hierarchyEnrichmentLookup([node], '0900da83-e96d-4baf-9f49-b7e96e382dfd');
    expect(lookup.get('662')).toMatchObject({
      chronology: 'RL → RH',
      bos: 'BOS Up · RECL · ◆ S&D',
    });
  });

  it('renders native Daily doctrine on the one original row under its Weekly parent', () => {
    const enrichment = new Map([['710', {
      chronology: 'RL → RH',
      bos: 'BOS Up · RECL · ◆ S&D',
      status: 'Approved',
    }]]);
    const structure = createElement('div', { 'data-range-id': '640', className: 'explorerTreeRow' },
      createElement('button', { className: 'explorerTreeRowMain' },
        createElement('span', { className: 'explorerTreeLine1' }, 'WEEKLY MAJOR #640')),
      createElement('div', { 'data-range-id': '710', className: 'explorerTreeRow' },
        createElement('button', { className: 'explorerTreeRowMain' },
          createElement('span', { className: 'explorerTreeLine1' }, 'R1 DAILY MAJOR #710 · Mar 23 2026'))));
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => root.render(renderNativeLayerAnnotations(structure, enrichment)));

    const weekly = container.querySelector('[data-range-id="640"]')!;
    const dailyRows = weekly.querySelectorAll('[data-range-id="710"]');
    expect(dailyRows).toHaveLength(1);
    expect(dailyRows[0].textContent).toContain('R1 DAILY MAJOR #710 · Mar 23 2026');
    expect(dailyRows[0].textContent).toContain('RL → RH');
    expect(dailyRows[0].textContent).toContain('BOS Up');
    expect(dailyRows[0].textContent).toContain('RECL');
    expect(dailyRows[0].textContent).toContain('◆ S&D');

    act(() => root.unmount());
    container.remove();
  });
});
