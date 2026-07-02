import type { Time } from 'lightweight-charts';
import { fxtmTimeToTradingViewTime, timeSortKey } from './candleAdapter';
import type { TradingViewBosMarker, TradingViewFitRequest, TradingViewOverlaySet, TradingViewRangeLine } from './types';

type SavedRangeOverlayInput = {
  rangeId?: string | number | null;
  structureLayer?: string;
  rangeScope?: string;
  status?: string;
  high?: number;
  low?: number;
  start?: string | null;
  end?: string | null;
  isActive?: boolean;
  isParentContext?: boolean;
};

type ParentRangeOverlayInput = {
  rangeId?: string | number | null;
  structureLayer?: string;
  kind?: 'high' | 'low' | string;
  price?: number;
  label?: string;
};

type EventOverlayInput = {
  id?: string | number;
  event_type?: string;
  event_name?: string;
  derived_event_code?: string;
  time?: string;
  price?: number;
};

type DraftAnchorInput = {
  price?: string;
  time?: string;
};

export type DraftRangeOverlayInput = {
  high?: number | null;
  low?: number | null;
  structureLayer?: string;
  visible?: boolean;
  start?: string | null;
  end?: string | null;
};

export type TradingViewOverlayAdapterInput = {
  timeframe: string;
  selectedRange?: unknown | null;
  savedRangeOverlays?: SavedRangeOverlayInput[];
  parentRangeOverlays?: ParentRangeOverlayInput[];
  visibleEvents?: EventOverlayInput[];
  draftRangeOverlay?: DraftRangeOverlayInput | null;
  draftRhAnchor?: DraftAnchorInput | null;
  draftRlAnchor?: DraftAnchorInput | null;
  suppressRangeGuideLines?: boolean;
};

export type TradingViewFitAdapterInput = {
  token?: number;
  intent?: string;
  reason?: string;
  fitWindow?: { start?: string; end?: string } | null;
  targetTime?: string | null;
  timeframe: string;
};

const LAYER_COLORS: Record<string, string> = {
  MACRO: '#a855f7',
  WEEKLY: '#ef4444',
  DAILY: '#22c55e',
  INTRADAY: '#3b82f6',
  MICRO: '#facc15',
};

export const TRADINGVIEW_LAYER_COLORS = LAYER_COLORS;

