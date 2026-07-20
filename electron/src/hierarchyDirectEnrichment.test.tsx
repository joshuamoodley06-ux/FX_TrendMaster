// @vitest-environment happy-dom

import fs from 'fs';
import path from 'path';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  HierarchyWorkspace,
  type HierarchyRangeEnrichment,
  type WeeklyAnalysisBridge,
} from './hierarchyWorkspace';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function approvedPublishedMasterMap() {
  const fixture = masterMapFixture() as any;
  fixture.analysis = { weekly_script1: {
    pipeline_name: 'Weekly analysis',
    processing_version: 'weekly_script1_v1',
    run_id: 'approved-run',
    approval_state: 'APPROVED',
    script_content_hash: 'script-hash',
    sample_count: 1,
    approval_count: 1,
    publication_status: 'PUBLISHED',
    validation_samples: [],
    eligible: 1,
    analysed: 1,
  } };
  for (const rootName of ['trusted_root', 'review_root', 'root']) {
    const weekly = fixture[rootName].children[0];
    weekly.source_refs = [{
      raw_id: 42,
      case_ref: 'case:live',
      source_record_id: '42',
      payload_sha256: 'sha-42',
    }];
    weekly.script1_chronology = 'RL_TO_RH';
    weekly.script1_bos_direction = 'BOS_UP';
    weekly.script1_processing_status = 'COMPLETE';
    weekly.script1_review_status = 'APPROVED';
    weekly.analysis_enrichments = {
      weekly_structure: {
        version_id: 'version-1',
        version_label: '1',
        adapter_key: 'weekly_chronology_bos_v1',
        output_hash: 'output-42',
        payload: { chronology: 'RL_TO_RH', bos_direction: 'BOS_UP' },
      },
    };
  }
  return fixture;
}

describe('direct hierarchy enrichment contract', () => {
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
  });

  it('keys approved published enrichment by the raw structural range id', async () => {
    const bridge: WeeklyAnalysisBridge = {
      getPaths: vi.fn().mockResolvedValue({ ok: true, databasePath: 'C:/live.sqlite3' }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        source: 'DISPOSABLE_ANALYSIS_COPY',
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: approvedPublishedMasterMap(),
      }),
      runWeeklyScript1: vi.fn(),
      reviewWeeklyScript1: vi.fn(),
    };
    let receivedEnrichments: ReadonlyMap<string, HierarchyRangeEnrichment> | null = null;

    await act(async () => {
      root.render(<HierarchyWorkspace
        ranges={[{ range_id: '42', structure_layer: 'WEEKLY' }]}
        caseRef="case:live"
        symbol="XAUUSD"
        onNavigateRange={vi.fn()}
        weeklyAnalysisBridge={bridge}
        structure={(enrichmentsByRangeId) => {
          receivedEnrichments = enrichmentsByRangeId;
          const enrichment = enrichmentsByRangeId.get('42');
          return <div className="explorerTreeRow">
            <button type="button" className="explorerTreeRowMain">
              <span className="explorerTreeLine1">WEEKLY 01 Jan 2026</span>
              {enrichment && <span className="weeklyScript1InlineEnrichment">
                {enrichment.chronology} · {enrichment.bos}
              </span>}
            </button>
          </div>;
        }}
      />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(receivedEnrichments?.has('42')).toBe(true);
    expect(container.querySelector('.explorerTreeRow')?.textContent).toContain('RL → RH · BOS Up');
    expect(container.querySelector('[data-range-id]')).toBeNull();
    expect(container.querySelectorAll('.weeklyScript1InlineEnrichment')).toHaveLength(1);
  });

  it('passes a renderer callback to the production hierarchy workspace', () => {
    const mainSource = fs.readFileSync(path.resolve(__dirname, 'main.tsx'), 'utf8');
    expect(mainSource).toContain('structure={(enrichmentsByRangeId) => <>');
    expect(mainSource).not.toContain('structure={<>');
  });
});
