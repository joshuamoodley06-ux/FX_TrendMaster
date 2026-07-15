import { describe, expect, it, vi } from 'vitest';

import { adaptMasterMapOutput } from './masterMapAdapter';
import {
  createMasterMapStructuralNavigationPort,
  masterMapRangeToStructuralRangeRecord,
  navigateMasterMapHierarchyRequest,
} from './masterMapNavigationIntegration';
import type { MasterMapNavigationRequest } from './masterMapHierarchy';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('Mapping Assistant structural navigation', () => {
  function request(): MasterMapNavigationRequest {
    const document = adaptMasterMapOutput(masterMapFixture());
    const range = document.trustedRoot.children[0];
    return {
      canonicalRangeId: range.canonicalRangeId,
      layer: 'WEEKLY',
      sourceTimeframe: 'W1',
      mode: 'all',
      range,
      reason: 'GAP',
      eventId: 'mm:event:formation-bos',
      preferredAnchorTime: '2025-12-28T00:00:00Z',
      visibleStart: '2025-10-01T00:00:00Z',
      visibleEnd: '2026-02-02T00:00:00Z',
    };
  }

  it('keeps exact assistant fields in the canonical read-only record', () => {
    expect(masterMapRangeToStructuralRangeRecord(request())).toMatchObject({
      canonical_range_id: 'mm:range:weekly-trusted',
      canonical_event_id: 'mm:event:formation-bos',
      canonical_structure_layer: 'WEEKLY',
      structure_layer: 'WEEKLY',
      source_timeframe: 'W1',
      preferred_anchor_time: '2025-12-28T00:00:00Z',
      visible_start_time: '2025-10-01T00:00:00Z',
      visible_end_time: '2026-02-02T00:00:00Z',
      read_only_canonical_master_map: true,
      mapping_assistant_gap: true,
    });
  });

  it('preserves the Daily parent layer when an Intraday gap opens H4/H1 context', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const daily = document.trustedRoot.children[0].children[0];
    const record = masterMapRangeToStructuralRangeRecord({
      canonicalRangeId: daily.canonicalRangeId,
      layer: 'INTRADAY',
      sourceTimeframe: 'H1',
      mode: 'all',
      range: daily,
      reason: 'GAP',
      eventId: null,
      preferredAnchorTime: daily.activeFromTime,
      visibleStart: daily.rangeLowTime,
      visibleEnd: daily.rangeHighTime,
    });

    expect(record).toMatchObject({
      canonical_range_id: daily.canonicalRangeId,
      canonical_structure_layer: 'DAILY',
      structure_layer: 'INTRADAY',
      chart_timeframe: 'H1',
      read_only_canonical_master_map: true,
      mapping_assistant_gap: true,
    });
  });

  it('uses GAP reason, exact visual window, and exact preferred anchor', async () => {
    const switchStructuralTimeframe = vi.fn();
    const loadStructuralCandleHistory = vi.fn();
    const exposeStructuralHighlight = vi.fn();
    const applyStructuralCameraWindow = vi.fn();
    const port = createMasterMapStructuralNavigationPort({
      getRuntimeState: () => ({
        currentTimeframe: 'D1',
        replayActive: false,
        cameraOwner: 'USER_PAN_ZOOM',
      }),
      switchStructuralTimeframe,
      loadCandles: (_timeframe, options) => loadStructuralCandleHistory(options),
      exposeReadOnlyStructuralHighlight: exposeStructuralHighlight,
      applyExplicitStructuralCameraWindow: applyStructuralCameraWindow,
    });

    const result = await navigateMasterMapHierarchyRequest(request(), port);

    expect(result.ok).toBe(true);
    expect(switchStructuralTimeframe).toHaveBeenCalledWith('W1', {
      reason: 'navigateStructuralTarget:gap',
    });
    expect(exposeStructuralHighlight).toHaveBeenCalledWith(expect.objectContaining({
      canonicalRangeId: 'mm:range:weekly-trusted',
      eventId: 'mm:event:formation-bos',
      reason: 'GAP',
      preferredAnchorTime: '2025-12-28T00:00:00.000Z',
      visibleWindow: {
        start: '2025-10-01T00:00:00.000Z',
        end: '2026-02-02T00:00:00.000Z',
      },
    }));
    expect(applyStructuralCameraWindow).toHaveBeenCalledWith(expect.objectContaining({
      from: '2025-10-01T00:00:00.000Z',
      to: '2026-02-02T00:00:00.000Z',
      target: '2025-12-28T00:00:00.000Z',
      explicit: true,
      useFitContent: false,
      reason: 'navigateStructuralTarget:gap',
    }));
  });
});
