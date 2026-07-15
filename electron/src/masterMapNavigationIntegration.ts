/** Master Map hierarchy -> Task C structural chart-navigation integration. */

import type { CandleLoadWindow } from './candleLoadPolicy';
import {
  navigateStructuralRangeRecord,
  type StructuralChartNavigationPort,
  type StructuralJumpExecutionResult,
  type StructuralJumpHighlight,
  type StructuralJumpPlan,
  type StructuralNavigationRuntimeState,
} from './structuralChartNavigation';
import type { MasterMapNavigationRequest } from './masterMapHierarchy';

export const MASTER_MAP_NAVIGATION_PATH = 'master-map-hierarchy' as const;

export type MasterMapStructuralCandleLoadOptions = {
  loadWindow: CandleLoadWindow;
  reason: string;
  structuralNavigation: true;
  deferCamera: true;
  skipCamera: true;
  timeframeSwitch: true;
  navigationPath: typeof MASTER_MAP_NAVIGATION_PATH;
};

/**
 * Existing renderer routes consumed by the Task C port. Deliberately absent:
 * mapping writes, structural saves, and routine-timeframe-memory operations.
 */
export type MasterMapStructuralNavigationRoutes = {
  getRuntimeState: () => StructuralNavigationRuntimeState;
  switchStructuralTimeframe: (
    timeframe: string,
    options: { reason: string },
  ) => Promise<void> | void;
  loadCandles: (
    timeframe: string,
    options: MasterMapStructuralCandleLoadOptions,
  ) => Promise<void> | void;
  exposeReadOnlyStructuralHighlight: (
    highlight: StructuralJumpHighlight,
  ) => Promise<void> | void;
  applyExplicitStructuralCameraWindow: (
    args: StructuralJumpPlan['camera'] & {
      reason: string;
      chartMode: StructuralJumpPlan['chartMode'];
    },
  ) => Promise<void> | void;
};

function sortedWindow(...values: Array<string | null | undefined>): { start: string; end: string } | null {
  const times = values
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .sort();
  if (!times.length) return null;
  return { start: times[0], end: times[times.length - 1] };
}

/**
 * Read-only adapter from Python-owned Master Map records to the raw hierarchy
 * chart-navigation shape. This is intentionally not a save payload.
 */
export function masterMapRangeToStructuralRangeRecord(request: MasterMapNavigationRequest): Record<string, unknown> | null {
  const range = request.range;
  const canonicalRangeId = String(request.canonicalRangeId || range?.canonicalRangeId || '').trim();
  const high = Number(range?.rangeHigh);
  const low = Number(range?.rangeLow);
  if (!canonicalRangeId || !Number.isFinite(high) || !Number.isFinite(low) || high <= low) return null;
  if (!range?.rangeHighTime || !range?.rangeLowTime) return null;
  const fallbackWindow = sortedWindow(range.rangeHighTime, range.rangeLowTime, range.activeFromTime, range.inactiveFromTime);
  const start = range.activeFromTime || fallbackWindow?.start || range.rangeHighTime || range.rangeLowTime;
  const end = range.inactiveFromTime || fallbackWindow?.end || range.rangeLowTime || range.rangeHighTime;
  return {
    range_id: canonicalRangeId,
    id: canonicalRangeId,
    canonical_range_id: canonicalRangeId,
    symbol: 'XAUUSD',
    structure_layer: request.layer,
    layer: request.layer,
    source_timeframe: request.sourceTimeframe || range.sourceTimeframe || undefined,
    chart_timeframe: request.sourceTimeframe || range.sourceTimeframe || undefined,
    range_high_price: high,
    range_high: high,
    range_low_price: low,
    range_low: low,
    range_high_time: range.rangeHighTime,
    range_low_time: range.rangeLowTime,
    range_start_time: start,
    range_end_time: end,
    active_from_time: range.activeFromTime,
    inactive_from_time: range.inactiveFromTime,
    status: range.status,
    direction_of_break: range.directionOfBreak,
    navigation_status: range.navigationStatus,
    statistics_status: range.statisticsStatus,
    ancestor_review_status: range.ancestorReviewStatus,
    direct_parent_link_status: range.directParentLinkStatus,
    review_context_only: range.reviewContextOnly,
    unlinked_review: range.unlinkedReview,
    source_refs: range.sourceRefs,
    source_count: range.sourceCount,
    read_only_canonical_master_map: true,
  };
}

/** The single production adapter between Master Map selection and Task C. */
export function createMasterMapStructuralNavigationPort(
  routes: MasterMapStructuralNavigationRoutes,
): StructuralChartNavigationPort {
  return {
    getRuntimeState: routes.getRuntimeState,
    switchStructuralTimeframe: (timeframe, options) => routes.switchStructuralTimeframe(
      timeframe,
      { reason: options.reason },
    ),
    loadStructuralCandleHistory: (args) => routes.loadCandles(args.timeframe, {
      loadWindow: args.loadWindow,
      reason: args.reason,
      structuralNavigation: true,
      deferCamera: true,
      skipCamera: true,
      timeframeSwitch: true,
      navigationPath: MASTER_MAP_NAVIGATION_PATH,
    }),
    exposeStructuralHighlight: routes.exposeReadOnlyStructuralHighlight,
    applyStructuralCameraWindow: (args) => {
      if (!args.explicit || args.useFitContent !== false) {
        throw new Error('Master Map structural camera navigation must be explicit and reject fitContent.');
      }
      return routes.applyExplicitStructuralCameraWindow(args);
    },
  };
}

/** Route every hierarchy mode, including review, through the same range contract. */
export function navigateMasterMapHierarchyRequest(
  request: MasterMapNavigationRequest,
  port: StructuralChartNavigationPort,
): Promise<StructuralJumpExecutionResult> {
  return navigateStructuralRangeRecord(request.range, port, {
    fallbackSymbol: 'XAUUSD',
    fallbackTimeframe: request.sourceTimeframe || undefined,
  });
}
