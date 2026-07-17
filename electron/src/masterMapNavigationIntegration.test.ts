// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adaptMasterMapOutput } from './masterMapAdapter';
import {
  MasterMapHierarchyView,
  type MasterMapNavigationRequest,
} from './masterMapHierarchy';
import {
  createMasterMapStructuralNavigationPort,
  masterMapRangeToStructuralRangeRecord,
  navigateMasterMapHierarchyRequest,
  type MasterMapStructuralCandleLoadOptions,
} from './masterMapNavigationIntegration';
import type { StructuralNavigationRuntimeState } from './structuralChartNavigation';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('Master Map structural chart-navigation integration', () => {
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

  function createHarness(runtime: StructuralNavigationRuntimeState) {
    const calls: string[] = [];
    const mappingWrite = vi.fn();
    const routes = {
      getRuntimeState: vi.fn(() => runtime),
      switchStructuralTimeframe: vi.fn(async (timeframe: string, _options: { reason: string }) => {
        calls.push(`switch:${timeframe}`);
      }),
      loadCandles: vi.fn(async (timeframe: string, _options: MasterMapStructuralCandleLoadOptions) => {
        calls.push(`load:${timeframe}`);
      }),
      exposeReadOnlyStructuralHighlight: vi.fn(async (highlight: { canonicalRangeId: string }) => {
        calls.push(`highlight:${highlight.canonicalRangeId}`);
      }),
      applyExplicitStructuralCameraWindow: vi.fn(async (camera: { useFitContent: false }) => {
        calls.push(`camera:${camera.useFitContent}`);
      }),
      mappingWrite,
    };
    return {
      calls,
      mappingWrite,
      routes,
      port: createMasterMapStructuralNavigationPort(routes),
    };
  }

  function renderView(onNavigationRequest: (request: MasterMapNavigationRequest) => void) {
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(masterMapFixture()),
        onNavigationRequest,
      }));
    });
  }

  function renderTwoWeeklyView(onNavigationRequest: (request: MasterMapNavigationRequest) => void) {
    const output = masterMapFixture();
    const weeklyA = {
      ...((output.trusted_root as Record<string, unknown>).children as Record<string, unknown>[])[0],
      id: 'mm:range:weekly-a',
      range_high: 2800,
      range_low: 2300,
      range_high_time: '2026-01-04T00:00:00Z',
      range_low_time: '2026-01-01T00:00:00Z',
      active_from_time: '2026-01-04T00:00:00Z',
      inactive_from_time: '2026-03-01T00:00:00Z',
      children: [],
    };
    const weeklyB = {
      ...weeklyA,
      id: 'mm:range:weekly-b',
      range_high: 3300,
      range_low: 2900,
      range_high_time: '2026-04-05T00:00:00Z',
      range_low_time: '2026-04-01T00:00:00Z',
      active_from_time: '2026-04-05T00:00:00Z',
      inactive_from_time: '2026-06-01T00:00:00Z',
      source_refs: [{
        raw_id: 2,
        case_ref: 'case:live',
        source_record_id: 'weekly-b',
        payload_sha256: 'sha-weekly-b',
      }],
    };
    (output.trusted_root as Record<string, unknown>).children = [weeklyA, weeklyB];
    (output.root as Record<string, unknown>).children = [weeklyA, weeklyB];
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(output),
        onNavigationRequest,
      }));
    });
  }

  function click(selector: string) {
    const element = container.querySelector(selector) as HTMLElement | null;
    expect(element, `missing ${selector}`).not.toBeNull();
    act(() => element?.click());
  }

  it('routes a hierarchy click through the shared structural navigation contract in strict production order', async () => {
    const harness = createHarness({
      currentTimeframe: 'D1',
      replayActive: false,
      cameraOwner: 'USER_PAN_ZOOM',
    });
    let execution: ReturnType<typeof navigateMasterMapHierarchyRequest> | null = null;
    renderView((request) => {
      execution = navigateMasterMapHierarchyRequest(request, harness.port);
    });

    click('[data-canonical-range-id="mm:range:weekly-trusted"] .masterMapRangeMain');
    expect(execution).not.toBeNull();
    const result = await execution!;

    expect(result.ok).toBe(true);
    expect(harness.calls).toEqual([
      'switch:W1',
      'load:W1',
      'highlight:mm:range:weekly-trusted',
      'camera:false',
    ]);
    expect(harness.routes.switchStructuralTimeframe).toHaveBeenCalledWith(
      'W1',
      { reason: 'navigateStructuralTarget:hierarchy' },
    );
    expect(harness.routes.loadCandles).toHaveBeenCalledTimes(1);
    const loadOptions = harness.routes.loadCandles.mock.calls[0][1];
    expect(loadOptions).toMatchObject({
      reason: 'navigateStructuralTarget:hierarchy',
      structuralNavigation: true,
      deferCamera: true,
      skipCamera: true,
      timeframeSwitch: true,
      navigationPath: 'master-map-hierarchy',
    });
    if (result.ok) {
      expect(loadOptions.loadWindow).toEqual(result.plan.dataLoadWindow);
    }
    expect(harness.routes.applyExplicitStructuralCameraWindow).toHaveBeenCalledWith(
      expect.objectContaining({
        explicit: true,
        useFitContent: false,
        ownerBefore: 'USER_PAN_ZOOM',
        ownerAfter: 'FIT_RANGE',
        chartMode: 'hierarchy',
      }),
    );
    expect(harness.mappingWrite).not.toHaveBeenCalled();
  });

  it('adapts canonical Master Map selection into a read-only raw hierarchy chart context', () => {
    const output = masterMapFixture();
    const document = adaptMasterMapOutput(output);
    const range = document.trustedRoot.children[0];
    const record = masterMapRangeToStructuralRangeRecord({
      canonicalRangeId: range.canonicalRangeId,
      layer: range.layer,
      sourceTimeframe: range.sourceTimeframe,
      mode: 'trusted',
      range,
    });

    expect(record).toMatchObject({
      range_id: 'mm:range:weekly-trusted',
      canonical_range_id: 'mm:range:weekly-trusted',
      structure_layer: 'WEEKLY',
      source_timeframe: 'W1',
      range_high_price: 2800,
      range_low_price: 2300,
      range_high_time: '2026-01-04T00:00:00Z',
      range_low_time: '2026-01-01T00:00:00Z',
      status: 'BROKEN',
      direction_of_break: 'DOWN',
      navigation_status: 'TRUSTED',
      statistics_status: 'ELIGIBLE',
      read_only_canonical_master_map: true,
      mapping_assistant_gap: false,
    });
    expect(record?.source_refs).toEqual(range.sourceRefs);
  });

  it('keeps a statistics-excluded review-mode item navigable through the same read-only port', async () => {
    const harness = createHarness({ currentTimeframe: 'D1', replayActive: false });
    let execution: ReturnType<typeof navigateMasterMapHierarchyRequest> | null = null;
    renderView((request) => {
      execution = navigateMasterMapHierarchyRequest(request, harness.port);
    });

    click('[aria-label="Master Map hierarchy mode"] button:nth-child(2)');
    click('[aria-label="Expand WEEKLY mm:range:weekly-trusted"]');
    const reviewRow = container.querySelector('[data-canonical-range-id="mm:range:daily-review"]');
    expect(reviewRow?.getAttribute('data-statistics-status')).toBe('EXCLUDED');
    click('[data-canonical-range-id="mm:range:daily-review"] .masterMapRangeMain');
    const result = await execution!;

    expect(result.ok).toBe(true);
    expect(harness.calls).toEqual([
      'load:D1',
      'highlight:mm:range:daily-review',
      'camera:false',
    ]);
    expect(harness.routes.exposeReadOnlyStructuralHighlight).toHaveBeenCalledWith(
      expect.objectContaining({
        canonicalRangeId: 'mm:range:daily-review',
        reason: 'HIERARCHY',
      }),
    );
    expect(harness.mappingWrite).not.toHaveBeenCalled();
  });

  it('navigates consecutive canonical Weekly clicks on W1 with distinct windows', async () => {
    const harness = createHarness({
      currentTimeframe: 'W1',
      replayActive: false,
      cameraOwner: 'FIT_RANGE',
    });
    const executions: ReturnType<typeof navigateMasterMapHierarchyRequest>[] = [];
    renderTwoWeeklyView((request) => {
      executions.push(navigateMasterMapHierarchyRequest(request, harness.port));
    });

    click('[data-canonical-range-id="mm:range:weekly-a"] .masterMapRangeMain');
    click('[data-canonical-range-id="mm:range:weekly-b"] .masterMapRangeMain');
    const results = await Promise.all(executions);

    expect(results.every((result) => result.ok)).toBe(true);
    expect(harness.routes.switchStructuralTimeframe).not.toHaveBeenCalled();
    expect(harness.routes.loadCandles).toHaveBeenCalledTimes(2);
    expect(harness.routes.loadCandles.mock.calls.map(([timeframe]) => timeframe)).toEqual(['W1', 'W1']);
    expect(harness.routes.loadCandles.mock.calls[0][1].loadWindow)
      .not.toEqual(harness.routes.loadCandles.mock.calls[1][1].loadWindow);
    expect(harness.routes.exposeReadOnlyStructuralHighlight).toHaveBeenCalledWith(
      expect.objectContaining({ canonicalRangeId: 'mm:range:weekly-a' }),
    );
    expect(harness.routes.exposeReadOnlyStructuralHighlight).toHaveBeenCalledWith(
      expect.objectContaining({ canonicalRangeId: 'mm:range:weekly-b' }),
    );
    expect(harness.routes.applyExplicitStructuralCameraWindow).toHaveBeenCalledTimes(2);
    expect(harness.routes.applyExplicitStructuralCameraWindow.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        canonicalRangeId: 'mm:range:weekly-a',
        explicit: true,
        useFitContent: false,
        from: '2026-01-01T00:00:00.000Z',
        to: '2026-03-01T00:00:00.000Z',
      }),
    );
    expect(harness.routes.applyExplicitStructuralCameraWindow.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        canonicalRangeId: 'mm:range:weekly-b',
        explicit: true,
        useFitContent: false,
        from: '2026-04-01T00:00:00.000Z',
        to: '2026-06-01T00:00:00.000Z',
      }),
    );
    expect(container.querySelector('.masterMapHierarchy')?.getAttribute('data-selected-canonical-range-id'))
      .toBe('mm:range:weekly-b');
    expect(harness.mappingWrite).not.toHaveBeenCalled();
  });

  it('blocks a hierarchy click whose target is in replay future before every side effect', async () => {
    const harness = createHarness({
      currentTimeframe: 'W1',
      replayActive: true,
      replayCursorTime: '2025-12-31T00:00:00.000Z',
      cameraOwner: 'FIT_REPLAY',
    });
    let execution: ReturnType<typeof navigateMasterMapHierarchyRequest> | null = null;
    renderView((request) => {
      execution = navigateMasterMapHierarchyRequest(request, harness.port);
    });

    click('[data-canonical-range-id="mm:range:weekly-trusted"] .masterMapRangeMain');
    const result = await execution!;

    expect(result).toEqual({
      ok: false,
      error: 'Structural jump blocked: target is beyond the current replay cursor.',
    });
    expect(harness.calls).toEqual([]);
    expect(harness.routes.switchStructuralTimeframe).not.toHaveBeenCalled();
    expect(harness.routes.loadCandles).not.toHaveBeenCalled();
    expect(harness.routes.exposeReadOnlyStructuralHighlight).not.toHaveBeenCalled();
    expect(harness.routes.applyExplicitStructuralCameraWindow).not.toHaveBeenCalled();
    expect(harness.mappingWrite).not.toHaveBeenCalled();
  });
});
