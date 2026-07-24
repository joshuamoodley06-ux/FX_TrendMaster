// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function fixtureWithLegacyRun() {
  const value = masterMapFixture() as any;
  value.analysis = {
    weekly_script1: {
      pipeline_name: 'Old Weekly BOS',
      processing_version: '2',
      run_id: 'old-run-v2',
      approval_state: 'APPROVED',
      eligible: 28,
      analysed: 28,
      pending: 0,
      needs_review: 0,
      script_content_hash: 'old-hash',
      sample_count: 5,
      approval_count: 5,
      publication_status: 'PUBLISHED',
      validation_samples: [{
        canonical_range_id: 'mm:range:weekly-trusted',
        sample_order: 0,
        decision: 'APPROVED',
        decided_at: '2026-07-21T00:00:00Z',
      }],
    },
  };
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

describe('HierarchyWorkspace exact version binding', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });

  it('does not show an old approved run under a new package candidate', async () => {
    const map = fixtureWithLegacyRun();
    const state = {
      status: 'APPROVED',
      current_approved_version_id: 'bos-v2',
      versions: [
        { version_id: 'bos-v2', version_label: '2' },
        { version_id: 'bos-v3', version_label: '3' },
      ],
      runs: [{
        run: {
          run_id: 'old-run-v2', version_id: 'bos-v2', case_ref: 'case:live', symbol: 'XAUUSD',
          approval_status: 'APPROVED', publication_status: 'PUBLISHED', eligible_count: 28,
          analysed_count: 28, sample_count: 5, approval_count: 5,
        },
        samples: [],
      }],
    };
    const scripts = [{
      script_id: 'bos', script_key: 'weekly_structure', display_name: 'Weekly BOS', execution_order: 10,
      status: 'APPROVED', current_approved_version_id: null, version_id: 'bos-v3', version_label: '3',
      adapter_key: 'doctrine_package_v1', latest_version_status: 'PENDING_APPROVAL',
      package_dependency_ready: false, doctrine_state: state,
    }];
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true, source: 'DISPOSABLE_ANALYSIS_COPY', analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: map, scripts,
      }),
      runWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: scripts }),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn(),
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

    expect(container.textContent).toContain('Version 3 · PENDING_APPROVAL');
    expect(container.textContent).toContain('Candidate has not run for this case.');
    expect(container.textContent).toContain('Previous approved version remains active until this candidate reaches 5/5.');
    expect(container.textContent).not.toContain('Version 2 · APPROVED');
    expect(container.textContent).not.toContain('28 eligible · 28 analysed');
    expect(Array.from(container.querySelectorAll<HTMLButtonElement>('.doctrineSelectedSummary button'))
      .some((button) => button.textContent === 'Run Candidate')).toBe(true);
  });
});
