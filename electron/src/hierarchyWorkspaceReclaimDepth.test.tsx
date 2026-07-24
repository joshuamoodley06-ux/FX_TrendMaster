// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function fixture() {
  const value = masterMapFixture() as any;
  for (const rootName of ['trusted_root', 'review_root', 'root']) {
    value[rootName].children[0].source_refs = [{
      raw_id: 1,
      case_ref: 'case:live',
      source_record_id: 'backend-weekly-1',
      payload_sha256: 'sha-1',
    }];
  }
  return value;
}

function approvedScript(id: string, key: string, name: string, order: number, version = '1') {
  const versionId = `${id}-v${version}`;
  const state = {
    status: 'APPROVED',
    current_approved_version_id: versionId,
    versions: [{ version_id: versionId, version_label: version }],
    runs: [],
  };
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
    doctrine_state: state,
  };
}

describe('HierarchyWorkspace approved reclaim depth audit', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });

  it('keeps trader depth, depth-anchor date and range-completion facts visible after approval', async () => {
    const map = fixture();
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
            depth_classification: 'NO_RETRACEMENT',
            source_range1_id: 'mm:range:weekly-trusted',
            source_bos_direction: 'BOS_UP',
            source_bos_time: '2026-01-12T00:00:00Z',
            source_reclaim_status: 'RECLAIMED',
            source_reclaim_abbreviation: 'RECL',
            source_reclaim_time: '2026-01-12T00:00:00Z',
            source_weeks_to_reclaim: 0,
            range1_high: 100,
            range1_low: 90,
            range1_size: 10,
            fib_zero_price: 100,
            fib_one_price: 90,
            range2_id: 'mm:range:weekly-2',
            range2_defined_at: '2026-01-26T00:00:00Z',
            range2_completed_at: '2026-01-26T00:00:00Z',
            range2_chronology: 'RL_TO_RH',
            range2_anchor_sequence: 'OPPOSITE_THEN_CONTINUATION',
            range2_opposite_anchor_type: 'RL',
            range2_opposite_anchor_price: 101.25,
            range2_opposite_anchor_time: '2026-01-12T00:00:00Z',
            range2_continuation_anchor_type: 'RH',
            range2_continuation_anchor_price: 110,
            range2_continuation_anchor_time: '2026-01-26T00:00:00Z',
            range2_completion_anchor_type: 'RH',
            range2_completion_anchor_price: 110,
            range2_completion_anchor_time: '2026-01-26T00:00:00Z',
            depth_window_start_time: '2026-01-12T00:00:00Z',
            depth_window_end_time: '2026-01-12T00:00:00Z',
            reclaim_depth_price: 0,
            reclaim_depth_ratio: 0,
            reclaim_depth_percent: 0,
            raw_reclaim_depth_price: -1.25,
            raw_reclaim_depth_ratio: -0.125,
            raw_reclaim_depth_percent: -12.5,
            boundary_distance_price: 1.25,
            boundary_position: 'ABOVE_BROKEN_RH',
            weeks_bos_to_depth_anchor: 0,
            weeks_reclaim_to_depth_anchor: 0,
            weeks_bos_to_range2_completion: 2,
            weeks_reclaim_to_range2_completion: 2,
            weeks_bos_to_range2_definition: 2,
            weeks_reclaim_to_range2_definition: 2,
            range2_formation_weeks: 2,
            old_opposite_external_touched: false,
            old_opposite_external_exceeded: false,
            reason_codes: ['RANGE2_OPPOSITE_1.2500_ABOVE_BROKEN_RH'],
          },
        }],
      }],
    };
    const scripts = [
      approvedScript('bos', 'weekly_structure', 'Weekly BOS', 10, '3'),
      approvedScript('reclaim', 'weekly_reclaim', 'Weekly Reclaim', 20, '2'),
      {
        script_id: 'depth', script_key: 'weekly_reclaim_depth', display_name: 'Weekly Reclaim Depth',
        execution_order: 30, status: 'APPROVED', current_approved_version_id: 'depth-v6',
        version_id: 'depth-v6', version_label: '6', latest_version_status: 'APPROVED',
        doctrine_state: depthState,
      },
    ];
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
      runDoctrinePipeline: vi.fn().mockResolvedValue({ ok: true, masterMap: map, scripts, result: {} }),
      reviewDoctrineSample: vi.fn().mockResolvedValue({ ok: true, result: {} }),
    };

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [{ range_id: 1, structure_layer: 'WEEKLY' }],
      structure: createElement('span', null, 'structure'),
      onNavigateRange: vi.fn(),
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

    expect(container.textContent).toContain('Version 6 · APPROVED');
    expect(container.textContent).toContain('Result: NO RETRACEMENT');
    expect(container.textContent).toContain('Reclaim result: RECL · RECLAIMED');
    expect(container.textContent).toContain('Range 1 ID: mm:range:weekly-trusted');
    expect(container.textContent).toContain('W1 RH: 100');
    expect(container.textContent).toContain('W1 RL: 90');
    expect(container.textContent).toContain('Range 2 ID: mm:range:weekly-2');
    expect(container.textContent).toContain('Range 2 defined: 2026-01-26');
    expect(container.textContent).toContain('W2 opposite anchor: RL 101.25');
    expect(container.textContent).toContain('W2 opposite candle: 2026-01-12');
    expect(container.textContent).toContain('W2 continuation anchor: RH 110');
    expect(container.textContent).toContain('W2 continuation candle: 2026-01-26');
    expect(container.textContent).toContain('Fib ratio: 0');
    expect(container.textContent).toContain('Depth: 0%');
    expect(container.textContent).toContain('Reasons: RANGE2 OPPOSITE 1.2500 ABOVE BROKEN RH');
    expect(container.textContent).toContain('Weeks BOS→R2 defined: 2');
    expect(container.textContent).toContain('Range 2 formation weeks: 2');
    expect(container.textContent).toContain('APPROVED');
    expect(container.querySelector('.weeklySampleActions')).toBeNull();
  });
});
