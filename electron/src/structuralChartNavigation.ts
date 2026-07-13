/** Reusable, read-only structural chart navigation planning and execution. */

import { resolveStructuralContextAndReplayWindows, type CandleLoadWindow } from './candleLoadPolicy';
import { resolveRangeChartTimeframe } from './hierarchyRangeNavigation';
import {
  isStructuralNavigationReason,
  shouldBlockTradingViewFitContent,
  type CameraViewOwner,
} from './chartViewportPolicy';
import type { StructuralJumpSource, StructuralJumpTarget } from './structuralJumpTarget';

export type StructuralNavigationRuntimeState = {
  currentTimeframe: string;
  replayActive?: boolean;
  replayCursorTime?: string | null;
  cameraOwner?: CameraViewOwner | null;
};

export type StructuralJumpHighlight = {
  canonicalRangeId: string;
  eventId?: string;
  structureLayer: string;
  rangeHighTime: string;
  rangeLowTime: string;
  activeFromTime: string;
  inactiveOrBreakTime?: string;
  preferredAnchorTime: string;
  visibleWindow: { start: string; end: string };
  reason: StructuralJumpSource;
  sourceRecordProvenance: StructuralJumpTarget['sourceRecordProvenance'];
};

export type StructuralJumpPlan = {
  target: StructuralJumpTarget;
  chartTimeframe: string;
  visualWindow: CandleLoadWindow;
  dataLoadWindow: CandleLoadWindow;
  navigationReason: string;
  chartMode: 'hierarchy' | 'replay';
  preserveReplayCursor: true;
  preserveRoutineTimeframeMemory: true;
  camera: {
    explicit: true;
    useFitContent: false;
    ownerBefore: CameraViewOwner;
    ownerAfter: 'FIT_RANGE' | 'FIT_REPLAY';
    from: string;
    to: string;
    target: string;
  };
  highlight: StructuralJumpHighlight;
};

export type StructuralJumpPlanResult =
  | { ok: true; plan: StructuralJumpPlan }
  | { ok: false; error: string };

export type StructuralChartNavigationPort = {
  getRuntimeState: () => StructuralNavigationRuntimeState;
  switchStructuralTimeframe: (
    timeframe: string,
    options: { reason: string; preserveRoutineTimeframeMemory: true },
  ) => Promise<void> | void;
  loadStructuralCandleHistory: (args: {
    timeframe: string;
    loadWindow: CandleLoadWindow;
    reason: string;
    structuralNavigation: true;
    deferCamera: true;
  }) => Promise<void> | void;
  exposeStructuralHighlight: (highlight: StructuralJumpHighlight) => Promise<void> | void;
  applyStructuralCameraWindow: (args: StructuralJumpPlan['camera'] & {
    reason: string;
    chartMode: StructuralJumpPlan['chartMode'];
  }) => Promise<void> | void;
};

export type StructuralJumpExecutionResult =
  | { ok: true; plan: StructuralJumpPlan }
  | { ok: false; error: string };

export function structuralNavigationReason(source: StructuralJumpSource): string {
  return `navigateStructuralTarget:${source.toLowerCase()}`;
}

export function resolveStructuralJumpTimeframe(target: StructuralJumpTarget, fallbackTimeframe = 'D1'): string {
  return resolveRangeChartTimeframe({
    structure_layer: target.structureLayer,
    source_timeframe: target.sourceTimeframe,
  }, fallbackTimeframe);
}

function isoMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) ? ms : null;
}

function replaySafeWindow(
  target: StructuralJumpTarget,
  state: StructuralNavigationRuntimeState,
): { window: { start: string; end: string }; anchor: string } | { error: string } {
  const fallbackTimes = [target.inactiveOrBreakTime, target.rangeHighTime, target.rangeLowTime, target.activeFromTime]
    .filter((value): value is string => !!value)
    .sort();
  const baseWindow = target.visibleWindow || {
    start: fallbackTimes[0],
    end: fallbackTimes[fallbackTimes.length - 1],
  };
  if (!state.replayActive) return { window: baseWindow, anchor: target.preferredAnchorTime };

  const cursorMs = isoMs(state.replayCursorTime);
  if (cursorMs === null) return { error: 'Structural jump blocked: replay is active but the replay cursor is unavailable.' };
  const startMs = isoMs(baseWindow.start);
  const endMs = isoMs(baseWindow.end);
  const anchorMs = isoMs(target.preferredAnchorTime);
  if (startMs === null || endMs === null || anchorMs === null) return { error: 'Structural jump blocked: target contains an invalid timestamp.' };
  if (startMs > cursorMs || anchorMs > cursorMs) {
    return { error: 'Structural jump blocked: target is beyond the current replay cursor.' };
  }
  const safeEndMs = Math.min(endMs, cursorMs);
  return {
    window: {
      start: new Date(startMs).toISOString(),
      end: new Date(Math.max(startMs, safeEndMs)).toISOString(),
    },
    anchor: new Date(Math.min(anchorMs, cursorMs)).toISOString(),
  };
}

