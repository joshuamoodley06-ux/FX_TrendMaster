import { describe, expect, it, vi } from 'vitest';
import { isStructuralNavigationReason } from './chartViewportPolicy';
import {
  buildStructuralJumpPlan,
  navigateStructuralTarget,
  resolveStructuralJumpTimeframe,
  structuralNavigationReason,
} from './structuralChartNavigation';
import type { StructuralJumpTarget } from './structuralJumpTarget';

const target: StructuralJumpTarget = {
  symbol: 'XAUUSD',
  structureLayer: 'INTRADAY',
  sourceTimeframe: 'H4',
  canonicalRangeId: 'mm:range:intraday-1',
  eventId: 'mm:event:1',
  rangeHighTime: '2026-06-01T08:00:00.000Z',
  rangeLowTime: '2026-06-01T12:00:00.000Z',
  activeFromTime: '2026-06-01T12:00:00.000Z',
  inactiveOrBreakTime: '2026-06-03T08:00:00.000Z',
  preferredAnchorTime: '2026-06-02T08:00:00.000Z',
  visibleWindow: {
    start: '2026-06-01T08:00:00.000Z',
    end: '2026-06-03T08:00:00.000Z',
  },
  sourceRecordProvenance: {
    caseRefs: ['case-live'],
    sourceRecordIds: ['500'],
    sourceRefs: [],
  },
  reason: 'REVIEW',
};

describe('structuralChartNavigation', () => {
  it('selects the compatible source timeframe and layer defaults', () => {
    expect(resolveStructuralJumpTimeframe(target, 'D1')).toBe('H4');
    expect(resolveStructuralJumpTimeframe({ ...target, sourceTimeframe: '', structureLayer: 'WEEKLY' }, 'D1')).toBe('W1');
    expect(resolveStructuralJumpTimeframe({ ...target, sourceTimeframe: 'M15', structureLayer: 'INTRADAY' }, 'D1')).toBe('H1');
  });

  it('builds an exact visual window plus a wider candle-history window', () => {
    const result = buildStructuralJumpPlan(target, {
      currentTimeframe: 'D1',
      replayActive: false,
      cameraOwner: 'USER_PAN_ZOOM',
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.plan.visualWindow).toMatchObject({ start: '2026-06-01', end: '2026-06-03' });
    expect(result.plan.dataLoadWindow.start < result.plan.visualWindow.start).toBe(true);
    expect(result.plan.dataLoadWindow.end > result.plan.visualWindow.end).toBe(true);
    expect(result.plan.camera).toMatchObject({
      explicit: true,
      useFitContent: false,
      ownerBefore: 'USER_PAN_ZOOM',
      ownerAfter: 'FIT_RANGE',
    });
    expect(result.plan.preserveRoutineTimeframeMemory).toBe(true);
  });

  it('uses an existing structural camera reason instead of routine timeframe memory', () => {
    const reason = structuralNavigationReason('GAP');
    expect(reason).toBe('navigateStructuralTarget:gap');
    expect(isStructuralNavigationReason(reason)).toBe(true);
    expect(reason.includes('routine-tf-memory')).toBe(false);
  });

  it('preserves replay cursor and caps the window without exposing future candles', () => {
    const result = buildStructuralJumpPlan({
      ...target,
      preferredAnchorTime: '2026-06-02T00:00:00.000Z',
    }, {
      currentTimeframe: 'H4',
      replayActive: true,
      replayCursorTime: '2026-06-02T12:00:00.000Z',
      cameraOwner: 'FIT_REPLAY',
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.plan.chartMode).toBe('replay');
    expect(result.plan.preserveReplayCursor).toBe(true);
    expect(result.plan.highlight.visibleWindow.end).toBe('2026-06-02T12:00:00.000Z');
    expect(result.plan.camera.ownerAfter).toBe('FIT_REPLAY');
    expect(result.plan.camera.useFitContent).toBe(false);
  });

  it('blocks a target beyond the current replay cursor', () => {
    const result = buildStructuralJumpPlan(target, {
      currentTimeframe: 'H4',
      replayActive: true,
      replayCursorTime: '2026-05-31T12:00:00.000Z',
    });
    expect(result).toEqual({
      ok: false,
      error: 'Structural jump blocked: target is beyond the current replay cursor.',
    });
  });

  it('executes switch, history load, highlight, then explicit camera fit', async () => {
    const calls: string[] = [];
    const result = await navigateStructuralTarget(target, {
      getRuntimeState: () => ({ currentTimeframe: 'D1', replayActive: false }),
      switchStructuralTimeframe: vi.fn(async (_tf: string, options: { reason: string }) => {
        calls.push(`switch:${options.reason}`);
      }),
      loadStructuralCandleHistory: vi.fn(async (args: { reason: string; deferCamera: true }) => {
        calls.push(`load:${args.reason}:${args.deferCamera}`);
      }),
      exposeStructuralHighlight: vi.fn(async (highlight: { canonicalRangeId: string }) => {
        calls.push(`highlight:${highlight.canonicalRangeId}`);
      }),
      applyStructuralCameraWindow: vi.fn(async (camera: { useFitContent: false; chartMode: string }) => {
        calls.push(`camera:${camera.useFitContent}:${camera.chartMode}`);
      }),
    });
    expect(result.ok).toBe(true);
    expect(calls).toEqual([
      'switch:navigateStructuralTarget:review',
      'load:navigateStructuralTarget:review:true',
      'highlight:mm:range:intraday-1',
      'camera:false:hierarchy',
    ]);
  });

  it('does not invoke any navigation side effect when replay safety blocks the target', async () => {
    const switchStructuralTimeframe = vi.fn();
    const loadStructuralCandleHistory = vi.fn();
    const exposeStructuralHighlight = vi.fn();
    const applyStructuralCameraWindow = vi.fn();
    const result = await navigateStructuralTarget(target, {
      getRuntimeState: () => ({
        currentTimeframe: 'H4',
        replayActive: true,
        replayCursorTime: '2026-05-31T12:00:00.000Z',
      }),
      switchStructuralTimeframe,
      loadStructuralCandleHistory,
      exposeStructuralHighlight,
      applyStructuralCameraWindow,
    });
    expect(result.ok).toBe(false);
    expect(switchStructuralTimeframe).not.toHaveBeenCalled();
    expect(loadStructuralCandleHistory).not.toHaveBeenCalled();
    expect(exposeStructuralHighlight).not.toHaveBeenCalled();
    expect(applyStructuralCameraWindow).not.toHaveBeenCalled();
  });
});
