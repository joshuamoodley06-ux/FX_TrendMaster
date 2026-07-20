// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  HierarchyWorkspace,
  selectWeeklyValidationSample,
  type HierarchyRangeEnrichment,
} from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('HierarchyWorkspace modes', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });
  async function renderWorkspace(weeklyAnalysisBridge?: any) {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    const onNavigateRange = vi.fn();
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [
        { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
        { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
      ],
      structure: (enrichmentsByRangeId: ReadonlyMap<string, HierarchyRangeEnrichment>) => {
        const enrichment = enrichmentsByRangeId.get('1');
        return createElement('div', { 'data-testid': 'structure' },
          'Mapped structure',
          enrichment && createElement('span', { className: 'weeklyScript1InlineEnrichment' },
            `${enrichment.chronology} · ${enrichment.bos}`));
      },
      onNavigateRange,
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge,
    })));
    return onNavigateRange;
  }
  it('defaults to Structure and switches compact modes', async () => {
    await renderWorkspace();
    expect(container?.querySelector('[data-testid="structure"]')).not.toBeNull();
    const tabs = () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs().find((node) => node.textContent === 'Coverage')!.click());
    expect(container?.querySelector('.hierarchyCoverageScroll')).not.toBeNull();
    await act(async () => tabs().find((node) => node.textContent === 'Python')!.click());
    expect(container?.textContent).toContain('Analysis dormant');
  });

  it('uses the canonical selected-case resolver in the structural explorer closure', () => {
    const mainSource = fs.readFileSync(path.resolve(__dirname, 'main.tsx'), 'utf8');
    expect(mainSource).toContain("caseRef={String(getCurrentMappingCaseRef().case_ref || '')}");
    expect(mainSource).not.toContain("caseRef={String(mappingCase.case_ref || '')}");
  });

  it('renders safely when no mapping case is selected', async () => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [], structure: createElement('div', { 'data-testid': 'empty-structure' }, 'No case selected'),
      onNavigateRange: vi.fn(), caseRef: '', symbol: 'XAUUSD', weeklyAnalysisBridge: null,
    })));
    expect(container.querySelector('[data-testid="empty-structure"]')).not.toBeNull();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Python')!.click());
    expect(container.textContent).toContain('Analysis dormant');
  });

  it('activates Script 1 through the disposable-copy workflow and renders refreshed facts', async () => {
    const fixture = masterMapFixture();
    (fixture as any).analysis = { weekly_script1: {
      pipeline_name: 'Weekly analysis', processing_version: 'weekly_script1_v1', run_id: 'run-1',
      executed_at: '2026-07-19T10:00:00Z', input_structural_content_hash: fixture.structural_content_hash,
      approval_state: 'PENDING', approved_at: null, eligible: 1, analysed: 1, pending: 1, needs_review: 0,
      script_content_hash: 'script-hash', sample_count: 1, approval_count: 0,
      publication_status: 'UNPUBLISHED', validation_samples: [
        { canonical_range_id: 'mm:range:weekly-trusted', sample_order: 0, decision: 'PENDING', decided_at: null },
      ],
    } };
    for (const rootName of ['trusted_root', 'review_root', 'root']) {
      const weekly = ((fixture[rootName] as any).children as any[])[0];
      weekly.source_refs = [{ raw_id: 1, case_ref: 'case:live', source_record_id: '1', payload_sha256: 'sha-1' }];
      weekly.script1_chronology = 'RH_TO_RL'; weekly.script1_bos_direction = 'BOS_DOWN';
      weekly.script1_bos_time = '2026-03-01T00:00:00Z'; weekly.script1_processing_status = 'COMPLETE';
      weekly.script1_review_status = 'PENDING';
      weekly.script1_reason_codes = [];
      weekly.analysis_enrichments = { weekly_structure: {
        version_id: 'approved-version', version_label: '1', adapter_key: 'weekly_chronology_bos_v1',
        output_hash: 'approved-output', payload: {
          chronology: 'RH_TO_RL', bos_direction: 'BOS_DOWN',
          bos_time: '2026-03-01T00:00:00Z', reasons: [],
        },
      } };
    }
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live/range-library.sqlite3' }),
      runWeeklyScript1: vi.fn().mockResolvedValue({ ok: true, source: 'DISPOSABLE_ANALYSIS_COPY',
        liveDatabasePath: 'C:/live/range-library.sqlite3', analysisDatabasePath: 'C:/analysis/copy.sqlite3', masterMap: fixture }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({ ok: false, source: 'LIVE' }),
      reviewWeeklyScript1: vi.fn().mockImplementation(async ({ decision }: any) => {
        for (const rootName of ['trusted_root', 'review_root', 'root']) {
          ((fixture[rootName] as any).children as any[])[0].script1_review_status = decision;
        }
        (fixture as any).analysis.weekly_script1.approval_state = decision;
        (fixture as any).analysis.weekly_script1.approval_count = 1;
        (fixture as any).analysis.weekly_script1.publication_status = 'PUBLISHED';
        (fixture as any).analysis.weekly_script1.validation_samples[0].decision = decision;
        return { ok: true, source: 'DISPOSABLE_ANALYSIS_COPY', analysisDatabasePath: 'C:/analysis/copy.sqlite3', masterMap: fixture };
      }),
    };
    const navigate = await renderWorkspace(bridge);
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Python')!.click());
    expect(container!.textContent).toContain('Analysis dormant');
    await act(async () => { (container!.querySelector('.weeklyScript1Header button') as HTMLButtonElement).click(); await Promise.resolve(); await Promise.resolve(); });
    expect(bridge.runWeeklyScript1).toHaveBeenCalledWith({
      databasePath: 'C:/live/range-library.sqlite3', caseRef: 'case:live', symbol: 'XAUUSD',
    });
    expect(container!.textContent).toContain('XAUUSD ANALYSIS WORKSPACE V2');
    expect(container!.textContent).toContain('RH → RL');
    expect(container!.textContent).toContain('BOS Down');
    await act(async () => (container!.querySelector('.weeklyScript1Row') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ range_id: 1 }));
    expect(container!.textContent).toContain('PENDING');
    await act(async () => {
      Array.from(container!.querySelectorAll<HTMLButtonElement>('.weeklySampleActions button')).find((button) => button.textContent === 'Approve')!.click();
      await Promise.resolve(); await Promise.resolve();
    });
    expect(bridge.reviewWeeklyScript1).toHaveBeenCalledWith(expect.objectContaining({
      analysisDatabasePath: 'C:/analysis/copy.sqlite3', liveDatabasePath: 'C:/live/range-library.sqlite3',
      runId: 'run-1', caseRef: 'case:live', symbol: 'XAUUSD',
      canonicalRangeId: 'mm:range:weekly-trusted', decision: 'APPROVED',
    }));
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Structure')!.click());
    expect(container!.querySelector('.weeklyScript1InlineEnrichment')).not.toBeNull();
  });

  it('keeps the validation sample bounded and prefers varied outputs', () => {
    const nodes = Array.from({ length: 8 }, (_, index) => ({
      canonicalRangeId: `range-${index}`,
      script1Chronology: index % 2 ? 'RH_TO_RL' : 'RL_TO_RH',
      script1BosDirection: index % 3 ? 'BOS_UP' : 'BOS_DOWN',
      script1ProcessingStatus: index === 4 ? 'NEEDS_REVIEW' : 'COMPLETE',
    })) as any;
    const sample = selectWeeklyValidationSample(nodes);
    expect(sample).toHaveLength(5);
    expect(new Set(sample.map((node: any) => node.script1BosDirection)).size).toBe(2);
    expect(sample.some((node: any) => node.script1ProcessingStatus === 'NEEDS_REVIEW')).toBe(true);
  });

  it('restores a published version without rerunning or recreating samples', async () => {
    const fixture = masterMapFixture() as any;
    fixture.analysis = { weekly_script1: { pipeline_name: 'Weekly analysis', processing_version: 'weekly_script1_v1',
      run_id: 'approved-run', approval_state: 'APPROVED', script_content_hash: 'hash', sample_count: 1,
      approval_count: 1, publication_status: 'PUBLISHED', validation_samples: [], eligible: 1, analysed: 1 } };
    for (const rootName of ['trusted_root', 'review_root', 'root']) {
      const weekly = fixture[rootName].children[0];
      weekly.source_refs = [{ raw_id: 1, case_ref: 'case:live', source_record_id: '1', payload_sha256: 'sha-1' }];
      weekly.script1_chronology = 'RL_TO_RH'; weekly.script1_bos_direction = 'BOS_UP';
      weekly.script1_processing_status = 'COMPLETE'; weekly.script1_review_status = 'APPROVED';
      weekly.analysis_enrichments = { weekly_structure: {
        version_id: 'approved-version', version_label: '1', adapter_key: 'weekly_chronology_bos_v1',
        output_hash: 'approved-output', payload: {
          chronology: 'RL_TO_RH', bos_direction: 'BOS_UP',
          bos_time: '2026-03-01T00:00:00Z', reasons: [],
        },
      } };
    }
    const bridge = { getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({ ok: true, source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3', masterMap: fixture }),
      runWeeklyScript1: vi.fn(), reviewWeeklyScript1: vi.fn() };
    await renderWorkspace(bridge);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(bridge.runWeeklyScript1).not.toHaveBeenCalled();
    expect(container!.querySelector('.weeklyScript1InlineEnrichment')).not.toBeNull();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Python')!.click());
    expect(container!.textContent).toContain('Analysis Approved');
    expect(container!.querySelectorAll('.weeklyScript1Sample')).toHaveLength(0);
  });

  it('leaves the existing hierarchy usable when activation fails', async () => {
    const bridge = { getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      runWeeklyScript1: vi.fn().mockResolvedValue({ ok: false, error: 'usage: cli.py --source-db\nsource database is missing required table: candles' }) };
    await renderWorkspace(bridge);
    const tabs = () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs().find((node) => node.textContent === 'Python')!.click());
    await act(async () => { (container!.querySelector('.weeklyScript1Header button') as HTMLButtonElement).click(); await Promise.resolve(); await Promise.resolve(); });
    expect(container!.querySelector('[role="alert"]')?.textContent).toContain('Existing hierarchy remains available');
    expect(container!.querySelector('[role="alert"]')?.textContent).not.toContain('usage:');
    expect(container!.textContent).toContain('Weekly Script 1');
    await act(async () => tabs().find((node) => node.textContent === 'Structure')!.click());
    expect(container!.querySelector('[data-testid="structure"]')).not.toBeNull();
  });
  it('routes parent and missing-span clicks through chart navigation', async () => {
    const navigate = await renderWorkspace();
    const coverage = Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!;
    await act(async () => coverage.click());
    expect(container?.textContent).toContain('50%');
    await act(async () => (container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ range_id: 1 }));
    await act(async () => (container!.querySelector('.hierarchyCoverageExpand') as HTMLButtonElement).click());
    expect(container?.textContent).toContain('06 Jan 2025');
    await act(async () => (container!.querySelector('.hierarchyCoverageGaps button') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({ range_start_time: '2025-01-06T00:00:00.000Z', range_end_time: '2025-01-11T00:00:00.000Z' }));
  });
  it('renders a readable one-line row at the supported compact width', async () => {
    await renderWorkspace();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const row = container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement;
    expect(row.textContent).toContain('WEEKLY|01 Jan 2025 → 11 Jan 2025|50%');
    expect(row.querySelector('.hierarchyCoveragePrimary')).not.toBeNull();
    expect(container!.querySelector('.hierarchyCoverageScroll')).not.toBeNull();
  });
  it('preserves the scrolling container and chart jump after year filtering', async () => {
    const navigate = await renderWorkspace();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const scroll = container!.querySelector('.hierarchyCoverageScroll') as HTMLDivElement;
    scroll.scrollTop = 19;
    const from = container!.querySelector('[aria-label="From year"]') as HTMLSelectElement;
    await act(async () => {
      from.value = '2025';
      from.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(container!.querySelector('.hierarchyCoverageScroll')).toBe(scroll);
    expect(scroll.scrollTop).toBe(19);
    await act(async () => (container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ range_id: 1 }));
  });

  it('keeps chart mapping controls usable in Coverage mode', async () => {
    await renderWorkspace();
    const rh = document.createElement('button');
    const rl = document.createElement('button');
    const onRh = vi.fn(); const onRl = vi.fn();
    rh.addEventListener('click', onRh); rl.addEventListener('click', onRl);
    document.body.append(rh, rl);
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    rh.click(); rl.click();
    expect(onRh).toHaveBeenCalledTimes(1);
    expect(onRl).toHaveBeenCalledTimes(1);
  });

  it('recomputes Coverage after refreshed saved ranges without resetting filters', async () => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    const base = [
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2024-01-01', range_end_time: '2024-01-11' },
      { range_id: 2, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
      { range_id: 3, parent_range_id: 2, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
    ];
    const render = async (ranges: Record<string, unknown>[]) => act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges, structure: createElement('div'), onNavigateRange: vi.fn(), caseRef: 'case:live', symbol: 'XAUUSD',
    })));
    await render(base);
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const from = container!.querySelector('[aria-label="From year"]') as HTMLSelectElement;
    await act(async () => { from.value = '2025'; from.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(container!.textContent).toContain('50%');
    await render([...base, { range_id: 4, parent_range_id: 2, structure_layer: 'DAILY', range_start_time: '2025-01-06', range_end_time: '2025-01-11' }]);
    expect((container!.querySelector('[aria-label="From year"]') as HTMLSelectElement).value).toBe('2025');
    expect(container!.textContent).toContain('100%');
  });
});