function finitePrice(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function rangeIdOf(value: any): string {
  return String(value?.rangeId ?? value?.range_id ?? value?.id ?? '');
}

function selectedRangeIds(selectedRange: unknown | null | undefined): Set<string> {
  const id = rangeIdOf(selectedRange);
  return id ? new Set([id]) : new Set<string>();
}

function selectedRangeFallback(selectedRange: unknown | null | undefined): SavedRangeOverlayInput | null {
  const range: any = selectedRange;
  const id = rangeIdOf(range);
  if (!id) return null;
  const high = finitePrice(range?.high ?? range?.range_high_price ?? range?.range_high);
  const low = finitePrice(range?.low ?? range?.range_low_price ?? range?.range_low);
  if (high === null && low === null) return null;
  return {
    rangeId: id,
    structureLayer: range?.structureLayer ?? range?.structure_layer ?? range?.layer,
    rangeScope: range?.rangeScope ?? range?.range_scope,
    status: range?.status,
    high: high ?? undefined,
    low: low ?? undefined,
    start: range?.start ?? range?.range_start_time ?? range?.range_high_time ?? null,
    end: range?.end ?? range?.range_end_time ?? range?.range_low_time ?? null,
    isActive: true,
  };
}

function lineStyleFor(range: SavedRangeOverlayInput): TradingViewRangeLine['lineStyle'] {
  const status = String(range.status || '').toUpperCase();
  if (status === 'BROKEN' || status === 'ABANDONED' || status === 'INACTIVE' || status === 'REPLACED') return 'dashed';
  if (String(range.rangeScope || '').toUpperCase() === 'MINOR') return 'dotted';
  return 'solid';
}

function rangeRole(range: SavedRangeOverlayInput, selectedIds: Set<string>): TradingViewRangeLine['role'] {
  const id = rangeIdOf(range);
  if ((id && selectedIds.has(id)) || range.isActive) return 'selected';
  if (range.isParentContext) return 'parent';
  return 'saved';
}

function rangeLineColor(layer: string | undefined): string {
  return LAYER_COLORS[String(layer || '').toUpperCase()] || '#94a3b8';
}

function addRangeLines(
  out: TradingViewRangeLine[],
  range: SavedRangeOverlayInput,
  selectedIds: Set<string>,
) {
  const high = finitePrice(range.high);
  const low = finitePrice(range.low);
  const id = rangeIdOf(range);
  const role = rangeRole(range, selectedIds);
  const layer = String(range.structureLayer || '').toUpperCase();
  const color = rangeLineColor(layer);
  const lineWidth = role === 'selected' ? 3 : role === 'parent' ? 2 : 1;
  const lineStyle = lineStyleFor(range);

  if (high !== null) {
    out.push({
      id: `${id || 'saved'}:RH`,
      rangeId: id || null,
      kind: 'RH',
      role,
      label: `${role === 'parent' ? 'Parent ' : ''}${layer || 'Range'} RH`,
      price: high,
      color,
      lineWidth,
      lineStyle,
    });
  }
  if (low !== null) {
    out.push({
      id: `${id || 'saved'}:RL`,
      rangeId: id || null,
      kind: 'RL',
      role,
      label: `${role === 'parent' ? 'Parent ' : ''}${layer || 'Range'} RL`,
      price: low,
      color,
      lineWidth,
      lineStyle,
    });
  }
}

function draftPrice(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  return finitePrice(value);
}

function resolveDraftRangeOverlay(input: TradingViewOverlayAdapterInput): DraftRangeOverlayInput | null {
  const draft = input.draftRangeOverlay;
  const high = draftPrice(draft?.high ?? input.draftRhAnchor?.price);
  const low = draftPrice(draft?.low ?? input.draftRlAnchor?.price);
  if (high === null && low === null) return null;
  if (draft?.visible === false) return null;
  return {
    high,
    low,
    structureLayer: draft?.structureLayer,
    visible: true,
    start: draft?.start ?? input.draftRhAnchor?.time ?? input.draftRlAnchor?.time ?? null,
    end: draft?.end ?? input.draftRlAnchor?.time ?? input.draftRhAnchor?.time ?? null,
  };
}

function addDraftRangeLines(out: TradingViewRangeLine[], draft: DraftRangeOverlayInput | null) {
  if (!draft?.visible) return;
  const high = draftPrice(draft.high);
  const low = draftPrice(draft.low);
  if (high === null && low === null) return;
  const layer = String(draft.structureLayer || '').toUpperCase();
  const color = LAYER_COLORS[layer] || '#38bdf8';
  const anchorsComplete = high !== null && low !== null;
  const lineStyle: TradingViewRangeLine['lineStyle'] = anchorsComplete ? 'solid' : 'dashed';
  const lineWidth = 2;
  if (high !== null) {
    out.push({
      id: 'draft:RH',
      rangeId: null,
      kind: 'RH',
      role: 'saved',
      label: `Draft ${layer || 'Range'} RH`,
      price: high,
      color,
      lineWidth,
      lineStyle,
    });
  }
  if (low !== null) {
    out.push({
      id: 'draft:RL',
      rangeId: null,
      kind: 'RL',
      role: 'saved',
      label: `Draft ${layer || 'Range'} RL`,
      price: low,
      color,
      lineWidth,
      lineStyle,
    });
  }
}

function addParentLine(out: TradingViewRangeLine[], overlay: ParentRangeOverlayInput, index: number) {
  const price = finitePrice(overlay.price);
  if (price === null) return;
  const kind = String(overlay.kind || '').toLowerCase() === 'low' ? 'RL' : 'RH';
  const layer = String(overlay.structureLayer || '').toUpperCase();
  out.push({
    id: `parent:${rangeIdOf(overlay) || index}:${kind}`,
    rangeId: overlay.rangeId ?? null,
    kind,
    role: 'parent',
    label: overlay.label || `${layer || 'Parent'} ${kind}`,
    price,
    color: rangeLineColor(layer),
    lineWidth: 2,
    lineStyle: 'dashed',
  });
}

function bosKind(event: EventOverlayInput): 'UP' | 'DOWN' | null {
  const raw = String(event.event_type || event.event_name || event.derived_event_code || '').toUpperCase();
  if (!raw.includes('BOS')) return null;
  if (raw.includes('DOWN')) return 'DOWN';
  if (raw.includes('UP')) return 'UP';
  return null;
}

function adaptBosMarker(event: EventOverlayInput, timeframe: string, index: number): TradingViewBosMarker | null {
  const direction = bosKind(event);
  if (!direction) return null;
  const time = fxtmTimeToTradingViewTime(event.time, timeframe);
  const price = finitePrice(event.price);
  if (!time || price === null) return null;
  return {
    id: String(event.id || `bos:${index}:${event.time}`),
    time,
    price,
    position: direction === 'UP' ? 'atPriceTop' : 'atPriceBottom',
    shape: direction === 'UP' ? 'arrowUp' : 'arrowDown',
    color: direction === 'UP' ? '#22c55e' : '#ef4444',
    text: `BOS ${direction}`,
    size: 1,
  };
}

export function adaptOverlaysForTradingView(input: TradingViewOverlayAdapterInput): TradingViewOverlaySet {
  const markers = (input.visibleEvents || [])
    .map((event, index) => adaptBosMarker(event, input.timeframe, index))
    .filter((marker): marker is TradingViewBosMarker => !!marker)
    .sort((a, b) => timeSortKey(a.time) - timeSortKey(b.time));

  if (input.suppressRangeGuideLines) {
    return {
      priceLines: [],
      markers,
      debug: {
        rangeOverlayCount: 0,
        rhRlLineCount: 0,
        bosMarkerCount: markers.length,
        selectedRangeFallbackUsed: false,
      },
    };
  }

  const selectedIds = selectedRangeIds(input.selectedRange);
  const priceLines: TradingViewRangeLine[] = [];
  const lineIds = new Set<string>();

  for (const range of input.savedRangeOverlays || []) {
    addRangeLines(priceLines, range, selectedIds);
  }
  for (const [index, overlay] of (input.parentRangeOverlays || []).entries()) {
    addParentLine(priceLines, overlay, index);
  }
  addDraftRangeLines(priceLines, resolveDraftRangeOverlay(input));
  const fallbackSelectedRange = selectedRangeFallback(input.selectedRange);
  let selectedRangeFallbackUsed = false;
  if (fallbackSelectedRange) {
    const selectedId = rangeIdOf(fallbackSelectedRange);
    const hasSelectedLine = priceLines.some((line) => String(line.rangeId || '') === selectedId);
    if (!hasSelectedLine) {
      selectedRangeFallbackUsed = true;
      addRangeLines(priceLines, fallbackSelectedRange, selectedIds);
    }
  }

  const dedupedLines = priceLines.filter((line) => {
    const key = `${line.role}:${line.rangeId ?? ''}:${line.kind}:${line.price}`;
    if (lineIds.has(key)) return false;
    lineIds.add(key);
    return true;
  });

  return {
    priceLines: dedupedLines,
    markers,
    debug: {
      rangeOverlayCount: dedupedLines.filter((line) => line.role !== 'parent' && !String(line.id).startsWith('draft:')).length,
      rhRlLineCount: dedupedLines.filter((line) => line.kind === 'RH' || line.kind === 'RL').length,
      bosMarkerCount: markers.length,
      selectedRangeFallbackUsed,
    },
  };
}

export function adaptFitRequestForTradingView(input: TradingViewFitAdapterInput): TradingViewFitRequest | null {
  if (input.intent !== 'FIT_STRUCTURAL_RANGE') return null;
  const token = Number(input.token || 0);
  if (!Number.isFinite(token) || token <= 0) return null;
  const from = fxtmTimeToTradingViewTime(input.fitWindow?.start, input.timeframe);
  const to = fxtmTimeToTradingViewTime(input.fitWindow?.end, input.timeframe);
  const target = fxtmTimeToTradingViewTime(input.targetTime, input.timeframe);
  if (from && to) return { token, from, to, target: target || undefined };
  if (target) return { token, target };
  return null;
}
