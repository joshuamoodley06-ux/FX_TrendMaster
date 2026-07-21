// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace, type HierarchyRangeEnrichment } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function fixtureWithReclaim(reclaimStatus: string, bosDirection: string, chronology: string) {
  const fixture = masterMapFixture() as any;
  for (const rootName of ['trusted_root', 'review_root', 'root']) {
    const weekly = fixture[rootName].children[0];
    weekly.source_refs = [{
      raw_id: 1,
      case_ref: 'case:live',
      source_record_id: 'backend-weekly-1',
      payload_sha256: 'sha-1',
    }];
    weekly.analysis_enrichments = {
      weekly_structure: {
        version_id: 'bos-v1',
        version_label: '1',
        adapter_key: 'doctrine_package_v1',
        output_hash: 'bos-output',
        payload: {
          chronology,
          bos_direction: bosDirection,
        },
      },
      weekly_reclaim: {
        version_id: 'reclaim-v1',
        version_label: '1',
        adapter_key: 'doctrine_package_v1',
        output_hash: 'reclaim-output',
        payload: {
          reclaim_status: reclaimStatus,
        },
      },
    };
  }
  return fixture;
}

describe('HierarchyWorkspace Weekly reclaim labels', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  it.each([
    ['RECLAIMED', 'BOS_UP', 'RL_TO_RH', 'RL → RH · BOS Up · RECL'],
    ['ABANDONED', 'BOS_DOWN', 'RH_TO_RL', 'RH → RL · BOS Down · ABND'],
    ['PENDING', 'BOS_UP', 'RL_TO_RH', 'RL → RH · BOS Up'],
  ])('shows %s beside the approved BOS result', async (
    reclaimStatus,
    bosDirection,
    chronology,
    expected,
  ) => {
    const masterMap = fixtureWithReclaim(reclaimStatus, bosDirection, chronology);
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap,
        scripts: [],
      }),
      runWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: [] }),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn(),
    };

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [{ range_id: 1, structure_layer: 'WEEKLY' }],
      structure: (items: ReadonlyMap<string, HierarchyRangeEnrichment>) => {
        const item = items.get('1');
        return createElement(
          'span',
          { 'data-testid': 'weekly-enrichment' },
          item ? `${item.chronology} · ${item.bos}` : 'none',
        );
      },
      onNavigateRange: vi.fn(),
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge: bridge,
      coverageCandleFetcher: null,
    })));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector('[data-testid="weekly-enrichment"]')?.textContent).toBe(expected);
  });
});
