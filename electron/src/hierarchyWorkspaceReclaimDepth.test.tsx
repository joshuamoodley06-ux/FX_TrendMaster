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

function approvedScript(id: string, key: string, name: string, order: number) {
  const state = {
    status: 'APPROVED',
    current_approved_version_id: `${id}-v1`,
    versions: [{ version_id: `${id}-v1`, version_label: '1' }],
    runs: [],
  };
  return {
    script_id: id,
    script_key: key,
    display_name: name,
    execution_order: order,
    status: 'APPROVED',
    current_approved_version_id: `${id}-v1`,
    version_id: `${id}-v1`,
    version_label: '1',
    latest_version_status: 'APPROVED',
    doctrine_state: state,
  };
}

describe('HierarchyWorkspace reclaim depth review', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });

  it('shows continuous reclaim depth facts instead of BOS labels', async () => {
    const map = fixture();
    const depthState = {
      status: 'PENDING_APPROVAL',
      current_approved_version_id: null,
      versions: [{ version_id: 'depth-v1', version_label: '1' }],
      runs: [{
        run: {
          run_id: 'run-depth-v1',
          version_id: 'depth-v1',
          case_ref: 'case:live',
          symbol: 'XAUUSD',
          approval_status: 'PENDING',
          publication_status: 'UNPUBLISHED',
          eligible_count: 1,
          analysed_count: 1,
          sample_count: 1,
          approval_count: 0,
        },
        samples: [{
          canonical_range_id: 'mm:range:weekly-trusted',
          sample_order: 0,
          decision: 'PENDING',
          decided_at: null,
          processing_status: 'COMPLETE',
          payload: {
            depth_status: 'MEASURED',
            reclaim_depth_percent: 50,
            deepest_wick_price: 95,
            weeks_observed: 3,
            reason_codes: [],
          },
        }],
      }],
    };
    const scripts = [
      approvedScript('bos', 'weekly_structure', 'Weekly BOS', 10),
      approvedScript('reclaim', 'weekly_reclaim', 'Weekly Reclaim', 20),
      {
        script_id: 'depth', script_key: 'weekly_reclaim_depth', display_name: 'Weekly Reclaim Depth',
        execution_order: 30, status: 'PENDING_APPROVAL', current_approved_version_id: null,
        version_id: 'depth-v1', version_label: '1', latest_version_status: 'PENDING_APPROVAL',
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

    expect(container.textContent).toContain('MEASURED');
    expect(container.textContent).toContain('50% depth');
    expect(container.textContent).toContain('Deepest wick 95');
    expect(container.textContent).toContain('3 weeks observed');
    expect(container.textContent).not.toContain('BOS Pending');

    const runCandidate = Array.from(container.querySelectorAll<HTMLButtonElement>('.doctrineSelectedSummary button'))
      .find((button) => button.textContent === 'Rerun Candidate')!;
    expect(runCandidate.disabled).toBe(false);
  });
});
