// @vitest-environment happy-dom

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import { HierarchyWorkspace, type WeeklyAnalysisBridge } from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function approvedOtherCaseState() {
  return {
    script_id: 'script-1',
    script_key: 'weekly_structure',
    status: 'APPROVED',
    current_approved_version_id: 'version-1',
    versions: [{ version_id: 'version-1', version_label: '1', approved_at: '2026-07-19T12:05:00Z' }],
    runs: [{
      run: {
        run_id: 'run-case-a',
        version_id: 'version-1',
        case_ref: 'case:a',
        symbol: 'XAUUSD',
        approval_status: 'APPROVED',
        publication_status: 'PUBLISHED',
        eligible_count: 5,
        analysed_count: 5,
        sample_count: 5,
        approval_count: 5,
      },
      samples: [{
        canonical_range_id: 'canonical-case-a',
        sample_order: 0,
        decision: 'APPROVED',
        decided_at: '2026-07-19T12:00:00Z',
      }],
    }],
  };
}

describe('Hierarchy doctrine case switch', () => {
  it('loads global approval without borrowing another case run', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const fixture = masterMapFixture();
    const bridge: WeeklyAnalysisBridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/research/range.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        liveDatabasePath: 'C:/research/range.sqlite3',
        analysisDatabasePath: 'C:/research/analysis-workspaces/v2/xauusd.sqlite3',
        masterMap: fixture,
        doctrineState: approvedOtherCaseState(),
        scripts: [],
      }),
      runWeeklyScript1: vi.fn(),
      reviewWeeklyScript1: vi.fn(),
      listDoctrineScripts: vi.fn(),
      insertDoctrineScript: vi.fn(),
      runDoctrinePipeline: vi.fn().mockResolvedValue({ ok: true, result: {} }),
    };

    await act(async () => {
      root.render(<HierarchyWorkspace ranges={[]} structure={<div>Case B hierarchy</div>}
        onNavigateRange={vi.fn()} caseRef="case:b" symbol="XAUUSD"
        weeklyAnalysisBridge={bridge} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const pythonTab = Array.from(container.querySelectorAll('[role="tab"]'))
      .find((button) => button.textContent === 'Python') as HTMLButtonElement;
    act(() => pythonTab.click());

    expect(container.textContent).toContain('Approved version ready · run the active pipeline for this case');
    expect(container.textContent).toContain('Approved script memory loaded. Run Active Pipeline to enrich this selected case.');
    expect(container.textContent).not.toContain('Approved sample (0)');
    const runButton = Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent === 'Run Active Pipeline') as HTMLButtonElement;
    expect(runButton.disabled).toBe(false);

    act(() => root.unmount());
    container.remove();
  });
});
