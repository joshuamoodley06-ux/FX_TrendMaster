// @vitest-environment happy-dom

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HierarchyWorkspace, type WeeklyAnalysisBridge } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function weeklyNode(index: number) {
  const canonicalId = `canonical-weekly-${index}`;
  const sourceId = String(index);
  return {
    id: canonicalId,
    node_type: 'RANGE',
    structure_layer: 'WEEKLY',
    source_timeframe: 'W1',
    range_high: 2500 + index,
    range_low: 2300 + index,
    range_high_time: `2026-01-${String(index + 5).padStart(2, '0')}T00:00:00Z`,
    range_low_time: `2026-01-${String(index).padStart(2, '0')}T00:00:00Z`,
    active_from_time: `2026-01-${String(index + 5).padStart(2, '0')}T00:00:00Z`,
    inactive_from_time: null,
    status: 'ACTIVE',
    direction_of_break: null,
    source_count: 1,
    source_refs: [{
      raw_id: index,
      case_ref: 'case:live',
      source_record_id: sourceId,
      payload_sha256: `sha-${index}`,
    }],
    navigation_status: 'TRUSTED',
    statistics_status: 'ELIGIBLE',
    ancestor_review_status: 'CLEAR',
    direct_parent_link_status: 'ROOT',
    review_context_only: false,
    events: [],
    children: [],
    analysis_enrichments: {
      weekly_structure: {
        version_id: 'version-1',
        version_label: '1',
        adapter_key: 'weekly_chronology_bos_v1',
        output_hash: `output-${index}`,
        payload: {
          chronology: index % 2 ? 'RL_TO_RH' : 'RH_TO_RL',
          bos_direction: index % 2 ? 'BOS_UP' : 'BOS_DOWN',
        },
      },
    },
  };
}

function approvedFixture() {
  const fixture = masterMapFixture();
  const nodes = [1, 2, 3, 4, 5].map(weeklyNode);
  const trusted = fixture.trusted_root as Record<string, unknown>;
  trusted.children = nodes;
  const all = fixture.root as Record<string, unknown>;
  all.children = nodes;
  return fixture;
}

function approvedDoctrineState() {
  const samples = [1, 2, 3, 4, 5].map((index, sampleOrder) => ({
    canonical_range_id: `canonical-weekly-${index}`,
    sample_order: sampleOrder,
    decision: 'APPROVED',
    decided_at: `2026-07-19T12:0${sampleOrder}:00Z`,
  }));
  return {
    script_id: 'script-1',
    script_key: 'weekly_structure',
    status: 'APPROVED',
    current_approved_version_id: 'version-1',
    versions: [{ version_id: 'version-1', version_label: '1', approved_at: '2026-07-19T12:05:00Z' }],
    runs: [{
      run: {
        run_id: 'run-1',
        version_id: 'version-1',
        case_ref: 'case:live',
        symbol: 'XAUUSD',
        approval_status: 'APPROVED',
        publication_status: 'PUBLISHED',
        eligible_count: 5,
        analysed_count: 5,
        sample_count: 5,
        approval_count: 5,
      },
      samples,
    }],
  };
}

describe('Hierarchy doctrine workspace v2', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    document.body.replaceChildren();
  });

  it('retains five approved samples and enriches existing hierarchy rows', async () => {
    const masterMap = approvedFixture();
    const doctrineState = approvedDoctrineState();
    const bridge: WeeklyAnalysisBridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/research/range.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        liveDatabasePath: 'C:/research/range.sqlite3',
        analysisDatabasePath: 'C:/research/analysis-workspaces/v2/xauusd.sqlite3',
        masterMap,
        doctrineState,
        scripts: [{
          script_id: 'script-1',
          display_name: 'Weekly Script 1',
          version_label: '1',
          status: 'APPROVED',
          latest_version_status: 'APPROVED',
          current_approved_version_id: 'version-1',
        }],
      }),
      runWeeklyScript1: vi.fn(),
      reviewWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn(),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn(),
    };
    const ranges = [1, 2, 3, 4, 5].map((index) => ({ range_id: String(index) }));
    const structure = ranges.map((range) => <div key={String(range.range_id)}>Range {String(range.range_id)}</div>);

    await act(async () => {
      root.render(<HierarchyWorkspace ranges={ranges} structure={structure}
        onNavigateRange={vi.fn()} caseRef="case:live" symbol="XAUUSD"
        weeklyAnalysisBridge={bridge} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelectorAll('.weeklyScript1InlineEnrichment')).toHaveLength(5);
    expect(container.textContent).toContain('RL → RH · BOS Up');
    expect(container.textContent).toContain('RH → RL · BOS Down');

    const pythonTab = Array.from(container.querySelectorAll('[role="tab"]'))
      .find((button) => button.textContent === 'Python') as HTMLButtonElement;
    act(() => pythonTab.click());

    expect(container.textContent).toContain('Approved sample (5)');
    expect(container.querySelectorAll('.weeklyScript1Sample')).toHaveLength(5);
    expect(container.textContent).toContain('Analysis Approved');
    const approvedButton = Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent === 'Analysis Approved');
    expect(approvedButton).toBeUndefined();
  });
});
