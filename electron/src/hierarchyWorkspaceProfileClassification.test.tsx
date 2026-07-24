// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function enrichment(version: string, payload: Record<string, unknown>) {
  return {
    version_id: `version-${version}`,
    version_label: version,
    adapter_key: 'doctrine_package_v1',
    output_hash: `hash-${version}`,
    payload,
  };
}

function mapWithApprovedProfile(profile = 'S&D') {
  const value = masterMapFixture() as any;
  const weekly = value.trusted_root.children[0];
  weekly.source_refs = [{
    raw_id: 1,
    case_ref: 'case:live',
    source_record_id: 'backend-weekly-1',
    payload_sha256: 'sha-1',
  }];
  weekly.analysis_enrichments = {
    weekly_structure: enrichment('3', {
      chronology: 'RL_TO_RH',
      bos_direction: 'BOS_UP',
    }),
    weekly_reclaim: enrichment('2', {
      reclaim_status: 'RECLAIMED',
    }),
    weekly_profile_classification: enrichment('1', {
      profile_classification: profile,
      profile_badge: profile,
    }),
  };
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

function profileCandidateScript() {
  return {
    script_id: 'profile',
    script_key: 'weekly_profile_classification',
    display_name: 'Weekly Profile Classification',
    execution_order: 50,
    status: 'PENDING_APPROVAL',
    current_approved_version_id: null,
    version_id: 'profile-v1',
    version_label: '1',
    latest_version_status: 'PENDING_APPROVAL',
    package_dependency_ready: false,
    adapter_key: 'doctrine_package_v1',
    doctrine_state: {
      status: 'PENDING_APPROVAL',
      current_approved_version_id: null,
      versions: [{ version_id: 'profile-v1', version_label: '1' }],
      runs: [{
        run: {
          run_id: 'run-profile-v1',
          version_id: 'profile-v1',
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
            profile_classification: 'S&R>FP',
            profile_badge: 'S&R>FP',
            classification_basis: 'RECLAIM_DEPTH',
            reclaim_depth_percent: 45,
            reclaim_status: 'RECLAIMED',
            source_bos_direction: 'BOS_UP',
            next_bos_direction: 'BOS_UP',
            reason_codes: ['DEPTH_38_2_TO_50'],
          },
        }],
      }],
    },
  };
}

function scripts(profileCandidate = false) {
  const base = [
    approvedScript('bos', 'weekly_structure', 'Weekly BOS', 10, '3'),
    approvedScript('reclaim', 'weekly_reclaim', 'Weekly Reclaim', 20, '2'),
    approvedScript('depth', 'weekly_reclaim_depth', 'Weekly Reclaim Depth', 30, '6'),
    approvedScript('movement', 'weekly_movement_classification', 'Weekly Movement Classification', 40, '4'),
  ];
  return [...base, profileCandidate
    ? profileCandidateScript()
    : approvedScript('profile', 'weekly_profile_classification', 'Weekly Profile Classification', 50, '1')];
}

describe('HierarchyWorkspace Weekly profile classification', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  it('adds the compact approved profile badge to the hierarchy range label', async () => {
    const map = mapWithApprovedProfile('S&D');
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
      runDoctrinePipeline: vi.fn(),
      reviewDoctrineSample: vi.fn(),
    };

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [{ range_id: 1, structure_layer: 'WEEKLY' }],
      structure: (values: ReadonlyMap<string, any>) => createElement(
        'span',
        { 'data-testid': 'profile-label' },
        values.get('1')?.bos || 'pending',
      ),
      onNavigateRange: vi.fn(),
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge: bridge,
      coverageCandleFetcher: null,
    })));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(container.querySelector('[data-testid="profile-label"]')?.textContent)
      .toBe('BOS Up · RECL · ◆ S&D');
  });

  it('shows only the basic trader-facing facts in the profile candidate', async () => {
    const map = mapWithApprovedProfile('S&R');
    const candidateScripts = scripts(true);
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: map,
        scripts: candidateScripts,
      }),
      runWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn().mockResolvedValue({ ok: true, result: candidateScripts }),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn(),
      reviewDoctrineSample: vi.fn(),
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

    const python = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((button) => button.textContent === 'Python')!;
    await act(async () => python.click());
    const profile = container.querySelector<HTMLButtonElement>('[data-script-key="weekly_profile_classification"]')!;
    await act(async () => profile.click());

    expect(container.textContent).toContain('Profile: S&R>FP');
    expect(container.textContent).toContain('Depth: 45%');
    expect(container.textContent).toContain('Reclaim: RECLAIMED');
    expect(container.textContent).toContain('Previous BOS: BOS Up');
    expect(container.textContent).toContain('Next BOS: BOS Up');
    expect(container.textContent).toContain('Classification basis: RECLAIM DEPTH');
    expect(container.textContent).not.toContain('raw Fib');
  });
});
