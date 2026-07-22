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

function state(versionId: string, versionLabel: string, status: string, samples: any[] = []) {
  return {
    status,
    current_approved_version_id: status === 'APPROVED' ? versionId : null,
    versions: [{ version_id: versionId, version_label: versionLabel }],
    runs: samples.length ? [{
      run: {
        run_id: `run-${versionId}`,
        version_id: versionId,
        case_ref: 'case:live',
        symbol: 'XAUUSD',
        approval_status: 'PENDING',
        publication_status: 'UNPUBLISHED',
        eligible_count: 1,
        analysed_count: 1,
        sample_count: samples.length,
        approval_count: 0,
      },
      samples,
    }] : [],
  };
}

const bosState = state('bos-v3', '3', 'APPROVED');
const reclaimState = state('reclaim-v2', '2', 'PENDING_APPROVAL', [{
  canonical_range_id: 'mm:range:weekly-trusted',
  sample_order: 0,
  decision: 'PENDING',
  decided_at: null,
  processing_status: 'COMPLETE',
  payload: {
    reclaim_status: 'RECLAIMED',
    reclaim_abbreviation: 'RECL',
    source_bos_direction: 'BOS_UP',
    source_bos_time: '2026-01-12T00:00:00Z',
    bos_candle_close: 4905,
    reclaim_boundary: 4891,
    same_candle_reclaim: false,
    reclaim_time: '2026-01-26T00:00:00Z',
    reclaim_wick_price: 4891,
    weeks_to_reclaim: 2,
    candles_scanned: 2,
    reason_codes: [],
  },
}]);
const depthState = state('depth-v3', '3', 'PENDING_APPROVAL');

function scripts() {
  return [
    { script_id: 'bos', script_key: 'weekly_structure', display_name: 'Weekly BOS', execution_order: 10,
      status: 'APPROVED', current_approved_version_id: 'bos-v3', version_id: 'bos-v3', version_label: '3',
      latest_version_status: 'APPROVED', package_dependency_ready: true, doctrine_state: bosState },
    { script_id: 'reclaim', script_key: 'weekly_reclaim', display_name: 'Weekly Reclaim', execution_order: 20,
      status: 'PENDING_APPROVAL', current_approved_version_id: null, version_id: 'reclaim-v2', version_label: '2',
      latest_version_status: 'PENDING_APPROVAL', package_dependency_ready: false, doctrine_state: reclaimState },
    { script_id: 'depth', script_key: 'weekly_reclaim_depth', display_name: 'Weekly Reclaim Depth', execution_order: 30,
      status: 'PENDING_APPROVAL', current_approved_version_id: null, version_id: 'depth-v3', version_label: '3',
      latest_version_status: 'PENDING_APPROVAL', package_dependency_ready: false, doctrine_state: depthState },
  ];
}

describe('HierarchyWorkspace doctrine chain', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });

  it('selects each version, renders its full payload and enforces latest-parent approval order', async () => {
    const map = fixture();
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: map,
        scripts: scripts(),
      }),
      runWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: scripts() }),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn().mockResolvedValue({ ok: true, masterMap: map, scripts: scripts(), result: {} }),
      reviewDoctrineSample: vi.fn().mockResolvedValue({ ok: true, result: { approval_status: 'PENDING' } }),
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

    expect(container.querySelectorAll('.doctrineStoredScripts > button')).toHaveLength(3);
    expect(container.textContent).toContain('3-script chain installed');

    const reclaim = container.querySelector<HTMLButtonElement>('[data-script-key="weekly_reclaim"]')!;
    await act(async () => reclaim.click());
    expect(container.textContent).toContain('Version 2 · PENDING');
    expect(container.textContent).toContain('Result: RECL · RECLAIMED');
    expect(container.textContent).toContain('Broken boundary: 4891');
    expect(container.textContent).toContain('Weeks to reclaim: 2');
    expect(container.textContent).toContain('Candles scanned: 2');

    const approve = Array.from(container.querySelectorAll<HTMLButtonElement>('.weeklySampleActions button'))
      .find((button) => button.textContent === 'Approve')!;
    await act(async () => { approve.click(); await Promise.resolve(); await Promise.resolve(); });
    expect(bridge.reviewDoctrineSample).toHaveBeenCalledWith({
      analysisDatabasePath: 'C:/analysis.sqlite3',
      runId: 'run-reclaim-v2',
      canonicalRangeId: 'mm:range:weekly-trusted',
      decision: 'APPROVED',
    });
    expect(bridge.runDoctrinePipeline).toHaveBeenCalledWith({
      analysisDatabasePath: 'C:/analysis.sqlite3',
      caseRef: 'case:live',
      symbol: 'XAUUSD',
    });
    expect(container.textContent).not.toContain('The review could not be saved safely.');

    const depth = container.querySelector<HTMLButtonElement>('[data-script-key="weekly_reclaim_depth"]')!;
    await act(async () => depth.click());
    const runCandidate = Array.from(container.querySelectorAll<HTMLButtonElement>('.doctrineSelectedSummary button'))
      .find((button) => button.textContent === 'Run Candidate')!;
    expect(runCandidate.disabled).toBe(true);
    expect(container.textContent).toContain('Approve the latest previous script first.');
  });
});
