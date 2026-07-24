// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function fixtureWithTwoWeeklyRanges() {
  const value = masterMapFixture() as any;
  const range1 = value.trusted_root.children[0];
  range1.source_refs = [{
    raw_id: 1,
    case_ref: 'case:live',
    source_record_id: 'backend-weekly-1',
    payload_sha256: 'sha-1',
  }];
  const range2 = structuredClone(range1);
  range2.id = 'mm:range:weekly-2';
  range2.range_high = 4381.25;
  range2.range_low = 3579.48;
  range2.range_high_time = '2025-10-19T00:00:00Z';
  range2.range_low_time = '2025-09-07T00:00:00Z';
  range2.active_from_time = '2025-10-19T00:00:00Z';
  range2.source_refs = [{
    raw_id: 2,
    case_ref: 'case:live',
    source_record_id: 'backend-weekly-2',
    payload_sha256: 'sha-2',
  }];
  value.trusted_root.children = [range1, range2];
  return value;
}

function approvedScript(id: string, key: string, name: string, order: number, version: string) {
  const versionId = `${id}-v${version}`;
  return {
    script_id: id,
    script_key: key,
    display_name: name,
    execution_order: order,
    status: 'APPROVED',
    current_approved_version_id: versionId,
    version_id: versionId,
    version_label: version,
    latest_version_status: 'APPROVED',
    package_dependency_ready: true,
    adapter_key: 'doctrine_package_v1',
    doctrine_state: {
      status: 'APPROVED',
      current_approved_version_id: versionId,
      versions: [{ version_id: versionId, version_label: version }],
      runs: [],
    },
  };
}

describe('HierarchyWorkspace depth range navigation', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  it('defaults the audit card to Range 2 and keeps explicit Range 1 and Range 2 controls after approval', async () => {
    const map = fixtureWithTwoWeeklyRanges();
    const depthState = {
      status: 'APPROVED',
      current_approved_version_id: 'depth-v6',
      versions: [{ version_id: 'depth-v6', version_label: '6' }],
      runs: [{
        run: {
          run_id: 'run-depth-v6',
          version_id: 'depth-v6',
          case_ref: 'case:live',
          symbol: 'XAUUSD',
          approval_status: 'APPROVED',
          publication_status: 'PUBLISHED',
          eligible_count: 1,
          analysed_count: 1,
          sample_count: 1,
          approval_count: 1,
        },
        samples: [{
          canonical_range_id: 'mm:range:weekly-trusted',
          sample_order: 0,
          decision: 'APPROVED',
          decided_at: '2026-07-22T10:00:00Z',
          processing_status: 'COMPLETE',
          payload: {
            depth_status: 'NO_RETRACEMENT',
            source_range1_id: 'mm:range:weekly-trusted',
            source_bos_direction: 'BOS_UP',
            source_bos_time: '2025-04-06T00:00:00Z',
            source_reclaim_status: 'RECLAIMED',
            source_reclaim_abbreviation: 'RECL',
            source_reclaim_time: '2025-05-11T00:00:00Z',
            source_weeks_to_reclaim: 5,
            range1_high: 3167.56,
            range1_low: 2832.58,
            range1_size: 334.98,
            fib_zero_price: 3167.56,
            fib_one_price: 2832.58,
            range2_id: 'mm:range:weekly-2',
            range2_completed_at: '2025-10-19T00:00:00Z',
            range2_chronology: 'RL_TO_RH',
            range2_anchor_sequence: 'OPPOSITE_THEN_CONTINUATION',
            range2_opposite_anchor_type: 'RL',
            range2_opposite_anchor_price: 3579.48,
            range2_opposite_anchor_time: '2025-09-07T00:00:00Z',
            range2_continuation_anchor_type: 'RH',
            range2_continuation_anchor_price: 4381.25,
            range2_continuation_anchor_time: '2025-10-19T00:00:00Z',
            reclaim_depth_price: 0,
            reclaim_depth_ratio: 0,
            reclaim_depth_percent: 0,
            raw_reclaim_depth_price: -411.92,
            raw_reclaim_depth_ratio: -1.2297,
            raw_reclaim_depth_percent: -122.97,
            boundary_distance_price: 411.92,
            boundary_position: 'ABOVE_BROKEN_RH',
            weeks_bos_to_depth_anchor: 22,
            weeks_reclaim_to_depth_anchor: 17,
            weeks_bos_to_range2_completion: 28,
            weeks_reclaim_to_range2_completion: 23,
            range2_formation_weeks: 6,
            old_opposite_external_touched: false,
            old_opposite_external_exceeded: false,
            reason_codes: ['RANGE2_OPPOSITE_411.9200_ABOVE_BROKEN_RH'],
          },
        }],
      }],
    };
    const scripts = [
      approvedScript('bos', 'weekly_structure', 'Weekly BOS', 10, '3'),
      approvedScript('reclaim', 'weekly_reclaim', 'Weekly Reclaim', 20, '2'),
      {
        ...approvedScript('depth', 'weekly_reclaim_depth', 'Weekly Reclaim Depth', 30, '6'),
        doctrine_state: depthState,
      },
    ];
    const onNavigateRange = vi.fn();
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: map,
        scripts,
      }),
      runWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: scripts }),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn(),
      reviewDoctrineSample: vi.fn(),
    };

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [
        { range_id: 1, structure_layer: 'WEEKLY', range_high: 3167.56, range_low: 2832.58 },
        { range_id: 2, structure_layer: 'WEEKLY', range_high: 4381.25, range_low: 3579.48 },
      ],
      structure: createElement('span', null, 'structure'),
      onNavigateRange,
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge: bridge,
      coverageCandleFetcher: null,
    })));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    const pythonTab = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((button) => button.textContent === 'Python')!;
    await act(async () => pythonTab.click());
    const depth = container.querySelector<HTMLButtonElement>('[data-script-key="weekly_reclaim_depth"]')!;
    await act(async () => depth.click());

    expect(container.textContent).toContain('Trading depth: 0%');
    expect(container.textContent).toContain('Raw Fib depth: -122.97%');
    expect(container.textContent).toContain('Distance beyond broken boundary: 411.92');
    expect(container.textContent).toContain('Card focus: Range 2');

    const auditCard = container.querySelector<HTMLButtonElement>('.doctrineValidationRow')!;
    await act(async () => auditCard.click());
    expect(onNavigateRange).toHaveBeenLastCalledWith(expect.objectContaining({ range_id: 2 }));

    const viewRange1 = Array.from(container.querySelectorAll<HTMLButtonElement>('.doctrineRangeActions button'))
      .find((button) => button.textContent?.trim() === 'View Range 1')!;
    const viewRange2 = Array.from(container.querySelectorAll<HTMLButtonElement>('.doctrineRangeActions button'))
      .find((button) => button.textContent?.trim() === 'View Range 2')!;
    await act(async () => viewRange1.click());
    expect(onNavigateRange).toHaveBeenLastCalledWith(expect.objectContaining({ range_id: 1 }));
    await act(async () => viewRange2.click());
    expect(onNavigateRange).toHaveBeenLastCalledWith(expect.objectContaining({ range_id: 2 }));

    expect(container.querySelector('.weeklySampleActions:not(.doctrineRangeActions)')).toBeNull();
    expect(viewRange1.disabled).toBe(false);
    expect(viewRange2.disabled).toBe(false);
  });
});
