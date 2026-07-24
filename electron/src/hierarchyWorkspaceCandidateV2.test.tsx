// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace, type HierarchyRangeEnrichment } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function makeFixture() {
  const fixture = masterMapFixture() as any;
  for (const rootName of ['trusted_root', 'review_root', 'root']) {
    const weekly = fixture[rootName].children[0];
    weekly.source_refs = [{ raw_id: 1, case_ref: 'case:live', source_record_id: 'backend-weekly-1', payload_sha256: 'sha-1' }];
    weekly.script1_chronology = 'RH_TO_RL';
    weekly.script1_bos_direction = 'BOS_DOWN';
    weekly.script1_processing_status = 'COMPLETE';
    weekly.script1_review_status = 'PENDING';
    weekly.analysis_enrichments = { weekly_structure: {
      version_id: 'v1', version_label: '1', adapter_key: 'weekly_chronology_bos_v1', output_hash: 'v1-output',
      payload: { chronology: 'RL_TO_RH', bos_direction: 'BOS_UP', reasons: [] },
    } };
  }
  return fixture;
}

const approvedRun = { run: { run_id: 'run-v1', version_id: 'v1', case_ref: 'case:live', symbol: 'XAUUSD',
  approval_status: 'APPROVED', publication_status: 'PUBLISHED', eligible_count: 1, analysed_count: 1,
  sample_count: 0, approval_count: 0 }, samples: [] };
const approvedState = { status: 'APPROVED', current_approved_version_id: 'v1',
  versions: [{ version_id: 'v1', version_label: '1' }], runs: [approvedRun] };
const candidateState = { status: 'APPROVED', current_approved_version_id: 'v1', versions: [
  { version_id: 'v1', version_label: '1' }, { version_id: 'v2', version_label: '2' },
], runs: [{ run: { run_id: 'run-v2', version_id: 'v2', case_ref: 'case:live', symbol: 'XAUUSD',
  approval_status: 'PENDING', publication_status: 'UNPUBLISHED', eligible_count: 1, analysed_count: 1,
  sample_count: 1, approval_count: 0 }, samples: [{ canonical_range_id: 'mm:range:weekly-trusted',
  sample_order: 0, decision: 'PENDING', decided_at: null, processing_status: 'COMPLETE',
  payload: { chronology: 'RH_TO_RL', bos_direction: 'BOS_DOWN', bos_time: '2026-02-01T00:00:00Z', weeks_to_bos: 2 } }] }, approvedRun] };

function script(state: any, versionId: string, versionLabel: string) {
  return { script_id: 'script-weekly', script_key: 'weekly_structure', display_name: 'Weekly BOS',
    execution_order: 10, status: 'APPROVED', current_approved_version_id: 'v1', version_id: versionId,
    version_label: versionLabel, latest_version_status: versionId === 'v2' ? 'PENDING_APPROVAL' : 'APPROVED',
    doctrine_state: state };
}

describe('HierarchyWorkspace Weekly v2 candidate', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });

  it('runs inserted v2 while Structure retains approved v1', async () => {
    const fixture = makeFixture();
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({ ok: true, source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3', masterMap: fixture, doctrineState: approvedState,
        scripts: [script(approvedState, 'v1', '1')] }),
      runWeeklyScript1: vi.fn(), reviewWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: [script(approvedState, 'v1', '1')] }),
      insertDoctrineScript: vi.fn().mockResolvedValue({ ok: true, result: { version_id: 'v2', script_key: 'weekly_structure' } }),
      runDoctrinePipeline: vi.fn().mockResolvedValue({ ok: true, result: { processed: 1 },
        masterMap: fixture, doctrineState: candidateState, scripts: [script(candidateState, 'v2', '2')] }),
    };
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [{ range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2026-01-05', range_end_time: '2026-03-01' }],
      structure: (items: ReadonlyMap<string, HierarchyRangeEnrichment>) => {
        const item = items.get('1');
        return createElement('span', { 'data-testid': 'approved-structure' }, item ? `${item.chronology} · ${item.bos}` : 'none');
      },
      onNavigateRange: vi.fn(), caseRef: 'case:live', symbol: 'XAUUSD', weeklyAnalysisBridge: bridge,
      coverageCandleFetcher: null,
    })));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const tabs = () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs().find((node) => node.textContent === 'Python')!.click());
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('.doctrineScriptControls button'))
      .find((button) => button.textContent === 'Insert Script')!.click());
    expect((container!.querySelector('.doctrineInsertForm select') as HTMLSelectElement).value).toBe('weekly_chronology_bos_v2');
    await act(async () => {
      (container!.querySelector('.doctrineInsertForm button') as HTMLButtonElement).click();
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    });
    expect(bridge.runDoctrinePipeline).toHaveBeenCalledWith({ analysisDatabasePath: 'C:/analysis.sqlite3',
      caseRef: 'case:live', symbol: 'XAUUSD', versionId: 'v2' });
    expect(container!.textContent).toContain('Version 2 · PENDING');
    expect(container!.textContent).toContain('RH → RL');
    expect(container!.textContent).toContain('BOS Down');
    await act(async () => tabs().find((node) => node.textContent === 'Structure')!.click());
    expect(container!.querySelector('[data-testid="approved-structure"]')?.textContent).toBe('RL → RH · BOS Up');
  });
});