export function buildStructuralJumpPlan(
  target: StructuralJumpTarget,
  state: StructuralNavigationRuntimeState,
): StructuralJumpPlanResult {
  const safe = replaySafeWindow(target, state);
  if ('error' in safe) return { ok: false, error: safe.error };
  const chartTimeframe = resolveStructuralJumpTimeframe(target, state.currentTimeframe);
  const windows = resolveStructuralContextAndReplayWindows({
    rangeSpan: safe.window,
    chartTf: chartTimeframe,
    structureLayer: target.structureLayer,
    label: `structural ${target.reason.toLowerCase()} target`,
  });
  if (!windows) return { ok: false, error: 'Structural jump blocked: no valid structural date window could be resolved.' };

  const navigationReason = structuralNavigationReason(target.reason);
  if (!isStructuralNavigationReason(navigationReason)) {
    return { ok: false, error: `Structural jump blocked: unrecognised camera reason ${navigationReason}.` };
  }
  const chartMode = state.replayActive ? 'replay' : 'hierarchy';
  if (!shouldBlockTradingViewFitContent(chartMode)) {
    return { ok: false, error: `Structural jump blocked: ${chartMode} mode must reject automatic fitContent.` };
  }
  const visualWindow = {
    ...windows.visualContext,
    start: safe.window.start.slice(0, 10),
    end: safe.window.end.slice(0, 10),
  };
  const ownerBefore = state.cameraOwner || 'AUTO';
  const camera: StructuralJumpPlan['camera'] = {
    explicit: true,
    useFitContent: false,
    ownerBefore,
    ownerAfter: state.replayActive ? 'FIT_REPLAY' : 'FIT_RANGE',
    from: safe.window.start,
    to: safe.window.end,
    target: safe.anchor,
  };
  return {
    ok: true,
    plan: {
      target,
      chartTimeframe,
      visualWindow,
      dataLoadWindow: windows.dataLoad,
      navigationReason,
      chartMode,
      preserveReplayCursor: true,
      preserveRoutineTimeframeMemory: true,
      camera,
      highlight: {
        canonicalRangeId: target.canonicalRangeId,
        eventId: target.eventId,
        structureLayer: target.structureLayer,
        rangeHighTime: target.rangeHighTime,
        rangeLowTime: target.rangeLowTime,
        activeFromTime: target.activeFromTime,
        inactiveOrBreakTime: target.inactiveOrBreakTime,
        preferredAnchorTime: safe.anchor,
        visibleWindow: safe.window,
        reason: target.reason,
        sourceRecordProvenance: target.sourceRecordProvenance,
      },
    },
  };
}

export async function navigateStructuralTarget(
  target: StructuralJumpTarget,
  port: StructuralChartNavigationPort,
): Promise<StructuralJumpExecutionResult> {
  const state = port.getRuntimeState();
  const result = buildStructuralJumpPlan(target, state);
  if (!result.ok) return result;
  const { plan } = result;
  if (String(state.currentTimeframe || '').toUpperCase() !== plan.chartTimeframe) {
    await port.switchStructuralTimeframe(plan.chartTimeframe, {
      reason: plan.navigationReason,
      preserveRoutineTimeframeMemory: true,
    });
  }
  await port.loadStructuralCandleHistory({
    timeframe: plan.chartTimeframe,
    loadWindow: plan.dataLoadWindow,
    reason: plan.navigationReason,
    structuralNavigation: true,
    deferCamera: true,
  });
  await port.exposeStructuralHighlight(plan.highlight);
  await port.applyStructuralCameraWindow({
    ...plan.camera,
    reason: plan.navigationReason,
    chartMode: plan.chartMode,
  });
  return { ok: true, plan };
}
